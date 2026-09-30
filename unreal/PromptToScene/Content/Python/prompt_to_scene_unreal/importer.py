"""Native FBX -> one StaticMesh asset and persistent StaticMeshActor instances."""

import unreal

from .materials import build_material


def is_commandlet():
    return "-run=" in unreal.SystemLibrary.get_command_line().lower()


def is_playing():
    # LevelEditorSubsystem's PIE query dereferences a Slate editor in UE 5.7.
    # Commandlets have no Slate editor and cannot enter PIE.
    return (
        not is_commandlet()
        and unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()
    )


def import_asset(request, source):
    if is_commandlet() or "-nullrhi" in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError("Scene placement requires the full Unreal Editor with graphics enabled")
    static_meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if static_meshes is None:
        raise RuntimeError("Static mesh editing is unavailable; run in the full Unreal Editor")
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    level = levels.get_current_level()
    if level is None or is_playing():
        raise RuntimeError("Open an editor level and leave Play In Editor before importing")
    asset_id = request["asset_id"]
    target = "/Game/PromptToScene/" + asset_id
    unreal.EditorAssetLibrary.make_directory(target)
    task = unreal.AssetImportTask()
    task.filename = str(source / "model.fbx")
    task.destination_path = target
    task.destination_name = "SM_" + asset_id
    # An explicit factory selects FBX instead of silently switching to Interchange
    # (which uses a different options pipeline in UE 5.7). No global CVar changes.
    task.factory = unreal.FbxFactory()
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = False
    options = unreal.FbxImportUI()
    options.automated_import_should_detect_type = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    options.import_mesh = True
    options.import_materials = False
    options.import_textures = False
    options.import_animations = False
    options.import_as_skeletal = False
    data = options.static_mesh_import_data
    for name, value in {
        "combine_meshes": True,
        "convert_scene": True,
        "convert_scene_unit": True,
        "force_front_x_axis": True,
        "transform_vertex_to_absolute": True,
        "auto_generate_collision": False,
        "import_uniform_scale": 1.0,
    }.items():
        data.set_editor_property(name, value)
    task.options = options
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    meshes = [obj for obj in task.get_objects() if isinstance(obj, unreal.StaticMesh)]
    if len(meshes) != 1:
        raise RuntimeError("FBX import did not produce one combined StaticMesh")
    mesh = meshes[0]
    if mesh.get_path_name() != target + "/SM_" + asset_id + ".SM_" + asset_id:
        raise RuntimeError("Importer changed the managed mesh path")
    materials = {m["fbx_name"]: build_material(m, source, target) for m in request["materials"]}
    slots = mesh.get_editor_property("static_materials")
    if not slots:
        raise RuntimeError("FBX has no material slots")
    for index, slot in enumerate(slots):
        name = str(slot.get_editor_property("imported_material_slot_name"))
        if name not in materials:
            raise RuntimeError("Unmapped FBX material slot: " + name)
        mesh.set_material(index, materials[name])
    if not static_meshes.remove_collisions(mesh):
        raise RuntimeError("Could not clear generated collision")
    if request["collider"]:
        if static_meshes.add_simple_collisions(mesh, unreal.ScriptCollisionShapeType.BOX) < 0:
            raise RuntimeError("Could not create box collision")
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "PromptToScene.AssetId", asset_id)
    unreal.EditorAssetLibrary.set_metadata_tag(
        mesh, "PromptToScene.Revision", request["request_id"]
    )
    if not unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False):
        raise RuntimeError("Could not save mesh")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    tag = "PTS.Asset:" + asset_id
    instances = [
        actor
        for actor in actors.get_all_level_actors()
        if actor.get_level() == level and tag in [str(t) for t in actor.tags]
    ]
    with unreal.ScopedEditorTransaction("Prompt-to-Scene: place/update " + asset_id):
        if not instances:
            actor = actors.spawn_actor_from_class(
                unreal.StaticMeshActor, unreal.Vector(*(v * 100 for v in request["position"]))
            )
            if actor is None:
                raise RuntimeError("Could not spawn StaticMeshActor")
            actor.set_actor_label(asset_id)
            instances = [actor]
        for actor in instances:
            if not isinstance(actor, unreal.StaticMeshActor):
                raise RuntimeError("An asset identity is attached to a non-StaticMeshActor")
            actor.modify()
            component = actor.static_mesh_component
            component.modify()
            component.set_static_mesh(mesh)
            tags = [str(t) for t in actor.tags if not str(t).startswith("PTS.Revision:")]
            if tag not in tags:
                tags.append(tag)
            tags.append("PTS.Revision:" + request["request_id"])
            actor.set_editor_property("tags", [unreal.Name(t) for t in tags])
    # Asset packages are saved; the user's level stays dirty until they save it.
    extent = mesh.get_bounds().box_extent
    triangles = mesh.get_num_triangles(0)
    if triangles <= 0:
        raise RuntimeError("Imported mesh has no triangles")
    return {
        "status": "imported",
        "engine": "unreal",
        "asset_id": asset_id,
        "request_id": request["request_id"],
        "asset_path": mesh.get_path_name(),
        "actor_guid": instances[0].get_editor_property("actor_guid").to_string(),
        "actor_guids": [a.get_editor_property("actor_guid").to_string() for a in instances],
        "scene": level.get_outer().get_path_name(),
        "material_names": [m["name"] for m in request["materials"]],
        "material_paths": [m.get_path_name() for m in materials.values()],
        "mesh_count": 1,
        "triangles": triangles,
        "bounds_size": [extent.x / 50, extent.y / 50, extent.z / 50],
        "bounds_unit": "meters",
        "scene_instances": len(instances),
        "collision_shapes": static_meshes.get_simple_collision_count(mesh),
    }
