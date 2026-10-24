"""Native scene contract; run only inside tools/scene_context_smoke.py's disposable project."""

import json
import math
import traceback
from pathlib import Path

from prompt_to_scene_unreal import actions

import unreal

root = Path(unreal.Paths.project_dir()).resolve()
try:
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels.new_level("/Game/SceneContext")
    target = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 50))
    target.static_mesh_component.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Cube"))
    target.set_actor_scale3d(unreal.Vector(2, 1, 0.5))
    target.set_editor_property("tags", ["PTS.Asset:blockout"])
    camera = actors.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(-1000, 0, 100))
    camera.set_editor_property("tags", ["PTS.GameCamera"])
    component = camera.camera_component
    component.set_editor_property("aspect_ratio", 2.0)
    component.set_editor_property("field_of_view", 90.0)
    actors.set_selected_level_actors([target])
    result = actions.execute(
        {"operation": "inspect", "scope": "selected", "request_id": "a" * 32},
        root / ".prompt-to-scene",
    )
    measured = result["cameras"][0]
    assert measured["primary"] and measured["projection_supported"]
    assert measured["position"] == [-10, 0, 1]
    assert math.isclose(measured["vertical_fov"], math.degrees(2 * math.atan(0.5)))
    bounds = result["selected_context"][0]
    assert math.isclose(bounds["bounds_max"][0] - bounds["bounds_min"][0], 2)
    result.update(engine="unreal", status="completed", request_id="a" * 32)
    (root / "scene-context-result.json").write_text(json.dumps(result, indent=2))
    component.set_editor_property("projection_mode", unreal.CameraProjectionMode.ORTHOGRAPHIC)
    component.set_editor_property("ortho_width", 1000.0)
    measured = actions.cameras()[0]
    assert measured["orthographic"] and math.isclose(measured["ortho_height_m"], 5)
    (root / "native-pass.txt").write_text(
        "bounds metres, horizontal-to-vertical FOV, ortho, camera"
    )
    unreal.log("PTS SCENE CONTEXT PASS")
except Exception:
    (root / "native-error.txt").write_text(traceback.format_exc())
    raise
finally:
    unreal.SystemLibrary.quit_editor()
