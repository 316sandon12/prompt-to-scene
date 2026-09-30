"""Editor-owned selection, instance edits, undo snapshots and viewport screenshots."""

import json
import math
import re
import time

import unreal

from .protocol import write_json

_captures = {}


def actors():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def guid(actor):
    return actor.get_editor_property("actor_guid").to_string()


def asset_id(actor):
    return next((str(t)[10:] for t in actor.tags if str(t).startswith("PTS.Asset:")), "")


def vector(value):
    return [value.x, value.y, value.z]


def describe(actor):
    component = actor.static_mesh_component
    rotation = actor.get_actor_rotation()
    center, extent = actor.get_actor_bounds(False)
    return {
        "bounds_min": [(getattr(center, k) - getattr(extent, k)) / 100 for k in ("x", "y", "z")],
        "bounds_max": [(getattr(center, k) + getattr(extent, k)) / 100 for k in ("x", "y", "z")],
        "id": guid(actor),
        "name": actor.get_actor_label(),
        "asset_id": asset_id(actor),
        "position": [v / 100 for v in vector(actor.get_actor_location())],
        "rotation": [rotation.roll, rotation.pitch, rotation.yaw],
        "scale": vector(actor.get_actor_scale3d()),
        "materials": [
            component.get_material(i).get_path_name() if component.get_material(i) else ""
            for i in range(component.get_num_materials())
        ],
    }


def scene():
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).get_current_level()
    return level.get_outer().get_path_name() if level else ""


def targets(request):
    candidates = (
        actors().get_selected_level_actors()
        if request.get("scope") != "asset"
        else actors().get_all_level_actors()
    )
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).get_current_level()
    return [
        a
        for a in candidates
        if isinstance(a, unreal.StaticMeshActor)
        and a.get_level() == level
        and asset_id(a)
        and (not request.get("asset_id") or asset_id(a) == request["asset_id"])
    ]


def focus(selected):
    actors().set_selected_level_actors(selected)
    bounds = [a.get_actor_bounds(False) for a in selected]
    low = [min(getattr(c, k) - getattr(e, k) for c, e in bounds) for k in ("x", "y", "z")]
    high = [max(getattr(c, k) + getattr(e, k) for c, e in bounds) for k in ("x", "y", "z")]
    center = unreal.Vector(*((a + b) / 2 for a, b in zip(low, high)))
    extent = unreal.Vector(*((b - a) / 2 for a, b in zip(low, high)))
    distance = max(extent.x, extent.y, extent.z, 30) * 4
    location = center + unreal.Vector(distance, -distance, distance * 0.7)
    rotation = unreal.MathLibrary.find_look_at_rotation(location, center)
    unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
        location, rotation
    )


def auto_position(mesh):
    camera = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem
    ).get_level_viewport_camera_info()
    location, rotation = camera if camera else (unreal.Vector(0, -400, 200), unreal.Rotator())
    direction = unreal.MathLibrary.get_forward_vector(rotation)
    position = location + direction * 400
    # Ground fallback uses Z=0; visible scene surfaces can override it through a trace.
    position.z = 0
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    try:
        result = unreal.SystemLibrary.line_trace_single(
            world,
            position + unreal.Vector(0, 0, 100000),
            position - unreal.Vector(0, 0, 100000),
            unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
            False,
            [],
            unreal.DrawDebugTrace.NONE,
            True,
        )
        if result:
            position = result.to_tuple()[4]
    except Exception as error:
        unreal.log_warning("[Prompt-to-Scene] Ground trace unavailable: " + str(error))
    bounds = mesh.get_bounds()
    position.z -= bounds.origin.z - bounds.box_extent.z
    return position


def validate(request, filename):
    if request.get("schema_version") != 1 or request.get("target_engine") != "unreal":
        raise ValueError("Unsupported editor action")
    if not re.fullmatch(r"[a-f0-9]{32}", filename) or request.get("request_id") != filename:
        raise ValueError("Invalid action ID")
    if request.get("scope") not in {"selected", "asset"}:
        raise ValueError("Invalid scope")
    if request.get("scope") == "asset" and not re.fullmatch(
        r"[a-z][a-z0-9_-]{0,63}", request.get("asset_id", "")
    ):
        raise ValueError("Choose an asset")
    for key in ("move", "rotate", "scale", "color"):
        if key in request:
            values = request[key]
            if (
                not isinstance(values, list)
                or len(values) != 3
                or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values)
            ):
                raise ValueError("Invalid " + key)
            if key == "scale" and any(v <= 0 or v > 100 for v in values):
                raise ValueError("Invalid scale")
            if key == "color" and any(not 0 <= v <= 1 for v in values):
                raise ValueError("Invalid color")


def execute(request, root):
    operation = request["operation"]
    revision = request["request_id"]
    selected = targets(request)
    if operation == "inspect":
        from . import layout

        visible = layout.context()
        return {
            "context": [describe(a) for a in visible],
            "selected_context": [
                describe(a) for a in actors().get_selected_level_actors() if a in visible
            ],
            "scene": scene(),
            "selected": [describe(a) for a in targets({"scope": "selected"})],
            "assets": [describe(a) for a in targets({"scope": "asset"})],
        }
    if operation == "arrange":
        from .layout import arrange

        return arrange(request, root)
    if operation == "undo":
        undo_id = request.get("undo_id", "")
        if not re.fullmatch(r"[a-f0-9]{32}", undo_id):
            raise ValueError("Invalid undo ID")
        snapshot = json.loads((root / "edits" / (undo_id + ".json")).read_text())
        if snapshot["scene"] != scene():
            raise ValueError("Open the level where this edit was made")
        objects = {
            guid(a): a
            for a in actors().get_all_level_actors()
            if isinstance(a, unreal.StaticMeshActor)
        }
        if any(row["id"] not in objects for row in snapshot["objects"]):
            raise ValueError("An edited actor is no longer loaded")
        with unreal.ScopedEditorTransaction("Prompt-to-Scene: restore instance edit"):
            for row in snapshot["objects"]:
                actor = objects[row["id"]]
                actor.modify()
                actor.set_actor_location(
                    unreal.Vector(*(v * 100 for v in row["position"])), False, False
                )
                actor.set_actor_rotation(
                    unreal.Rotator(row["rotation"][1], row["rotation"][2], row["rotation"][0]),
                    False,
                )
                actor.set_actor_scale3d(unreal.Vector(*row["scale"]))
                actor.static_mesh_component.modify()
                for i, path in enumerate(row["materials"]):
                    actor.static_mesh_component.set_material(
                        i, unreal.load_asset(path) if path else None
                    )
        for created_id in snapshot.get("created_ids", []):
            if created_id in objects:
                actors().destroy_actor(objects[created_id])
        return {"restored_edit": undo_id, "objects": snapshot["objects"]}
    if not selected:
        raise ValueError("Select a Prompt-to-Scene prop in this level, or choose an asset scope")
    if operation == "focus":
        focus(selected)
        return {"objects": [describe(a) for a in selected]}
    if operation == "preview":
        focus(selected)
        path = root / "previews" / (revision + ".png")
        path.parent.mkdir(exist_ok=True)
        task = unreal.AutomationLibrary.take_high_res_screenshot(1024, 768, str(path), delay=0.3)
        _captures[revision] = (path, time.monotonic(), task)
        return None
    if operation not in {"transform", "tint"}:
        raise ValueError("Unknown editor action")
    snapshot = {"scene": scene(), "objects": [describe(a) for a in selected]}
    write_json(root / "edits" / (revision + ".json"), snapshot)
    changed = 0
    with unreal.ScopedEditorTransaction("Prompt-to-Scene: " + operation):
        for actor in selected:
            actor.modify()
            if operation == "transform":
                if "move" in request:
                    actor.set_actor_location(
                        actor.get_actor_location()
                        + unreal.Vector(*(v * 100 for v in request["move"])),
                        False,
                        False,
                    )
                if "rotate" in request:
                    old = actor.get_actor_rotation()
                    r = request["rotate"]
                    actor.set_actor_rotation(
                        unreal.Rotator(old.pitch + r[1], old.yaw + r[2], old.roll + r[0]), False
                    )
                if "scale" in request:
                    old = vector(actor.get_actor_scale3d())
                    actor.set_actor_scale3d(
                        unreal.Vector(*(a * b for a, b in zip(old, request["scale"])))
                    )
                changed += 1
            else:
                component = actor.static_mesh_component
                component.modify()
                for i in range(component.get_num_materials()):
                    old = component.get_material(i)
                    if not old:
                        continue
                    parent = old
                    while isinstance(parent, unreal.MaterialInstanceConstant):
                        parent = parent.get_editor_property("parent")
                    original = unreal.EditorAssetLibrary.get_metadata_tag(
                        parent, "PromptToScene.MaterialName"
                    )
                    if request.get("material") and request["material"] != original:
                        continue
                    name = "MI_" + revision + "_" + str(i) + "_" + guid(actor).replace("-", "")
                    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                        name,
                        "/Game/PromptToScene/Overrides",
                        unreal.MaterialInstanceConstant,
                        unreal.MaterialInstanceConstantFactoryNew(),
                    )
                    unreal.MaterialEditingLibrary.set_material_instance_parent(material, old)
                    library = unreal.MaterialEditingLibrary
                    library.update_material_instance(material)
                    if "PTS_Color" not in map(str, library.get_vector_parameter_names(old)):
                        raise ValueError("Material needs a v0.3 import before instance tinting")
                    # UE 5.7's setter always returns false (engine implementation bug).
                    # Confirm the stored parameter instead of trusting that return value.
                    library.set_material_instance_vector_parameter_value(
                        material, "PTS_Color", unreal.LinearColor(*request["color"], 1)
                    )
                    actual = library.get_material_instance_vector_parameter_value(
                        material, "PTS_Color"
                    )
                    if any(
                        abs(a - b) > 0.0001
                        for a, b in zip((actual.r, actual.g, actual.b), request["color"])
                    ):
                        raise ValueError("Instance color verification failed")
                    library.update_material_instance(material)
                    unreal.EditorAssetLibrary.save_loaded_asset(material, False)
                    component.set_material(i, material)
                    changed += 1
    if not changed:
        raise ValueError("No matching material was found")
    return {"undo_id": revision, "objects": [describe(a) for a in selected], "changed": changed}


def process(root):
    for revision, (path, started, task) in list(_captures.items()):
        if path.is_file() and path.stat().st_size > 8:
            write_json(
                root / "action-receipts" / (revision + ".json"),
                {
                    "status": "completed",
                    "request_id": revision,
                    "preview": "previews/" + path.name,
                    "engine": "unreal",
                },
            )
            del _captures[revision]
        elif time.monotonic() - started > 30:
            write_json(
                root / "action-receipts" / (revision + ".json"),
                {
                    "status": "error",
                    "request_id": revision,
                    "error": "Screenshot timed out; open a visible level viewport and retry",
                },
            )
            del _captures[revision]
    for path in sorted((root / "actions").glob("*.json")):
        receipt = {"status": "error", "request_id": path.stem, "engine": "unreal"}
        try:
            if path.is_symlink() or path.stat().st_size > 100000:
                raise ValueError("Invalid action file")
            request = json.loads(path.read_text())
            validate(request, path.stem)
            if (root / "cancel" / path.stem).exists():
                receipt["status"] = "cancelled"
            else:
                result = execute(request, root)
                if result is None:
                    path.unlink()
                    continue
                receipt.update(result, status="completed")
        except Exception as error:
            receipt["error"] = str(error)
            snapshot = root / "edits" / (path.stem + ".json")
            if snapshot.exists():
                try:
                    execute(
                        {"operation": "undo", "request_id": path.stem, "undo_id": path.stem}, root
                    )
                except Exception as restore_error:
                    receipt["restore_error"] = str(restore_error)
        write_json(root / "action-receipts" / path.name, receipt)
        path.unlink()
