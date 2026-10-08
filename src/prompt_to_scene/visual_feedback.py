"""Image-backed appearance feedback with stale-revision guards and reusable preferences."""

import hashlib
from pathlib import Path

from . import core, game_art, reviews, workflow


def evidence(project, request_id):
    state = workflow.job_status(project, workflow.identifier(request_id))
    if state.get("kind") != "quality" or state["status"] != "completed":
        raise ValueError("Wait for the quality review to finish")
    info = workflow.inspect_asset(project, state["asset_id"])
    if info["current"].get("request_id") != state["asset_revision"]:
        raise ValueError("Asset changed; capture its current appearance")
    review = reviews.read(project, state["review_id"])
    images = []
    for stage in ("before", "after"):
        receipt = review["captures"][stage]
        if receipt["status"] != "completed":
            raise ValueError("Wait for the actual images")
        path = game_art.root(project) / "previews" / (receipt["request_id"] + ".png")
        images.append(
            {
                "stage": stage,
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    reference = state.get("brief", {})
    if reference.get("image"):
        path = Path(reference["image"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
            raise ValueError("Reference changed; save it and start a new review")
        images.append({"stage": "reference", "path": str(path), "sha256": reference["sha256"]})
    token = hashlib.sha256(str([(i["stage"], i["sha256"]) for i in images]).encode()).hexdigest()
    return {
        "request_id": request_id,
        "asset_id": state["asset_id"],
        "token": token,
        "asset_revision": state["asset_revision"],
        "view": review["view"],
        "images": images,
        "parts": (info.get("metadata") or {}).get("report", {}).get("parts", {}),
        "design": state.get("art_design"),
        "criteria": [
            "silhouette at game distance",
            "readable interaction point",
            "reference proportions and construction",
            "material scale and noise",
            "contact, thickness and moving clearance",
        ],
        "instructions": "Inspect these pixels, identify concrete part-level differences. "
        "Save observations; repair only affected unlocked parts. "
        "Acceptance is a host/user judgment, never a geometry test result.",
    }


def save(project, request_id, token, observations, accepted=False, preference=""):
    proof = evidence(project, request_id)
    if token != proof["token"]:
        raise ValueError("Images changed since inspection")
    observations = game_art.text(observations, "observations", 2000)
    preference = game_art.text(preference, "preference", 1000)
    if not observations or type(accepted) is not bool:
        raise ValueError("Provide visible observations and a boolean accepted value")
    row = {k: proof[k] for k in ("request_id", "asset_id", "asset_revision", "token", "view")}
    row.update(
        observations=observations,
        accepted=accepted,
        preference=preference,
        updated_utc=workflow.now(),
    )
    core.atomic_json(game_art.root(project) / "visual-feedback" / (request_id + ".json"), row)
    if preference:
        path = game_art.root(project) / "visual-preferences.json"
        records = core.read_optional_json(path) or []
        records = [r for r in records if r["request_id"] != request_id]
        core.atomic_json(path, [*records, row][-20:])
    return row
