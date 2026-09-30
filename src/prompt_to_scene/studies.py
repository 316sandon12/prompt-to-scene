"""Isolated, real-geometry candidate studies and explicit final publication."""

import uuid
from copy import deepcopy

from . import core, recipes, registry, styles, workflow


def create(project, kind, asset_id, parameters=None, count=3):
    if type(count) is not int or not 2 <= count <= 3:
        raise ValueError("Choose two or three candidates")
    core.asset_id(asset_id)
    art = styles.read(project)
    prepared = []
    for i in range(count):
        values = {
            **(parameters or {}),
            "variant": i,
            "seed": int((parameters or {}).get("seed", 0)) + i * 71,
        }
        script, recipe = recipes.prepare(kind, values, style=art, quality="draft")
        prepared.append((script, recipe))
    root = core.state_root(registry.resolve(project).root)
    study_id = uuid.uuid4().hex
    record = {
        "study_id": study_id,
        "asset_id": asset_id,
        "kind": kind,
        "final_quality": art["quality"],
        "candidates": [],
        "created_utc": workflow.now(),
    }
    core.atomic_json(root / "studies" / (study_id + ".json"), record)
    try:
        for i, (script, recipe) in enumerate(prepared):
            name = "draft_" + study_id[:16] + "_" + str(i + 1)
            task = workflow.submit(project, name, script, recipe=recipe, preview_only=True)
            record["candidates"].append(
                {
                    "index": i + 1,
                    "asset_id": name,
                    "request_id": task["request_id"],
                    "recipe": recipe,
                }
            )
            core.atomic_json(root / "studies" / (study_id + ".json"), record)
    except Exception as error:
        record["error"] = str(error)
        core.atomic_json(root / "studies" / (study_id + ".json"), record)
        raise
    return read(project, study_id)


def read(project, study_id):
    workflow.identifier(study_id)
    root = core.state_root(registry.resolve(project).root)
    record = core.read_optional_json(root / "studies" / (study_id + ".json"))
    if not record:
        raise ValueError("Unknown candidate study")
    result = deepcopy(record)
    if result.get("chosen"):
        final = workflow.job_status(project, result["chosen"]["request_id"])
        result["chosen"].update(status=final["status"], error=final.get("error"))
    for candidate in result["candidates"]:
        state = workflow.job_status(project, candidate["request_id"])
        candidate.update(
            status=state["status"],
            report=state.get("report"),
            error=state.get("error"),
            views=state.get("previews", []),
        )
        candidate.pop("recipe", None)
    result["status"] = (
        "error"
        if record.get("error")
        or any(c["status"] in {"error", "cancelled"} for c in result["candidates"])
        else "completed"
        if all(c["status"] == "completed" for c in result["candidates"])
        else "building"
    )
    result["preview_source"] = (
        "Actual Blender geometry, consistent studio lighting; not an engine screenshot"
    )
    return result


def choose(project, study_id, index, quality=None, position=None):
    result = read(project, study_id)
    if type(index) is not int or not 1 <= index <= len(result["candidates"]):
        raise ValueError("Choose a listed candidate index")
    if result["candidates"][index - 1]["status"] != "completed":
        raise ValueError("Wait until this draft finishes")
    root = core.state_root(registry.resolve(project).root)
    path = root / "studies" / (study_id + ".json")
    record = core.read_optional_json(path)
    final_quality = quality or record["final_quality"]
    if final_quality == "draft":
        final_quality = "desktop"
    previous = record.get("chosen")
    if previous and previous["index"] == index and previous["quality"] == final_quality:
        state = workflow.job_status(project, previous["request_id"])
        if state["status"] not in {"error", "cancelled"}:
            return state
    recipe = record["candidates"][index - 1]["recipe"]
    script, recipe = recipes.revise(recipe, quality=final_quality)
    task = workflow.submit(project, record["asset_id"], script, position, recipe=recipe)
    record["chosen"] = {"index": index, "quality": final_quality, "request_id": task["request_id"]}
    core.atomic_json(path, record)
    return task


def preview_path(project, asset_id, revision, view="studio"):
    core.asset_id(asset_id)
    workflow.identifier(revision)
    if view not in {"studio", "front", "back"}:
        raise ValueError("View must be studio, front or back")
    root = core.state_root(registry.resolve(project).root)
    path = root / "work" / asset_id / revision / (view + ".png")
    if (
        not path.resolve().is_relative_to(root)
        or not path.is_file()
        or path.stat().st_size > 10 * 1024 * 1024
    ):
        raise ValueError("Preview is not ready or is invalid")
    return path
