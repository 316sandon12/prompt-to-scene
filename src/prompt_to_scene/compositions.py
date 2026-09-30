"""Build, place and reuse small furnished scenes through checked native layouts."""

import math
from copy import deepcopy

from . import background, core, kits, layout, registry, workflow


def submit(
    project,
    kit="reading_corner",
    prefix="corner",
    position=None,
    yaw=0,
    anchor_id=None,
    mode="create",
    template=None,
    asset_ids=None,
):
    if mode not in {"create", "save", "place"}:
        raise ValueError("Choose create, save or place")
    if mode == "create" and kit not in kits.KITS:
        raise ValueError("Unknown scene kit")
    core.asset_id(prefix)
    if position is not None:
        core.position_values(position)
    if not isinstance(yaw, (int, float)) or not math.isfinite(yaw):
        raise ValueError("Yaw must be finite degrees")
    if template:
        core.asset_id(template)
    if mode != "create" and not template:
        raise ValueError("Choose a layout template name")
    for name in asset_ids or []:
        core.asset_id(name)
    return background.submit(
        project,
        "composition",
        dict(
            kit=kit,
            prefix=prefix,
            position=position,
            yaw=yaw,
            anchor_id=anchor_id,
            mode=mode,
            template=template,
            asset_ids=asset_ids,
        ),
    )


def templates(project):
    root = core.state_root(registry.resolve(project).root)
    return [core.read_optional_json(p) for p in sorted((root / "layouts").glob("*.json"))]


def planned(scene, assets, origin, angle, anchor, kit=None, saved=None, duplicate=False):
    engine = scene["engine"]
    up = 1 if engine == "unity" else 2
    a, b = [i for i in range(3) if i != up]
    rows = []
    primary = assets[0]
    psize = [primary["bounds_max"][i] - primary["bounds_min"][i] for i in range(3)]
    patterns = {
        "reading_corner": {"chair": (0, -1), "shelf": (-1, 0)},
        "village_market": {"crate": (0, -1), "barrel": (1, 0), "sign": (-1, 0)},
        "makers_workshop": {"stool": (0, -1), "cabinet": (-1, 0), "shelf": (1, 0)},
    }
    for index, obj in enumerate(assets):
        rotation = [0, 0, 0]
        scale = list(obj["scale"])
        if saved:
            row = saved[index]
            offset, rotation, scale = (
                deepcopy(row["offset"]),
                deepcopy(row["rotation"]),
                row["scale"],
            )
            rotation[up] += angle
        else:
            kind = obj["asset_id"].rsplit("_", 1)[-1]
            direction = patterns[kit].get(kind, (0, 0))
            size = [obj["bounds_max"][i] - obj["bounds_min"][i] for i in range(3)]
            offset = [0.0, 0.0, 0.0]
            offset[a] = direction[0] * (psize[a] / 2 + size[a] / 2 + 0.45)
            offset[b] = direction[1] * (psize[b] / 2 + size[b] / 2 + 0.55)
            if kind in {"chair", "stool", "sign", "shelf", "cabinet"} and any(direction):
                rotation[up] = (
                    math.degrees(math.atan2(-offset[a], -offset[b]))
                    if engine == "unity"
                    else math.degrees(math.atan2(-offset[b], -offset[a]))
                )
            rotation[up] += angle
        offset = layout.rotate(offset, angle, engine)
        target = [origin[i] + offset[i] for i in range(3)]
        placed = layout.pose(obj, target, rotation, scale, engine)
        if not saved:
            target[up] += origin[up] - placed["bounds_min"][up]
            placed = layout.pose(obj, target, rotation, scale, engine)
        rows.append(layout.placement(obj, placed, duplicate))
    layout.check_placements(scene, rows, anchor["id"])
    return {
        "scene": scene["scene"],
        "anchor": anchor,
        "placements": rows,
        "snap_to_surface": not bool(saved),
    }


def run(job, kit, prefix, position, yaw, anchor_id, mode, template, asset_ids):
    if not job.state.get("initial"):
        job.update(stage="Reading the target scene")
        job.update(initial=job.action("inspect"))
    initial = job.state["initial"]
    if mode == "save":
        objects = (
            [o for o in initial["assets"] if o["asset_id"] in (asset_ids or [])]
            if asset_ids
            else initial["selected"]
        )
        if not objects or len(objects) > 32:
            raise ValueError("Select one to 32 managed instances to save")
        origin = objects[0]["position"]
        data = {
            "name": template,
            "engine": initial["engine"],
            "items": [
                {
                    "asset_id": o["asset_id"],
                    "offset": [o["position"][i] - origin[i] for i in range(3)],
                    "rotation": o["rotation"],
                    "scale": o["scale"],
                }
                for o in objects
            ],
        }
        core.atomic_json(job.root / "layouts" / (template + ".json"), data)
        return {"stage": "Layout saved", "template": data}
    if mode == "create":
        from .authoring import submit_recipe

        prepared, _ = kits.blueprint(job.project, kit, prefix)
        if not job.state.get("reserved_assets"):
            for name, _, _, _ in prepared:
                if workflow.inspect_asset(job.project, name)["current"]["status"] != "unknown":
                    raise ValueError("Kit prefix is already in use; choose a new prefix")
            job.update(reserved_assets=[row[0] for row in prepared], asset_tasks=[])
        tasks = list(job.state.get("asset_tasks", []))
        for name, script, recipe, initial_position in prepared:
            job.check()
            task = next((t for t in tasks if t["asset_id"] == name), None)
            if task and workflow.job_status(job.project, task["request_id"])["status"] in {
                "error",
                "cancelled",
            }:
                # Retry only the local build; native import preserves existing instances.
                tasks.remove(task)
                task = None
            if not task:
                job.update(stage="Building " + name)
                task = submit_recipe(job.project, name, script, recipe, initial_position)
                tasks.append(task)
                job.update(asset_tasks=tasks)
            job.wait(task)
        ids = [t["asset_id"] for t in job.state["asset_tasks"]]
        ids.sort(key=lambda name: not name.endswith("_table"))
        saved = None
    else:
        saved = core.read_optional_json(job.root / "layouts" / (template + ".json"))
        if not saved or saved["engine"] != initial["engine"]:
            raise ValueError("Use a saved layout for this engine")
        saved = saved["items"]
        ids = [row["asset_id"] for row in saved]
    if job.state.get("layout_request"):
        saved_request = job.state["layout_request"]
        if workflow.job_status(job.project, saved_request["request_id"])["status"] not in {
            "error",
            "cancelled",
        }:
            result = job.wait(saved_request)
            return {
                "stage": "Scene layout ready",
                "layout": result,
                "undo_id": result.get("undo_id"),
            }
        job.update(layout_request=None)
    job.update(stage="Placing the composition")
    scene = job.action("inspect")
    if scene["scene"] != initial["scene"]:
        raise ValueError(
            "The scene changed during generation. Reopen the original scene and resume."
        )
    assets = []
    for name in ids:
        obj = next((o for o in scene["assets"] if o["asset_id"] == name), None)
        if not obj:
            raise ValueError("Import a source instance before reusing this layout: " + name)
        assets.append(obj)
    selected = initial.get("selected_context", [])
    anchor_id = anchor_id or (selected[0]["id"] if len(selected) == 1 else assets[0]["id"])
    anchor = next((o for o in scene["context"] if o["id"] == anchor_id), None)
    if anchor is None:
        raise ValueError("The chosen anchor was removed")
    up = 1 if scene["engine"] == "unity" else 2
    origin = list(position or anchor["position"])
    if position is None and anchor_id not in {o["id"] for o in assets}:
        origin[up] = anchor["bounds_max"][up]
    angle = yaw + (layout.yaw(anchor, scene["engine"]) if position is None else 0)
    values = planned(scene, assets, origin, angle, anchor, kit, saved, mode == "place")
    request = workflow.action(job.project, "arrange", values=values)
    job.update(layout_request=request)
    result = job.wait(request)
    return {"stage": "Scene layout ready", "layout": result, "undo_id": result.get("undo_id")}
