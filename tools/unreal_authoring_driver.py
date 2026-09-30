"""Disposable real Unreal scene for the v0.4 authoring smoke test."""

import json
import time
from pathlib import Path

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.new_level("/Game/AuthoringSmoke_" + str(int(time.time())))
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
floor = actors.spawn_actor_from_object(
    unreal.load_asset("/Engine/BasicShapes/Cube.Cube"), unreal.Vector(0, 0, -50)
)
floor.set_actor_scale3d(unreal.Vector(100, 100, 1))
light = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 600))
light.set_actor_rotation(unreal.Rotator(pitch=-45, yaw=30), False)
light.light_component.set_editor_property("intensity", 5)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "authoring-ready").write_text("ready")
deadline = time.monotonic() + 1800


def finish(error=None):
    if error:
        (root / "authoring-error.txt").write_text(str(error))
    unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def tick(_delta):
    try:
        if time.monotonic() > deadline:
            raise RuntimeError("Authoring timeout")
        path = root / "authoring-command.json"
        if not path.exists():
            return
        command = json.loads(path.read_text())
        path.unlink()
        if command["operation"] == "stop":
            finish()
            return
        selected = [
            a
            for a in actors.get_all_level_actors()
            if any(
                (
                    str(t).startswith("PTS.Asset:" + command["asset_id"])
                    if command["operation"] == "select_all"
                    else str(t) == "PTS.Asset:" + command["asset_id"]
                )
                for t in a.tags
            )
        ]
        assert selected, "Fixture asset missing"
        if command["operation"] in {"select", "select_all"}:
            actors.set_selected_level_actors(selected)
        if command["operation"] == "check":
            for actor in selected:
                for material in actor.static_mesh_component.get_materials():
                    while isinstance(material, unreal.MaterialInstanceConstant):
                        material = material.get_editor_property("parent")
                    textures = unreal.MaterialEditingLibrary.get_used_textures(material)
                    assert len(textures) >= 4, "Baked PBR map missing in UE"
                    linear = [t for t in textures if not t.get_editor_property("srgb")]
                    assert len(linear) >= 3, "PBR data texture color spaces incorrect"
        if command["operation"] == "capture_material":
            material = next(
                m
                for m in selected[0].static_mesh_component.get_materials()
                if unreal.EditorAssetLibrary.get_metadata_tag(m, "PromptToScene.MaterialName")
                == "Wood"
            )
            path = material.get_path_name().split(".")[0]
            file = Path(unreal.Paths.project_content_dir()) / (
                path.removeprefix("/Game/") + ".uasset"
            )
            (root / "authoring-material.json").write_text(
                json.dumps({"path": path, "file": str(file.resolve())})
            )
        if command["operation"] == "check_reuse":
            reference = json.loads((root / "authoring-material.json").read_text())
            assert any(
                m.get_path_name().split(".")[0] == reference["path"]
                for m in selected[0].static_mesh_component.get_materials()
            ), "Existing material was not reused"
        (root / "authoring-command-done").write_text("done")
    except Exception as error:
        finish(error)


handle = unreal.register_slate_post_tick_callback(tick)
