"""Real editor fixture for workflow_smoke.py; never used in production projects."""

import json
import time
from pathlib import Path

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
assert (root / "initial-passed.json").exists()
assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level("/Game/Smoke")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
floor = actors.spawn_actor_from_object(
    unreal.load_asset("/Engine/BasicShapes/Cube.Cube"), unreal.Vector(0, 0, 50)
)
floor.set_actor_scale3d(unreal.Vector(30, 30, 1))
light = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 600))
light.set_actor_rotation(unreal.Rotator(pitch=-45, yaw=30), False)
light.light_component.set_editor_property("intensity", 5)
unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
    unreal.Vector(0, -400, 300), unreal.Rotator(pitch=-20, yaw=90)
)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "workflow-ready").write_text("ready")
deadline = time.monotonic() + 400


def finish(error=None):
    if error:
        (root / "workflow-error.txt").write_text(str(error))
    unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def tick(_delta):
    try:
        if time.monotonic() > deadline:
            raise RuntimeError("Workflow timeout")
        path = root / "workflow-command.json"
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
            if "PTS.Asset:" + command["asset_id"] in map(str, a.tags)
        ]
        if command["operation"] == "duplicate":
            actor = selected[0]
            actors.duplicate_actor(actor, offset=unreal.Vector(300, 0, 0))
            actors.set_selected_level_actors([actor])
        if command["operation"] == "check":
            for actor in selected:
                mesh = actor.static_mesh_component.static_mesh
                assert (
                    unreal.get_editor_subsystem(
                        unreal.StaticMeshEditorSubsystem
                    ).get_simple_collision_count(mesh)
                    == 0
                )
        (root / "workflow-command-done").write_text("done")
    except Exception as error:
        finish(error)


handle = unreal.register_slate_post_tick_callback(tick)
