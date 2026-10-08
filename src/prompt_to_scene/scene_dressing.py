"""Furnish a real blockout using measured props while reserving walking and interaction space."""

import json
import math

from . import background, core, development, layout, workflow


def submit(
    project, level_id, asset_ids, room_index=0, approach=0.75, protected_zones=None, duplicate=True
):
    core.asset_id(level_id)
    if not isinstance(asset_ids, list) or not 1 <= len(asset_ids) <= 12:
        raise ValueError("Choose one to twelve already imported props")
    for name in asset_ids:
        core.asset_id(name)
    if len(set(asset_ids)) != len(asset_ids) or type(room_index) is not int or room_index < 0:
        raise ValueError("Use unique assets and a non-negative room index")
    approach = development.number(approach, "Interaction approach", 0.3, 2)
    if type(duplicate) is not bool:
        raise ValueError("duplicate must be a boolean")
    zones = protected_zones or []
    if not isinstance(zones, list) or len(zones) > 20:
        raise ValueError("Use at most twenty camera/interaction exclusion boxes")
    for zone in zones:
        if set(zone) != {"bounds_min", "bounds_max"}:
            raise ValueError("Exclusion zones need bounds_min and bounds_max in engine meters")
        for key in zone:
            core.position_values(zone[key])
        if any(zone["bounds_min"][i] >= zone["bounds_max"][i] for i in range(3)):
            raise ValueError("Exclusion box has no volume")
    return background.submit(
        project,
        "dressing",
        dict(
            level_id=level_id,
            asset_ids=asset_ids,
            room_index=room_index,
            approach=approach,
            protected_zones=zones,
            duplicate=duplicate,
        ),
    )


def plan(
    scene, level, asset_ids, room_index=0, approach=0.75, protected_zones=None, duplicate=True
):
    engine = scene["engine"]
    up = 1 if engine == "unity" else 2
    a, b = [i for i in range(3) if i != up]
    floor = next((x for x in level["boxes"] if x["name"] == "floor_" + str(room_index)), None)
    if not floor:
        raise ValueError("Choose a room floor from this level; stairs cannot be furnished")
    angle = floor["yaw"]
    center = floor["position"][:]
    center[up] += floor["size"][up] / 2
    anchor = next(
        (
            o
            for o in scene["context"]
            if o["name"].endswith(floor["name"])
            and math.dist(o["position"], floor["position"]) < 0.03
        ),
        None,
    )
    if not anchor:
        raise ValueError("Room floor changed; inspect the current blockout")
    reserved = list(protected_zones or [])
    radius = level["player_radius"] + 0.12
    for row in level["checkpoints"]:
        foot = row["position"]
        low, high = foot[:], foot[:]
        for axis in (a, b):
            low[axis] -= radius
            high[axis] += radius
        high[up] += level["player_height"]
        reserved.append({"bounds_min": low, "bounds_max": high})
    result, approaches = [], []
    for name in asset_ids:
        obj = next((o for o in scene["assets"] if o["asset_id"] == name), None)
        if not obj:
            raise ValueError("Import a source instance first: " + name)
        selected = None
        # Search perimeter slots, preserving the level's connected central routes.
        for side in range(4):
            for fraction in (0, -0.55, 0.55, -0.28, 0.28, -0.78, 0.78):
                rotation = [0, 0, 0]
                rotation[up] = angle + side * 90
                # Measure the oriented asset at the candidate orientation in room coordinates.
                oriented = layout.pose(
                    obj,
                    [0, 0, 0],
                    [0, side * 90, 0] if up == 1 else [0, 0, side * 90],
                    obj["scale"],
                    engine,
                )
                size = [oriented["bounds_max"][i] - oriented["bounds_min"][i] for i in range(3)]
                axis, along = (b, a) if side % 2 == 0 else (a, b)
                sign = -1 if side in (0, 3) else 1
                offset = [0, 0, 0]
                offset[axis] = sign * (floor["size"][axis] / 2 - size[axis] / 2 - 0.16)
                offset[along] = fraction * (floor["size"][along] - size[along]) / 2
                if any(size[i] + 0.32 > floor["size"][i] for i in (a, b)):
                    continue
                offset = layout.rotate(offset, angle, engine)
                initial = layout.pose(obj, center, rotation, obj["scale"], engine)
                position = [
                    center[i]
                    + offset[i]
                    + center[i]
                    - (initial["bounds_min"][i] + initial["bounds_max"][i]) / 2
                    for i in range(3)
                ]
                position[up] = center[up] + center[up] - initial["bounds_min"][up]
                placed = layout.pose(obj, position, rotation, obj["scale"], engine)
                if any(layout.overlaps(placed, zone) for zone in reserved + approaches):
                    continue
                clearance = {key: placed[key][:] for key in ("bounds_min", "bounds_max")}
                # Reserve the inward-facing approach in world axes, conservatively for yaw.
                direction = [0, 0, 0]
                direction[axis] = -sign * approach
                direction = layout.rotate(direction, angle, engine)
                for i in (a, b):
                    clearance["bounds_min"][i] += min(0, direction[i])
                    clearance["bounds_max"][i] += max(0, direction[i])
                if any(layout.overlaps(clearance, p) for p in result):
                    continue
                candidate = layout.placement(obj, placed, duplicate)
                try:
                    layout.check_placements(scene, [*result, candidate], anchor["id"])
                except ValueError:
                    continue
                selected = candidate
                approaches.append(clearance)
                break
            if selected:
                break
        if not selected:
            raise ValueError(
                "No clear slot for " + name + "; use fewer/smaller props or a larger room"
            )
        result.append(selected)
    return {
        "scene": scene["scene"],
        "anchor": anchor,
        "placements": result,
        "snap_to_surface": False,
    }


def run(job, level_id, asset_ids, room_index, approach, protected_zones, duplicate=True):
    previous = job.state.get("layout_task")
    if previous and workflow.job_status(job.project, previous["request_id"])["status"] in {
        "error",
        "cancelled",
    }:
        job.update(layout_task=None)
    if not job.state.get("layout_task"):
        state = job.wait(
            development.request(job.project, "level", level_id=level_id, mode="inspect")
        )
        level = json.loads(state["development"]["plan_json"])
        scene = job.action("inspect")
        values = plan(scene, level, asset_ids, room_index, approach, protected_zones, duplicate)
        job.update(stage="Furnishing the room with reserved walking space", plan=values)
        job.update(layout_task=job.track(workflow.action(job.project, "arrange", values=values)))
    result = job.wait(job.state["layout_task"])
    check = job.wait(development.request(job.project, "level", level_id=level_id, mode="check"))
    if not check["development"].get("passed"):
        job.action("undo", undo_id=result["undo_id"])
        job.update(layout_task=None, rolled_back=True)
        raise ValueError("Native walking clearance failed; furniture placement was undone")
    return {
        "stage": "Furnished room ready",
        "layout": result,
        "clearance": check,
        "undo_id": result["undo_id"],
        "reserved_approach_m": approach,
    }
