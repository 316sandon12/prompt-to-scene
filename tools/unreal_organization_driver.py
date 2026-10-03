"""Disposable organization fixture, reused after a real editor restart."""

import json
from pathlib import Path

from prompt_to_scene_unreal.protocol import write_json

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
config = json.loads((root / "organization-fixture.json").read_text())
folder, destination = config["folder"], config["destination"]
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
scene = folder + "_Reference"

if config["fresh"]:
    assert levels.new_level(scene)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(root / "organization-texture.png"))
    task.set_editor_property("destination_path", folder + "/PackA")
    task.set_editor_property("destination_name", "oak_albedo")
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    tools.import_asset_tasks([task])
    texture = unreal.load_asset(folder + "/PackA/oak_albedo")
    material = tools.create_asset(
        "oak", folder + "/PackA", unreal.Material, unreal.MaterialFactoryNew()
    )
    sample = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSample
    )
    sample.set_editor_property("texture", texture)
    unreal.MaterialEditingLibrary.connect_material_property(
        sample, "RGB", unreal.MaterialProperty.MP_BASE_COLOR
    )
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    unreal.EditorAssetLibrary.duplicate_asset(material.get_path_name(), folder + "/PackB/oak")
    unreal.EditorAssetLibrary.duplicate_asset(
        material.get_path_name(), destination + "/Materials/M_Oak"
    )
    unreal.EditorAssetLibrary.duplicate_asset(
        material.get_path_name(), folder + "/Resources/runtime"
    )
    mesh = unreal.EditorAssetLibrary.duplicate_asset(
        "/Engine/BasicShapes/Cube.Cube", folder + "/PackA/cube_shape"
    )
    mesh.set_material(0, material)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", unreal.StaticMeshActor)
    blueprint = tools.create_asset("my_blueprint", folder + "/PackA", unreal.Blueprint, factory)
    default = unreal.get_default_object(blueprint.generated_class())
    default.static_mesh_component.set_static_mesh(mesh)
    unreal.EditorAssetLibrary.save_loaded_asset(blueprint)
    actor = actors.spawn_actor_from_class(blueprint.generated_class(), unreal.Vector())
    actor.set_actor_label("organization reference")
    actor.static_mesh_component.set_static_mesh(mesh)
    for index in range(9):
        unreal.EditorAssetLibrary.duplicate_asset(
            material.get_path_name(), folder + "/extra_" + str(index)
        )
    assert unreal.EditorAssetLibrary.save_directory(folder, only_if_is_dirty=False, recursive=True)
    assert unreal.EditorAssetLibrary.save_directory(
        destination, only_if_is_dirty=False, recursive=True
    )
    assert levels.save_current_level()
    write_json(
        root / "organization-fixture-assets.json",
        dict(
            material=folder + "/PackA/oak",
            texture=folder + "/PackA/oak_albedo",
            mesh=folder + "/PackA/cube_shape",
            prefab=folder + "/PackA/my_blueprint",
            scene=scene,
        ),
    )
else:
    assert levels.load_level(scene)

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "organization-ready").write_text("ready")


def check(moved):
    actor = next(
        a for a in actors.get_all_level_actors() if a.get_actor_label() == "organization reference"
    )
    mesh = actor.static_mesh_component.static_mesh
    material = mesh.get_material(0)
    prefix = destination if moved else folder
    assert mesh.get_path_name().startswith(prefix + "/"), mesh.get_path_name()
    assert material.get_path_name().startswith(prefix + "/"), material.get_path_name()
    textures = unreal.MaterialEditingLibrary.get_used_textures(material)
    assert len(textures) == 1 and textures[0].get_path_name().startswith(prefix + "/"), textures
    assert actor.get_class().get_path_name().startswith(prefix + "/"), (
        actor.get_class().get_path_name()
    )
    assert unreal.EditorAssetLibrary.does_asset_exist(folder + "/Resources/runtime")
    protected = unreal.load_asset(folder + "/Resources/runtime")
    protected_textures = unreal.MaterialEditingLibrary.get_used_textures(protected)
    assert len(protected_textures) == 1 and protected_textures[0] == textures[0]


def tick(_delta):
    try:
        path = root / "organization-command.json"
        if not path.exists():
            return
        command = json.loads(path.read_text())
        path.unlink()
        operation = command["operation"]
        if operation == "cancel_after_moves":
            from prompt_to_scene_unreal import organization

            original_batch = organization.move_batch

            def cancel_after_batch(state, restoring=False):
                # Exercise real native rename and reverse rename; inject only the cancel signal.
                result = original_batch(state, restoring)
                if result and not restoring:
                    organization.move_batch = original_batch
                    cancel_path = root / "cancel" / state["request"]["request_id"]
                    cancel_path.parent.mkdir(exist_ok=True)
                    cancel_path.write_text("cancel after native moves")
                return result

            organization.move_batch = cancel_after_batch
        if operation == "check_moved":
            check(True)
        if operation == "check_restored":
            check(False)
        if operation == "mutate":
            material = unreal.load_asset(folder + "/PackA/oak")
            unreal.EditorAssetLibrary.set_metadata_tag(material, "FixtureChange", "yes")
            unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
        if operation == "block_undo":
            candidate = next(
                folder + "/extra_" + str(i)
                for i in range(9)
                if not unreal.EditorAssetLibrary.does_asset_exist(folder + "/extra_" + str(i))
            )
            package, name = candidate.rsplit("/", 1)
            blocker = tools.create_asset(
                name, package, unreal.Material, unreal.MaterialFactoryNew()
            )
            assert blocker
            unreal.EditorAssetLibrary.save_loaded_asset(blocker)
            (root / "organization-blocker.txt").write_text(candidate)
        if operation == "unblock_undo":
            assert unreal.EditorAssetLibrary.delete_asset(
                (root / "organization-blocker.txt").read_text()
            )
        if operation == "save_stop":
            assert levels.save_current_level()
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            return
        (root / "organization-command-done").write_text("done")
    except Exception as error:
        (root / "organization-error.txt").write_text(str(error))
        unreal.log_error(str(error))
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)


handle = unreal.register_slate_post_tick_callback(tick)
