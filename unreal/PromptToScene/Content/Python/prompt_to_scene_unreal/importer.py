"""Native FBX -> one StaticMesh asset and persistent StaticMeshActor instances."""

import json

import unreal

from . import locations
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
    warnings = []
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
    layout = locations.validate(request.get("native_layout") or locations.get(asset_id))
    target = layout["folder"]
    model = layout["model"]
    model_folder, _, model_name = (target + "/" + model).rpartition("/")
    unreal.EditorAssetLibrary.make_directory(target)
    expected_path = target + "/" + model + "." + model_name
    mesh = (
        unreal.load_asset(expected_path)
        if unreal.EditorAssetLibrary.does_asset_exist(expected_path)
        else None
    )
    from . import protection

    preserved = protection.capture(
        mesh, asset_id, {m["fbx_name"]: m["name"] for m in request["materials"]}
    )
    conflicts = protection.conflicts(preserved, [m["name"] for m in request["materials"]])
    if conflicts:
        raise ValueError(
            "; ".join(conflicts)
            + ". Review the candidate or explicitly remap/clear overrides first."
        )
    geometry_hash = request.get("geometry_hash", "")
    reuse_geometry = bool(
        geometry_hash
        and isinstance(mesh, unreal.StaticMesh)
        and unreal.EditorAssetLibrary.get_metadata_tag(mesh, "PromptToScene.GeometryHash")
        == geometry_hash
        and mesh.get_num_lods() == 1 + len(request.get("lods", []))
    )
    if not reuse_geometry:
        task = unreal.AssetImportTask()
        task.filename = str(source / "model.fbx")
        task.destination_path = model_folder
        task.destination_name = model_name
        # Keep initial import and repeated in-session reimports on the same FBX pipeline.
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
        setting = "Interchange.FeatureFlags.Import.FBX"
        enabled = unreal.SystemLibrary.get_console_variable_bool_value(setting)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        try:
            unreal.SystemLibrary.execute_console_command(world, setting + " 0")
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        finally:
            unreal.SystemLibrary.execute_console_command(
                world, setting + (" 1" if enabled else " 0")
            )
        meshes = [obj for obj in task.get_objects() if isinstance(obj, unreal.StaticMesh)]
        if len(meshes) != 1:
            raise RuntimeError("FBX import did not produce one combined StaticMesh")
        mesh = meshes[0]
        if mesh.get_path_name() != target + "/" + model + "." + model_name:
            raise RuntimeError("Importer changed the managed mesh path")
        if static_meshes.get_lod_count(mesh) > 1 and not static_meshes.remove_lods(mesh):
            raise RuntimeError("Could not replace the previous LOD chain")
        try:
            unreal.SystemLibrary.execute_console_command(world, setting + " 0")
            for index, lod in enumerate(request.get("lods", []), 1):
                if static_meshes.import_lod(mesh, index, str(source / lod["file"])) != index:
                    raise RuntimeError(f"Could not import LOD {index}")
                if mesh.get_num_triangles(index) != lod["triangles"]:
                    raise RuntimeError(f"LOD {index} geometry differs from the prepared mesh")
            if request.get("lods"):
                # The subsystem disables automatic sizing; that mesh property is not Python-exposed.
                if not static_meshes.set_lod_screen_sizes(
                    mesh, [1.0] + [lod["screen_height"] for lod in request["lods"]]
                ):
                    raise RuntimeError("Could not set LOD screen sizes")
        finally:
            unreal.SystemLibrary.execute_console_command(
                world, setting + (" 1" if enabled else " 0")
            )
    materials = {
        m["fbx_name"]: build_material(m, source, target, layout) for m in request["materials"]
    }
    slots = mesh.get_editor_property("static_materials")
    if not slots:
        raise RuntimeError("FBX has no material slots")
    for index, slot in enumerate(slots):
        name = str(slot.get_editor_property("imported_material_slot_name"))
        if name not in materials:
            raise RuntimeError("Unmapped FBX material slot: " + name)
        mesh.set_material(index, materials[name])
    canonical = {m["fbx_name"]: m["name"] for m in request["materials"]}
    unreal.EditorAssetLibrary.set_metadata_tag(
        mesh,
        "PromptToScene.SlotNames",
        json.dumps(
            [canonical[str(s.get_editor_property("imported_material_slot_name"))] for s in slots]
        ),
    )
    unreal.EditorAssetLibrary.set_metadata_tag(
        mesh,
        "PromptToScene.GeneratedMaterials",
        json.dumps([mesh.get_material(i).get_path_name() for i in range(len(slots))]),
    )
    protection.restore(mesh, preserved)
    if not reuse_geometry:
        if not static_meshes.remove_collisions(mesh):
            raise RuntimeError("Could not clear generated collision")
        if request["collider"]:
            if request.get("collision_mode") == "convex":
                # FBX with auto_generate_collision=False can leave section collision disabled.
                # Convex decomposition only considers enabled sections and otherwise returns
                # true with zero hulls. Enable them and verify the resulting native geometry.
                for section in range(mesh.get_num_sections(0)):
                    static_meshes.enable_section_collision(mesh, True, 0, section)
                static_meshes.set_convex_decomposition_collisions(mesh, 8, 32, 100000)
                if static_meshes.get_convex_collision_count(mesh) == 0:
                    # Some meshes/builds produce no V-HACD hull. A native 26-DOP is a
                    # usable convex approximation, and the receipt makes this fallback explicit.
                    if (
                        static_meshes.add_simple_collisions(
                            mesh, unreal.ScriptCollisionShapeType.NDOP26
                        )
                        < 0
                    ):
                        raise RuntimeError("Could not create native convex collision")
                    warnings.append(
                        "Convex decomposition produced no hulls; used one native 26-DOP hull"
                    )
                if static_meshes.get_convex_collision_count(mesh) == 0:
                    raise RuntimeError("Native collision creation produced no geometry")
            elif (
                request.get("collision_mode", "box") == "box"
                and static_meshes.add_simple_collisions(mesh, unreal.ScriptCollisionShapeType.BOX)
                < 0
            ):
                raise RuntimeError("Could not create box collision")
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "PromptToScene.GeometryHash", geometry_hash)
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
    part_tag = "PTS.Part:" + asset_id
    part_owners = [
        actor
        for actor in actors.get_all_level_actors()
        if actor.get_level() == level and part_tag in map(str, actor.tags)
    ]
    if not instances and part_owners:
        instances = part_owners
    created = not instances
    with unreal.ScopedEditorTransaction("Prompt-to-Scene: place/update " + asset_id):
        if not instances:
            from .actions import auto_position

            position = (
                auto_position(mesh)
                if request.get("auto_place")
                else unreal.Vector(*(v * 100 for v in request["position"]))
            )
            actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, position)
            if actor is None:
                raise RuntimeError("Could not spawn StaticMeshActor")
            actor.set_actor_label(asset_id)
            instances = [actor]
        for actor in instances:
            if not isinstance(actor, unreal.StaticMeshActor):
                raise RuntimeError("An asset identity is attached to a non-StaticMeshActor")
            actor.modify()
            component = (
                actor.get_editor_property("MovingMesh")
                if actor in part_owners
                else actor.static_mesh_component
            )
            component.modify()
            component.set_static_mesh(mesh)
            if actor in part_owners:
                continue
            tags = [str(t) for t in actor.tags if not str(t).startswith("PTS.Revision:")]
            if tag not in tags:
                tags.append(tag)
            tags.append("PTS.Revision:" + request["request_id"])
            actor.set_editor_property("tags", [unreal.Name(t) for t in tags])
    if created and request.get("auto_place"):
        from .actions import focus

        focus(instances)
    if any(any(str(t).startswith("PTS.Interaction:") for t in a.tags) for a in instances):
        from .development import enable_collision

        enable_collision(mesh)
    # Asset packages are saved; the user's level stays dirty until they save it.
    extent = mesh.get_bounds().box_extent
    triangles = mesh.get_num_triangles(0)
    # UE counts primitive shapes and convex hulls separately.
    collisions = static_meshes.get_simple_collision_count(
        mesh
    ) + static_meshes.get_convex_collision_count(mesh)
    if triangles <= 0:
        raise RuntimeError("Imported mesh has no triangles")
    return {
        "status": "imported",
        "geometry_reused": reuse_geometry,
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
        "lod_count": static_meshes.get_lod_count(mesh),
        "collision_count": collisions,
        "warnings": warnings,
        "scene_instances": len(instances),
        "collision_shapes": collisions,
    }
