"""Native production fixture containing only the shipped engine plugin."""

import json
import os
import time
from pathlib import Path

from prompt_to_scene_unreal import actions, protection

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if os.environ.get("PTS_PRODUCTION_EXISTING"):
    assert levels.load_level("/Game/ProductionSmoke")
else:
    assert levels.new_level("/Game/ProductionSmoke")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if os.environ.get("PTS_PRODUCTION_EXISTING"):
    for actor in actors.get_all_level_actors():
        if isinstance(actor, unreal.CameraActor):
            actors.destroy_actor(actor)
    subject = actors.spawn_actor_from_object(protection.mesh_for("material_probe"), unreal.Vector())
    subject.tags = [unreal.Name("PTS.Asset:material_probe")]
light = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 500))
light.set_actor_rotation(unreal.Rotator(pitch=-45, yaw=-35), False)
light.light_component.set_editor_property("intensity", 5)
sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 400))
sky.light_component.set_editor_property("intensity", 1)
camera = actors.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(700, -700, 800))
camera.tags = [unreal.Name("PTS.GameCamera")]
camera.set_actor_rotation(
    unreal.MathLibrary.find_look_at_rotation(camera.get_actor_location(), unreal.Vector(0, 0, 100)),
    False,
)
levels.save_current_level()
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "production-ready").write_text("ready")
stopping = None


def tick(_delta):
    global stopping
    if stopping is not None:
        if time.monotonic() >= stopping:
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.SystemLibrary.quit_editor()
        return
    if levels.is_in_play_in_editor():
        return
    path = root / "production-command.json"
    if not path.exists():
        return
    try:
        command = json.loads(path.read_text())
        path.unlink()
        operation = command["operation"]
        if operation == "stop":
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            stopping = time.monotonic() + 2
            return
        actor = actions.targets({"scope": "asset", "asset_id": command["asset_id"]})[0]
        if operation == "lens":
            camera.camera_component.field_of_view = 90
            camera.camera_component.aspect_ratio = 4 / 3
        if operation == "camera":
            center, extents = actor.get_actor_bounds(False)
            size = max(extents.length(), 100)
            camera.set_actor_location(center + unreal.Vector(1.4, -2.7, 1.1) * size, False, False)
            camera.set_actor_rotation(
                unreal.MathLibrary.find_look_at_rotation(camera.get_actor_location(), center), False
            )
        if operation == "materials":
            mesh = protection.mesh_for(command["asset_id"])
            materials = {
                unreal.EditorAssetLibrary.get_metadata_tag(
                    m.material_interface, "PromptToScene.MaterialName"
                ): m.material_interface
                for m in mesh.static_materials
            }
            assert materials["ProbeMask"].blend_mode == unreal.BlendMode.BLEND_MASKED
            assert materials["ProbeMask"].get_editor_property("two_sided")
            assert materials["ProbeBlend"].blend_mode == unreal.BlendMode.BLEND_TRANSLUCENT
            lib = unreal.MaterialEditingLibrary
            assert (
                lib.get_material_default_vector_parameter_value(
                    materials["ProbeEmission"], "PTS_Emission"
                ).g
                > 1
            )
            assert (
                abs(
                    lib.get_material_default_scalar_parameter_value(
                        materials["ProbeBlend"], "PTS_Opacity"
                    )
                    - 0.3
                )
                < 0.01
            )
        if operation == "hooks":
            assert actor.get_editor_property("GameEventId") == "ore_mined"
            assert actor.get_editor_property("UsesRequired") == 3
            assert actor.get_editor_property("DepletedMesh")
        (root / "production-command-done").write_text("done")
    except Exception as error:
        (root / "production-error.txt").write_text(str(error))
        unreal.log_error(str(error))


handle = unreal.register_slate_post_tick_callback(tick)
