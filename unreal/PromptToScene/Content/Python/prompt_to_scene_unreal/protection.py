"""Preserve native material assignments by canonical slot; never guess missing bindings."""

import json

import unreal

from . import actions, locations


def mesh_for(name):
    mesh = unreal.load_asset(locations.asset(name))
    if not isinstance(mesh, unreal.StaticMesh):
        raise ValueError("Import this managed mesh first: " + name)
    return mesh


def names(mesh):
    return json.loads(
        unreal.EditorAssetLibrary.get_metadata_tag(mesh, "PromptToScene.SlotNames") or "[]"
    )


def generated(mesh):
    return json.loads(
        unreal.EditorAssetLibrary.get_metadata_tag(mesh, "PromptToScene.GeneratedMaterials") or "[]"
    )


def components(asset_id):
    """Include moving meshes nested in an interactive Blueprint instance."""
    result = []
    for actor in actions.actors().get_all_level_actors():
        tags = set(map(str, actor.tags))
        if "PTS.Asset:" + asset_id in tags:
            result.append(actor.static_mesh_component)
        elif "PTS.Part:" + asset_id in tags:
            result.append(actor.get_editor_property("MovingMesh"))
    return result


def capture(mesh, asset_id, material_map=None):
    if not mesh:
        return {"mesh": [], "actors": []}
    slots, original = names(mesh), generated(mesh)
    if not slots:
        # Migrate pre-v0.7 meshes without erasing component overrides. Canonical FBX
        # IDs are stable; an unmapped legacy slot fails preflight instead of being lost.
        slots = [
            (material_map or {}).get(
                str(row.get_editor_property("imported_material_slot_name")),
                str(row.get_editor_property("imported_material_slot_name")),
            )
            for row in mesh.get_editor_property("static_materials")
        ]
    native = []
    for i, slot in enumerate(slots):
        material = mesh.get_material(i)
        custom = material and (
            material.get_path_name() != original[i]
            if i < len(original)
            else not material.get_path_name().startswith(f"/Game/PromptToScene/{asset_id}/M_")
        )
        if custom:
            native.append((slot, material))
    actors = []
    for component in components(asset_id):
        custom = [
            (slot, component.get_material(i))
            for i, slot in enumerate(slots)
            if component.get_material(i) and component.get_material(i) != mesh.get_material(i)
        ]
        actors.append((component, custom))
    return {"mesh": native, "actors": actors}


def conflicts(snapshot, candidate_slots):
    return sorted(
        {
            "Protected material slot is missing: " + name
            for row in [snapshot["mesh"], *(v for _, v in snapshot["actors"])]
            for name, material in row
            if name not in candidate_slots
        }
    )


def restore(mesh, snapshot):
    slots = names(mesh)
    for name, material in snapshot["mesh"]:
        mesh.set_material(slots.index(name), material)
    for component, bindings in snapshot["actors"]:
        component.set_editor_property("override_materials", [])
        for name, material in bindings:
            component.set_material(slots.index(name), material)


def execute(request, c):
    name = request["asset_id"]
    mesh = mesh_for(name)
    targets = actions.targets({"scope": "asset", "asset_id": name})
    snapshot = capture(mesh, name)
    if c["command"] == "update_review":
        missing = conflicts(snapshot, c.get("slots", []))
        return dict(
            command="update_review",
            candidate_request_id=c["candidate_request_id"],
            passed=not missing,
            conflicts=missing,
        )
    mode = c.get("mode")
    slots = names(mesh)
    planned = []
    for binding in c.get("bindings", []):
        if binding["slot"] not in slots:
            raise ValueError("Unknown canonical slot: " + binding["slot"])
        path = binding["material_path"]
        if not path.startswith("/Game/") or ".." in path:
            raise ValueError("Material must be inside /Game/")
        material = unreal.load_asset(path)
        if not isinstance(material, unreal.MaterialInterface):
            raise ValueError("Material not found: " + path)
        planned.append((slots.index(binding["slot"]), material))
    if mode not in {"inspect", "set", "clear"}:
        raise ValueError("Invalid protection mode")
    if mode != "inspect":
        with unreal.ScopedEditorTransaction("Prompt-to-Scene: protected settings"):
            mesh.modify()
            for index, material in planned:
                mesh.set_material(index, material)
                for component in components(name):
                    component.set_material(index, material)
            if mode == "clear":
                for i, path in enumerate(generated(mesh)):
                    mesh.set_material(i, unreal.load_asset(path))
                for component in components(name):
                    component.set_editor_property("override_materials", [])
                for actor in targets:
                    for child in actor.get_attached_actors():
                        if any(str(tag).startswith("PTS.Socket:") for tag in child.tags):
                            actions.actors().destroy_actor(child)
            for actor in targets:
                for row in c.get("sockets", []):
                    tag = "PTS.Socket:" + row["name"]
                    child = next(
                        (a for a in actor.get_attached_actors() if tag in map(str, a.tags)), None
                    )
                    if child is None:
                        child = actions.actors().spawn_actor_from_class(
                            unreal.TargetPoint, actor.get_actor_location()
                        )
                        child.set_actor_label("Socket_" + row["name"])
                        child.tags = [unreal.Name(tag)]
                        child.attach_to_actor(
                            actor,
                            "",
                            unreal.AttachmentRule.KEEP_RELATIVE,
                            unreal.AttachmentRule.KEEP_RELATIVE,
                            unreal.AttachmentRule.KEEP_RELATIVE,
                            False,
                        )
                    child.set_actor_relative_location(
                        unreal.Vector(*(v * 100 for v in row["position"])), False, False
                    )
                    x, y, z = row["rotation"]
                    child.set_actor_relative_rotation(
                        unreal.Rotator(roll=x, pitch=y, yaw=z), False, False
                    )
            unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    snapshot = capture(mesh, name)
    bindings = [
        dict(slot=slot, material_path=material.get_path_name())
        for row in [snapshot["mesh"], *(v for _, v in snapshot["actors"])]
        for slot, material in row
    ]
    sockets = [
        dict(
            name=str(tag)[11:],
            position=actions.vector(child.root_component.get_editor_property("relative_location")),
        )
        for actor in targets
        for child in actor.get_attached_actors()
        for tag in child.tags
        if str(tag).startswith("PTS.Socket:")
    ]
    for socket in sockets:
        socket["position"] = [v / 100 for v in socket["position"]]
    return dict(
        command="protection",
        bindings=bindings,
        sockets=sockets,
        message="Canonical material bindings, Actor settings and socket actors survive reimport.",
    )
