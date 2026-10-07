"""Isolated, real-geometry candidate studies and explicit final publication."""

import json
import uuid
from copy import deepcopy

from . import core, design, game_art, recipes, registry, styles, workflow


def create(project, kind, asset_id, parameters=None, count=3):
    if type(count) is not int or not 2 <= count <= 3:
        raise ValueError("Choose two or three candidates")
    core.asset_id(asset_id)
    art = styles.read(project)
    brief = game_art.for_recipe(project, asset_id, kind)
    if brief:
        art = brief["style"]
    prepared = []
    for i in range(count):
        values = {
            **(parameters or {}),
            "variant": i,
            "seed": int((parameters or {}).get("seed", 0)) + i * 71,
        }
        script, recipe = recipes.prepare(kind, values, style=art, quality="draft", art_design=brief)
        p = recipe["parameters"]
        frame = [
            [-p["width"] * 0.65, -p["depth"] * 0.65, 0],
            [
                p["width"] * 0.65,
                p["depth"] * 0.65,
                p["height"] * (1.7 if kind == "bench" else 1.15),
            ],
        ]
        script += (
            '\nimport bpy\nbpy.context.scene["pts_preview_frame"] = '
            + repr(json.dumps(frame))
            + "\n"
        )
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
                    "label": design.VARIANTS[kind][i],
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
    from .authoring import submit_recipe

    task = submit_recipe(project, record["asset_id"], script, recipe, position)
    record["chosen"] = {"index": index, "quality": final_quality, "request_id": task["request_id"]}
    core.atomic_json(path, record)
    return task


def preview_path(project, asset_id, revision, view="studio"):
    core.asset_id(asset_id)
    workflow.identifier(revision)
    if view not in {"studio", "front", "back", "before"}:
        raise ValueError("View must be studio, front, back or before")
    root = core.state_root(registry.resolve(project).root)
    path = root / "work" / asset_id / revision / (view + ".png")
    if (
        not path.resolve().is_relative_to(root)
        or not path.is_file()
        or path.stat().st_size > 10 * 1024 * 1024
    ):
        raise ValueError("Preview is not ready or is invalid")
    return path
