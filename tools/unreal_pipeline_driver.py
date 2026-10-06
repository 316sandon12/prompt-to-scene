"""Disposable full-editor fixture for the native workshop and material adaptation."""

import json
import time
from pathlib import Path

from prompt_to_scene_unreal import adaptation, panel

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.new_level("/Game/PipelineSmoke/Level_" + str(int(time.time())))
folder = "/Game/PipelineSmoke"
unreal.EditorAssetLibrary.make_directory(folder)
library = unreal.MaterialEditingLibrary


def material(name, color, roughness, tiling):
    path = folder + "/" + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.Material, unreal.MaterialFactoryNew()
    )
    for field, value, prop in [
        ("BaseColor", color, unreal.MaterialProperty.MP_BASE_COLOR),
        ("Roughness", roughness, unreal.MaterialProperty.MP_ROUGHNESS),
        ("UVScale", tiling, unreal.MaterialProperty.MP_SPECULAR),
    ]:
        vector = isinstance(value, list)
        n = library.create_material_expression(
            m,
            unreal.MaterialExpressionVectorParameter
            if vector
            else unreal.MaterialExpressionScalarParameter,
            -200,
            0,
        )
        n.set_editor_property("parameter_name", field)
        n.set_editor_property("default_value", unreal.LinearColor(*value) if vector else value)
        assert library.connect_material_property(n, "", prop)
    library.recompile_material(m)
    assert unreal.EditorAssetLibrary.save_loaded_asset(m, only_if_is_dirty=False)
    return m


reference = material("Reference", [0.8, 0.25, 0.12, 1], 0.75, 2.0)
for index in range(2):
    path = folder + "/Prop" + str(index)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    mesh = unreal.EditorAssetLibrary.duplicate_asset("/Engine/BasicShapes/Cube", path)
    mesh.set_material(0, material("Original" + str(index), [0, 0, 1, 1], 0.2, 1.0))
    assert unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
panel.open_panel()
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "pipeline-ready").write_text("ready")
stopping_at = None


def tick(_delta):
    global stopping_at
    if stopping_at is not None:
        if time.monotonic() >= stopping_at:
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.SystemLibrary.quit_editor()
        return
    path = root / "pipeline-command.json"
    if not path.is_file():
        return
    try:
        c = json.loads(path.read_text())
        path.unlink()
        if c["operation"] == "stop":
            levels.save_current_level()
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            # Let the engine retire its async script notification before ICU/Slate
            # shutdown. Quitting in the same tick retains that notification.
            stopping_at = time.monotonic() + 2
            return
        if c["operation"] in {"verify_apply", "verify_undo"}:
            first = adaptation.material_values(unreal.load_asset(folder + "/Prop0").get_material(0))
            second = adaptation.material_values(
                unreal.load_asset(folder + "/Prop1").get_material(0)
            )
            assert second["color"]["value"] == [0, 0, 1, 1], second
            if c["operation"] == "verify_apply":
                assert abs(first["color"]["value"][0] - 0.8) < 0.001, first
                assert first["roughness"]["value"] == 0.75 and first["texture_scale"]["value"] == 2
            else:
                assert first["color"]["value"] == [0, 0, 1, 1], first
        (root / "pipeline-command-done").write_text("done")
    except Exception as error:
        (root / "pipeline-error.txt").write_text(str(error))


handle = unreal.register_slate_post_tick_callback(tick)
