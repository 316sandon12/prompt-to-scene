"""Small, image-backed reuse shortlists; interpretation stays with the connected AI."""

import hashlib
import json
from pathlib import Path

from . import background, core, creations, game_art, project_library, registry, semantics, workflow


def start(project, query, requirements=None, size=None, limit=6):
    """Recommend existing assets by purpose/style/size, with actual native thumbnails.

    Returns one task. Read recommendation_images after completion, inspect the images with
    the host's vision, then save_asset_matches. No image model or paid endpoint is invoked.
    Ambiguous filenames can enter a small fallback shortlist; they are marked unverified.
    """
    if not isinstance(query, str) or not query.strip() or len(query) > 300:
        raise ValueError("Describe the desired asset in at most 300 characters")
    if type(limit) is not int or not 1 <= limit <= 8:
        raise ValueError("Preview 1–8 candidates per request")
    project_library.validate_requirements(requirements)
    from . import development

    if size is not None:
        development.number(size, "size", 0.01, 1000)
    return background.submit(
        project,
        "asset_recommendations",
        dict(query=query, requirements=requirements, size=size, limit=limit),
    )


def stamp(project, native):
    target = registry.resolve(project)
    project_library.asset_path(project, native)
    path = (
        Path(target.root) / native
        if target.engine == "unity"
        else Path(target.root) / "Content" / (native.removeprefix("/Game/") + ".uasset")
    )
    return [path.stat().st_size, path.stat().st_mtime_ns] if path.is_file() else None


def run(job, query, requirements, size, limit):
    task = creations.step(job, "index", lambda: project_library.search(job.project))
    result = project_library.search(
        job.project, query, task["request_id"], size, min(100, limit * 8), requirements
    )
    rows = distinct(result["development"]["entries"], limit)
    if len(rows) < limit:
        fallback = project_library.search(
            job.project, "", task["request_id"], size, 100, requirements
        )["development"]["entries"]
        rows = distinct(rows + [{**r, "unverified_match": True} for r in fallback], limit)
    proofs = []
    if rows:
        captured = creations.step(
            job, "thumbnails", lambda: semantics.start(job.project, [r["path"] for r in rows])
        )
        proofs = captured["results"]
    by_path = {p["path"]: p for p in proofs}
    candidates = [
        {
            **r,
            "evidence_id": by_path[r["path"]]["request_id"],
            "source_stamp": stamp(job.project, r["path"]),
        }
        for r in rows
    ]
    review = dict(
        request_id=job.id,
        query=query,
        requirements=requirements or {},
        desired_size=size,
        candidates=candidates,
        truncated=result["development"].get("truncated", False),
        assessments=[],
    )
    core.atomic_json(
        game_art.root(job.project) / "asset-recommendations" / (job.id + ".json"), review
    )
    return {"stage": "Reuse candidates ready for visual comparison", **review}


def distinct(entries, limit):
    """Keep one representative of a generated asset, rather than prefab + FBX copies."""
    seen, result = set(), []
    for row in entries:
        key = ("asset", row["asset_id"]) if row.get("asset_id") else ("path", row["path"])
        if key not in seen:
            seen.add(key)
            result.append(row)
            if len(result) == limit:
                break
    return result


def evidence(project, request_id):
    """Return actual candidate images, dimensions, reasons and a token for visual assessment."""
    row = core.read_optional_json(
        game_art.root(project)
        / "asset-recommendations"
        / (workflow.identifier(request_id) + ".json")
    )
    if not row:
        raise ValueError("Wait for the recommendation task")
    images = []
    for candidate in row["candidates"]:
        proof, path = semantics.evidence(project, candidate["evidence_id"])
        if stamp(project, candidate["path"]) != candidate["source_stamp"]:
            raise ValueError("Candidate asset changed; request a fresh comparison")
        images.append(
            dict(path=str(path), asset_path=candidate["path"], sha256=proof["image_sha256"])
        )
    token = hashlib.sha256(
        json.dumps([row["query"], row["requirements"], images], sort_keys=True).encode()
    ).hexdigest()
    return {
        **row,
        "images": images,
        "token": token,
        "instruction": (
            "Compare visible silhouette, material, style and intended use. "
            "Dimensions are native metadata. Do not infer licensing from appearance. "
            "Save each match as reuse/adapt/reject with concrete reasons; "
            "no invented beauty scores."
        ),
    }


def assess(project, request_id, token, matches):
    """Retain observed reuse/adapt/reject decisions tied to the actual thumbnail versions."""
    row = evidence(project, request_id)
    if token != row["token"]:
        raise ValueError("Recommendation images changed; inspect them again")
    if not isinstance(matches, list) or len(matches) > len(row["candidates"]):
        raise ValueError("Assess only the captured candidates")
    paths = {r["path"] for r in row["candidates"]}
    seen, values = set(), []
    for match in matches:
        if (
            not isinstance(match, dict)
            or match.keys() != {"path", "decision", "reason"}
            or match["path"] not in paths
            or match["path"] in seen
        ):
            raise ValueError("Each match needs a unique candidate path, decision and reason")
        if match["decision"] not in {"reuse", "adapt", "reject"}:
            raise ValueError("Choose reuse, adapt or reject")
        reason = game_art.text(match["reason"], "reason", 1500)
        if not reason.strip():
            raise ValueError("Give a concrete visible reason")
        seen.add(match["path"])
        values.append({**match, "reason": reason})
    row["assessments"] = values
    core.atomic_json(
        game_art.root(project) / "asset-recommendations" / (request_id + ".json"),
        {k: v for k, v in row.items() if k not in {"images", "instruction"}},
    )
    return row


def reuse(project, request_id, token, path, position=None):
    """Place a reviewed candidate as its original native reference; never duplicate source files."""
    row = evidence(project, request_id)
    if token != row["token"] or not any(
        m["path"] == path and m["decision"] == "reuse" for m in row["assessments"]
    ):
        raise ValueError("Choose an inspected candidate marked reuse, or adapt its materials first")
    return project_library.reuse(project, path, "place", position)
