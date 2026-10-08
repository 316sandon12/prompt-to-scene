"""Search existing project assets before generating another copy."""

import re

from . import core, development, organization, registry, workflow

ALIASES = {
    "木": "wood",
    "门": "door",
    "箱": "crate chest",
    "椅": "chair",
    "桌": "table",
    "石": "stone",
    "金属": "metal",
    "卡通": "cartoon stylized",
    "科幻": "sci fi",
    "灯": "lamp light",
    "花瓶": "vase",
    "墙": "wall",
}


def asset_path(project, path):
    engine = registry.resolve(project).engine
    prefix = "Assets/" if engine == "unity" else "/Game/"
    if not isinstance(path, str) or not path.startswith(prefix) or ".." in path or "\\" in path:
        raise ValueError("Choose an asset inside " + prefix)
    return path


def annotate(project, path, tags=None, notes="", license="", source=""):
    asset_path(project, path)
    if (
        not isinstance(tags or [], list)
        or len(tags or []) > 32
        or any(not isinstance(t, str) or len(t) > 60 for t in tags or [])
    ):
        raise ValueError("Use at most 32 short tags")
    if any(not isinstance(v, str) or len(v) > 2000 for v in (notes, license, source)):
        raise ValueError("Metadata fields must be text up to 2000 characters")
    root = core.state_root(registry.resolve(project).root)
    data = dict(tags=tags or [], notes=notes, license=license, source=source)
    organization.save_annotation(root, path, data)
    return {"path": path, **data}


def rank(entries, query, annotations=None, size=None, limit=20, requirements=None):
    terms = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", query.lower())
    for key, words in ALIASES.items():
        if key in query:
            terms.extend(words.split())
    rows = []
    for original in entries:
        annotation = (annotations or {}).get(original["path"], {})
        entry = {**original, **{k: v for k, v in annotation.items() if v}}
        entry["tags"] = list(
            dict.fromkeys([*original.get("tags", []), *annotation.get("tags", [])])
        )
        semantic = annotation.get("semantic", {})
        entry["tags"] = list(
            dict.fromkeys(
                [
                    *entry["tags"],
                    *semantic.get("materials", []),
                    *semantic.get("uses", []),
                    semantic.get("object_type", ""),
                    semantic.get("style", ""),
                ]
            )
        )
        entry["tags"] = [tag for tag in entry["tags"] if tag]
        text = " ".join(
            [
                entry.get("name", ""),
                entry["path"],
                entry.get("notes", ""),
                semantic.get("name", ""),
                semantic.get("description", ""),
                *entry.get("tags", []),
            ]
        ).lower()
        score = sum(3 if t == entry.get("name", "").lower() else 1 for t in set(terms) if t in text)
        reasons = []
        requirements = requirements or {}
        for field in ("style", "uses", "materials"):
            wanted = requirements.get(field, [])
            wanted = [wanted] if isinstance(wanted, str) else wanted
            observed = semantic.get(field, "")
            observed = " ".join(observed) if isinstance(observed, list) else observed
            for word in wanted:
                if word.casefold() in (observed + " " + " ".join(entry["tags"])).casefold():
                    score += 4
                    reasons.append(field + ": " + word)
        if (
            requirements.get("max_triangles")
            and entry.get("triangles", 0) > requirements["max_triangles"]
        ):
            continue
        if terms and score == 0:
            continue
        if size and entry.get("size"):
            score += max(0, 1 - abs(max(entry["size"]) - size) / max(size, 0.001))
        entry["score"] = round(score, 3)
        entry["match_reasons"] = reasons
        if not entry.get("license"):
            entry["license"] = "Unknown — check the asset's original license"
        rows.append(entry)
    return sorted(rows, key=lambda r: (-r["score"], r["path"]))[:limit]


def search(project, query="", request_id=None, size=None, limit=20, requirements=None):
    if (
        not isinstance(query, str)
        or len(query) > 300
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise ValueError("Use a short query and limit between 1 and 100")
    if size is not None:
        size = development.number(size, "Desired longest dimension", 0.01, 1000)
    if requirements is not None:
        if not isinstance(requirements, dict) or requirements.keys() - {
            "style",
            "uses",
            "materials",
            "max_triangles",
        }:
            raise ValueError("Match style, uses, materials and an optional maximum triangle count")
        for key, value in requirements.items():
            if key == "max_triangles":
                development.number(value, key, 1, 2000000)
            elif (
                not isinstance(value, (str, list))
                or len(value) > (120 if isinstance(value, str) else 12)
                or isinstance(value, list)
                and any(not isinstance(v, str) or len(v) > 120 for v in value)
            ):
                raise ValueError("Use short style/material/use descriptions")
    if not request_id:
        return development.request(project, "library", mode="index")
    receipt = workflow.job_status(project, request_id)
    if receipt["status"] != "completed":
        return receipt
    data = receipt.get("development", {})
    if data.get("command") != "library":
        raise ValueError("Use the request ID returned by search_project_assets")
    root = core.state_root(registry.resolve(project).root)
    organization.sync_annotations(root)
    annotations = core.read_optional_json(root / "project-library.json") or {}
    for entry in data.get("entries", []):
        name = entry.get("asset_id")
        if not name or not core.ASSET_ID.fullmatch(name):
            continue
        successes = [core.read_optional_json(p) for p in (root / "history" / name).glob("*.json")]
        successes = [s for s in successes if s and s.get("status") == "imported"]
        if not successes:
            continue
        latest = max(successes, key=lambda s: s.get("completed_utc", ""))
        metadata = (
            core.read_optional_json(
                root / "work" / name / workflow.identifier(latest["request_id"]) / "asset.json"
            )
            or {}
        )
        provenance = metadata.get("provenance") or {}
        if provenance.get("license") and provenance["license"] != "user-supplied":
            entry["license"] = provenance["license"]
        entry["source"] = (
            provenance.get("url") or provenance.get("page") or provenance.get("path", "")
        )
        recipe = metadata.get("recipe") or {}
        if recipe.get("style", {}).get("name"):
            entry["tags"] = [*entry.get("tags", []), recipe["style"]["name"]]
    return {
        **receipt,
        "development": {
            **data,
            "entries": rank(data.get("entries", []), query, annotations, size, limit, requirements),
        },
        "query": query,
    }


def reuse(project, path, mode="place", position=None):
    asset_path(project, path)
    if mode not in {"place", "preview"}:
        raise ValueError("Choose place or preview")
    return development.request(
        project, "library", mode=mode, path=path, position=core.position_values(position)
    )
