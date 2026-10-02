"""Disposable native UE fixture; no helper C++ module is installed in this project."""

import json
import time
from pathlib import Path

from prompt_to_scene_unreal.development import level_material

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.new_level("/Game/DevelopmentSmoke_" + str(int(time.time())))
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
floor = actors.spawn_actor_from_object(
    unreal.load_asset("/Engine/BasicShapes/Cube.Cube"), unreal.Vector(1000, 1000, -10)
)
floor.set_actor_scale3d(unreal.Vector(80, 80, 0.2))
floor.static_mesh_component.set_material(0, level_material("floor"))
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "development-ready").write_text("ready")
deadline = time.monotonic() + 1500


def tick(_delta):
    try:
        if time.monotonic() > deadline:
            raise RuntimeError("Development fixture timeout")
        if levels.is_in_play_in_editor():
            return
        path = root / "development-command.json"
        if not path.is_file():
            return
        c = json.loads(path.read_text())
        path.unlink()
        if c["operation"] == "stop":
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            return
        if c["operation"] == "material":
            from prompt_to_scene_unreal.development import level_material

            level_material("trim")
        if c["operation"] == "block":
            from prompt_to_scene_unreal import actions

            plan = next(
                row
                for row in (json.loads(p.read_text()) for p in (root / "levels").glob("*.json"))
                if row["scene"] == actions.scene()
            )
            from prompt_to_scene_unreal.development import vec

            cube = actors.spawn_actor_from_object(
                unreal.load_asset("/Engine/BasicShapes/Cube.Cube"),
                vec(plan["checkpoints"][0]["position"]) + unreal.Vector(0, 0, 90),
            )
            cube.set_actor_scale3d(unreal.Vector(1, 1, 1.8))
            cube.set_actor_label("PTS Blocker")
        if c["operation"] == "unblock":
            for actor in actors.get_all_level_actors():
                if actor.get_actor_label() == "PTS Blocker":
                    actors.destroy_actor(actor)
        if c["operation"] == "check_preserved":
            from prompt_to_scene_unreal import actions

            actor = actions.targets({"scope": "asset", "asset_id": c["asset_id"]})[0]
            assert actor.get_editor_property("InteractionRange") == 350
            assert any("PTS.Socket:handle" in map(str, a.tags) for a in actor.get_attached_actors())
            assert any(
                m.get_path_name().startswith("/Game/PromptToScene/LevelMaterials/M_trim")
                for m in actor.static_mesh_component.get_materials()
            )
        if c["operation"] == "legacy_bindings":
            from prompt_to_scene_unreal import protection

            mesh = protection.mesh_for(c["asset_id"])
            unreal.EditorAssetLibrary.remove_metadata_tag(mesh, "PromptToScene.SlotNames")
            unreal.EditorAssetLibrary.remove_metadata_tag(mesh, "PromptToScene.GeneratedMaterials")
        if c["operation"] == "check_restored":
            from prompt_to_scene_unreal import presentation

            assert not presentation.owned()
        (root / "development-command-done").write_text("done")
    except Exception as error:
        (root / "development-error.txt").write_text(str(error))
        unreal.log_error(str(error))
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)


handle = unreal.register_slate_post_tick_callback(tick)
