"""Persistent art briefs, native diagnostics, bounded repairs and same-camera evidence."""

import hashlib
import shutil
from pathlib import Path

from . import authoring, background, core, parts, performance, registry, reviews, workflow


def brief(project):
    root = core.state_root(registry.resolve(project).root)
    return core.read_optional_json(root / "art-brief.json") or {
        "notes": "",
        "reference_asset": None,
    }


def set_brief(project, image_path=None, reference_asset=None, notes="", overrides=None):
    if not isinstance(notes, str) or len(notes) > 4000:
        raise ValueError("Art direction notes must be at most 4000 characters")
    root = core.state_root(registry.resolve(project).root)
    data = brief(project)
    if image_path:
        source = Path(image_path).expanduser().resolve()
        if (
            source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
            or not source.is_file()
            or source.stat().st_size > 10 * 1024**2
        ):
            raise ValueError("Choose a PNG, JPEG or WebP reference up to 10 MiB")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        saved = root / "references" / (digest + source.suffix.lower())
        saved.parent.mkdir(parents=True, exist_ok=True)
        if source != saved:
            shutil.copy2(source, saved)
        data.update(image=str(saved), sha256=digest)
    if reference_asset or overrides:
        data["style"] = authoring.set_style(
            project, reference_asset=reference_asset, overrides=overrides
        )
    data.update(notes=notes, reference_asset=reference_asset, updated_utc=workflow.now())
    core.atomic_json(root / "art-brief.json", data)
    return data


def findings(native):
    result = []
    for row in native.get("metrics", []):
        if row.get("missing_materials", 0):
            result.append({"object_id": row["id"], "kind": "missing_material", "severity": "error"})
        if row.get("support_known") and abs(row.get("support_gap", 0)) > 0.015:
            result.append(
                {
                    "object_id": row["id"],
                    "kind": "floating" if row["support_gap"] > 0 else "below_surface",
                    "distance_m": row["support_gap"],
                    "fix": "ground",
                }
            )
        if row.get("overlap_candidates"):
            result.append(
                {
                    "object_id": row["id"],
                    "kind": "possible_overlap",
                    "others": row["overlap_candidates"],
                    "requires_visual_review": True,
                }
            )
    return result


def start(project, asset_id, auto_fix=False, preset="scene_prop"):
    if type(auto_fix) is not bool:
        raise ValueError("auto_fix must be a boolean")
    info = workflow.inspect_asset(project, asset_id)
    if info["current"].get("status") != "imported":
        raise ValueError("Import this asset before checking it")
    if preset not in performance.PRESETS:
        raise ValueError("Unknown usage preset")
    return background.submit(
        project,
        "quality",
        {
            "asset_id": asset_id,
            "auto_fix": auto_fix,
            "preset": preset,
            "revision": info["current"]["request_id"],
        },
        asset_id,
    )


def run(job, asset_id, auto_fix, preset, revision):
    pending = job.state.get("part_repair")
    if pending:
        result = job.wait(pending)
        job.update(asset_revision=result["request_id"])
    revision = job.state.get("asset_revision", revision)
    current = workflow.inspect_asset(job.project, asset_id)["current"]
    if current.get("request_id") != revision:
        raise ValueError("Asset changed; start a fresh review")
    job.update(
        stage="Checking native asset and recording the current view", brief=brief(job.project)
    )
    if not job.state.get("before_capture"):
        capture = reviews.capture(job.project, asset_id, stage="before")
        job.update(before_capture=capture, review_id=capture["review_id"], repair_count=0)
    job.wait(job.state["before_capture"])
    if not job.state.get("before"):
        before = job.action("analyze", asset_id=asset_id, scope="asset")
        job.update(before=performance.summarize(before, preset), findings=findings(before))
    issues = job.state["findings"]
    groundable = [i for i in issues if i.get("fix") == "ground" and abs(i["distance_m"]) <= 0.5]
    if auto_fix and groundable and not job.state.get("repair_request") and not pending:
        if any(i.get("fix") == "ground" and abs(i["distance_m"]) > 0.5 for i in issues):
            raise ValueError("Large support offset needs review before automatic placement")
        request = workflow.action(job.project, "ground", asset_id=asset_id, scope="asset")
        job.update(
            repair_request=request, repair_count=1, stage="Aligning props to detected surfaces"
        )
    if job.state.get("repair_request"):
        job.wait(job.state["repair_request"])
    after = job.action("analyze", asset_id=asset_id, scope="asset")
    capture = reviews.capture(
        job.project,
        asset_id,
        stage="after",
        review_id=job.state["review_id"],
        refresh=bool(pending),
    )
    job.wait(capture)
    return {
        "stage": "Ready for visual review",
        "after": performance.summarize(after, preset),
        "findings": findings(after),
        "review": reviews.read(job.project, job.state["review_id"]),
        "requires_visual_review": True,
        "asset_revision": revision,
        "guidance": (
            "Compare native before/after and the saved reference using the client's vision. "
            "Apply at most two concrete part/material repairs. No aesthetic score is assigned."
        ),
    }


def repair(project, request_id, part=None, changes=None):
    root = core.state_root(registry.resolve(project).root)
    path = root / "jobs" / workflow.identifier(request_id) / "state.json"
    if not path.is_file():
        raise ValueError("Unknown quality review")
    with background.lock(path):
        state = core.read_optional_json(path)
        if state.get("kind") != "quality":
            raise ValueError("Choose a quality review")
        if state["status"] == "building":
            return state
        if state["status"] != "completed":
            raise ValueError("Complete or resume this quality review first")
        if state.get("repair_count", 0) >= 2:
            raise ValueError("Two-repair limit reached; compare the result before a new review")
        info = workflow.inspect_asset(project, state["asset_id"])
        if info["current"].get("request_id") != state["asset_revision"]:
            raise ValueError("Asset changed outside this review; start a new review")
        if not part or not changes:
            raise ValueError("Supply a named part and concrete changes from visual inspection")
        task = (
            authoring.edit_part(project, state["asset_id"], part, changes)
            if info["metadata"].get("recipe")
            else parts.edit(project, state["asset_id"], part, changes)
        )
        state.update(
            part_repair=task,
            repair_count=state.get("repair_count", 0) + 1,
            status="building",
            stage="Applying repair and refreshing the same-camera comparison",
        )
        core.atomic_json(path, state)
        try:
            child = workflow.launch_worker(path.with_name("spec.json"))
            core.atomic_json(path.with_name("process.json"), {"pid": child.pid})
        except OSError as error:
            state.update(status="error", error=str(error))
            core.atomic_json(path, state)
            raise
        return state
