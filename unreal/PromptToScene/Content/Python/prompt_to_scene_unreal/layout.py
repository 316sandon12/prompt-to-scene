"""Apply preflighted world-space layouts, with native duplication and persistent undo."""

import math

import unreal

from .protocol import write_json


def context():
    from . import actions

    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).get_current_level()
    return [
        a
        for a in actions.actors().get_all_level_actors()
        if isinstance(a, unreal.StaticMeshActor)
        and a.get_level() == level
        and a.static_mesh_component.static_mesh
    ]


def near(a, b):
    return (
        a is not None
        and b is not None
        and len(a) == len(b)
        and all(abs(x - y) < 0.002 for x, y in zip(a, b))
    )


def overlap(row, other):
    broad = all(
        min(row["bounds_max"][i], other["bounds_max"][i])
        - max(row["bounds_min"][i], other["bounds_min"][i])
        > 0.005
        for i in range(3)
    )
    if not broad:
        return False
    a, b = row.get("footprint"), other.get("footprint")
    if not a or not b:
        return True
    for shape in (a, b):
        for i in range(0, len(shape), 2):
            j = (i + 2) % len(shape)
            axis = (-(shape[j + 1] - shape[i + 1]), shape[j] - shape[i])
            length = math.hypot(*axis)
            if length < 1e-8:
                continue
            projections = [
                [(p[k] * axis[0] + p[k + 1] * axis[1]) / length for k in range(0, len(p), 2)]
                for p in (a, b)
            ]
            if min(max(p) for p in projections) - max(min(p) for p in projections) <= 0.005:
                return False
    return True


def arrange(request, root):
    from . import actions

    if request.get("scene") != actions.scene():
        raise ValueError("Level changed; inspect and plan again")
    placements = request.get("placements")
    if not isinstance(placements, list) or not 1 <= len(placements) <= 32:
        raise ValueError("Invalid layout plan")
    objects = {actions.guid(a): a for a in context()}
    expected_anchor = request.get("anchor", {})
    anchor = objects.get(expected_anchor.get("id"))
    if not anchor:
        raise ValueError("Anchor is no longer loaded")
    current_anchor = actions.describe(anchor)
    if any(
        not near(current_anchor[k], expected_anchor.get(k))
        for k in ("position", "rotation", "scale", "bounds_min", "bounds_max")
    ):
        raise ValueError("Anchor changed; plan again")
    moved = set()
    for row in placements:
        for key in ("position", "rotation", "scale", "bounds_min", "bounds_max"):
            values = row.get(key)
            if (
                not isinstance(values, list)
                or len(values) != 3
                or any(
                    not isinstance(v, (float, int))
                    or not math.isfinite(v)
                    or (key == "scale" and not 0 < v <= 100)
                    for v in values
                )
            ):
                raise ValueError("Invalid placement vector")
        source = objects.get(row.get("source_id"))
        if not source or actions.asset_id(source) != row.get("asset_id"):
            raise ValueError("Source instance is missing")
        current = actions.describe(source)
        if any(
            not near(current[k], row.get("expected", {}).get(k))
            for k in ("position", "rotation", "scale", "bounds_min", "bounds_max")
        ):
            raise ValueError("Source changed; plan again")
        if not row.get("duplicate"):
            if row["source_id"] in moved:
                raise ValueError("Duplicate target in layout")
            moved.add(row["source_id"])
    for key, actor in objects.items():
        if key not in moved | {actions.guid(anchor)} and any(
            overlap(row, actions.describe(actor)) for row in placements
        ):
            raise ValueError("Layout overlaps " + actor.get_actor_label())
    snapshot = {
        "scene": actions.scene(),
        "objects": [actions.describe(objects[key]) for key in moved],
        "created_ids": [],
    }
    path = root / "edits" / (request["request_id"] + ".json")
    write_json(path, snapshot)
    created, changed = [], []
    try:
        with unreal.ScopedEditorTransaction("Prompt-to-Scene: arrange props"):
            for row in placements:
                actor = objects[row["source_id"]]
                if row.get("duplicate"):
                    source = actor
                    actor = actions.actors().spawn_actor_from_class(
                        unreal.StaticMeshActor, source.get_actor_location()
                    )
                    if not actor:
                        raise RuntimeError("Could not duplicate managed actor")
                    created.append(actor)
                    actor.set_editor_property("tags", list(source.tags))
                    actor.set_actor_label(source.get_actor_label() + " copy")
                    actor.static_mesh_component.set_static_mesh(
                        source.static_mesh_component.static_mesh
                    )
                    for i in range(source.static_mesh_component.get_num_materials()):
                        actor.static_mesh_component.set_material(
                            i, source.static_mesh_component.get_material(i)
                        )
                actor.modify()
                actor.set_actor_location(
                    unreal.Vector(*(v * 100 for v in row["position"])), False, False
                )
                actor.set_actor_rotation(
                    unreal.Rotator(
                        pitch=row["rotation"][1], yaw=row["rotation"][2], roll=row["rotation"][0]
                    ),
                    False,
                )
                actor.set_actor_scale3d(unreal.Vector(*row["scale"]))
                if request.get("snap_to_surface"):
                    from .diagnostics import ground

                    ground(actor, required=False)
                changed.append(actor)
            snapshot["created_ids"] = [actions.guid(a) for a in created]
            write_json(path, snapshot)
    except Exception:
        for actor in created:
            actions.actors().destroy_actor(actor)
        # The normal action error handler restores the saved original instances.
        raise
    return {
        "scene": actions.scene(),
        "objects": [actions.describe(a) for a in changed],
        "created_ids": snapshot["created_ids"],
        "changed": len(changed),
        "undo_id": request["request_id"],
    }
