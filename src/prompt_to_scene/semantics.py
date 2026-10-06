"""Evidence-backed asset descriptions. Vision is optional; filenames are never visual proof."""

import base64
import hashlib
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from . import (
    background,
    core,
    credentials,
    development,
    generation,
    organization,
    project_library,
    registry,
    workflow,
)


def configure(endpoint=None, model=None, api_key=None):
    path = registry.home() / "vision.json"
    if endpoint is None:
        return core.read_optional_json(path) or {"configured": False}
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"})
    ):
        raise ValueError(
            "Use an HTTPS API base URL, or HTTP on loopback, without embedded credentials"
        )
    if not isinstance(model, str) or not 1 <= len(model) <= 120:
        raise ValueError("Specify the vision model served by this endpoint")
    if api_key:
        credentials.put("vision", api_key)
    data = {"configured": True, "endpoint": endpoint.rstrip("/"), "model": model}
    core.atomic_json(path, data)
    return data


def labels(value):
    if not isinstance(value, dict) or value.keys() - {
        "name",
        "description",
        "object_type",
        "materials",
        "style",
        "uses",
        "confidence",
    }:
        raise ValueError("Unknown semantic label field")
    result = {}
    for key in ("name", "description", "object_type", "style"):
        text = value.get(key, "")
        if not isinstance(text, str) or len(text) > (1200 if key == "description" else 100):
            raise ValueError("Use short text for " + key)
        result[key] = text.strip()
    if not result["name"] or not result["object_type"]:
        raise ValueError("Give the object a suggested name and type")
    for key in ("materials", "uses"):
        entries = value.get(key, [])
        if (
            not isinstance(entries, list)
            or len(entries) > 12
            or any(not isinstance(v, str) or len(v) > 80 for v in entries)
        ):
            raise ValueError("Use at most 12 short " + key)
        result[key] = entries
    result["confidence"] = development.number(value.get("confidence", 0), "Confidence", 0, 1)
    return result


def evidence(project, request_id):
    root = core.state_root(registry.resolve(project).root)
    value = core.read_optional_json(
        root / "semantic-evidence" / (workflow.identifier(request_id) + ".json")
    )
    if not value:
        raise ValueError("Capture this asset before describing its contents")
    preview = root / "previews" / (request_id + ".png")
    if (
        not preview.is_file()
        or preview.stat().st_size > 10 * 1024**2
        or hashlib.sha256(preview.read_bytes()).hexdigest() != value["image_sha256"]
    ):
        raise ValueError("Visual evidence is missing or changed; capture again")
    return value, preview


def save(project, evidence_id, description, corrected=False):
    proof, _ = evidence(project, evidence_id)
    data = labels(description)
    root = core.state_root(registry.resolve(project).root)
    organization.sync_annotations(root)
    path = proof["path"]
    # Annotation writes share the organizer lock; its path migrations retain these fields.
    with organization.annotation_lock(root):
        records = core.read_optional_json(root / "project-library.json") or {}
        matches = [
            native
            for native, record in records.items()
            if evidence_id in record.get("evidence_ids", [])
        ]
        if len(matches) > 1:
            raise ValueError("Evidence is attached to multiple assets; capture again")
        if matches:
            path = matches[0]
        previous = records.get(path, {})
        if previous.get("semantic", {}).get("corrected") and not corrected:
            raise ValueError(
                "This description was corrected by a user; keep it or explicitly correct it"
            )
        previous.update(
            semantic={
                **data,
                "evidence_id": evidence_id,
                "corrected": bool(corrected),
                "source": "user correction" if corrected else "visual description",
                "updated_utc": workflow.now(),
            }
        )
        records[path] = previous
        core.atomic_json(root / "project-library.json", records)
    return {"path": path, **previous, "review_required": data["confidence"] < 0.75}


def start(project, paths, use_provider=False, allow_remote=False):
    if not isinstance(paths, list) or not 1 <= len(paths) <= 20:
        raise ValueError("Choose 1–20 model/prefab assets for visual indexing")
    paths = list(dict.fromkeys(project_library.asset_path(project, p) for p in paths))
    if use_provider:
        config = configure()
        if not config.get("configured"):
            raise ValueError(
                "Configure a vision endpoint or let the connected AI describe the captured images"
            )
        if (
            urlsplit(config["endpoint"]).hostname not in {"localhost", "127.0.0.1", "::1"}
            and not allow_remote
        ):
            raise ValueError(
                "Remote vision sends thumbnails to the configured provider; set "
                "allow_remote when authorized"
            )
    return background.submit(project, "semantic", dict(paths=paths, use_provider=use_provider))


def infer(image, metadata):
    config = configure()
    content = [
        {
            "type": "text",
            "text": "Describe the visible game asset. Return only JSON with name, "
            "description, object_type, materials (array), style, uses (array), "
            "confidence (0–1). Include useful Chinese and English search words. "
            "Dimensions/triangles are metadata, not visual proof. Be conservative; "
            "do not infer hidden geometry or provenance. Metadata:"
            + json.dumps(metadata, ensure_ascii=False),
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()
            },
        },
    ]
    headers = {"Content-Type": "application/json"}
    key = credentials.get("vision")
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(
        config["endpoint"] + "/chat/completions",
        data=json.dumps(
            {
                "model": config["model"],
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 800,
            }
        ).encode(),
        headers=headers,
    )
    try:
        with urllib.request.build_opener(generation.NoRedirect).open(
            request, timeout=90
        ) as response:
            raw = response.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError("Vision response is too large")
        text = json.loads(raw)["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return labels(json.loads(text))
    except urllib.error.HTTPError as error:
        raise ValueError("Vision endpoint returned HTTP " + str(error.code)) from None


def run(job, paths, use_provider=False):
    index = job.wait(project_library.search(job.project))["development"]["entries"]
    metadata = {e["path"]: e for e in index}
    results = list(job.state.get("results", []))
    done = {r["path"] for r in results}
    for path in paths:
        job.check()
        if path in done:
            continue
        if path not in metadata:
            raise ValueError("Choose an indexed model/prefab/Blueprint: " + path)
        job.update(stage="Rendering asset thumbnail: " + path)
        task = job.wait(project_library.reuse(job.project, path, "preview"))
        revision = task["request_id"]
        preview = job.root / "previews" / (revision + ".png")
        proof = {
            "path": path,
            "request_id": revision,
            "metadata": metadata[path],
            "captured_utc": workflow.now(),
            "image_sha256": hashlib.sha256(preview.read_bytes()).hexdigest(),
        }
        core.atomic_json(job.root / "semantic-evidence" / (revision + ".json"), proof)
        with organization.annotation_lock(job.root):
            records = core.read_optional_json(job.root / "project-library.json") or {}
            row = records.setdefault(path, {})
            row["evidence_ids"] = [*row.get("evidence_ids", []), revision][-20:]
            row["thumbnail_request_id"] = revision
            core.atomic_json(job.root / "project-library.json", records)
        if use_provider:
            job.update(stage="Describing the captured image")
            proof["description"] = save(job.project, revision, infer(preview, metadata[path]))
        results.append(proof)
        job.update(results=results)
    return {
        "results": results,
        "message": "Native thumbnails captured. Describe them with the connected "
        "AI, or use the configured vision endpoint."
        if not use_provider
        else "Visual descriptions indexed; low-confidence suggestions require review.",
    }
