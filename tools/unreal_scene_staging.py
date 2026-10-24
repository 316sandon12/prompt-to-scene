"""Real UE scene-camera pixels and reversible trial; dedicated disposable project only."""

import json
import time
import traceback
import uuid
from pathlib import Path

from prompt_to_scene_unreal import actions
from prompt_to_scene_unreal.protocol import write_json

import unreal

root = Path(unreal.Paths.project_dir()).resolve()
assert root == Path(__file__).resolve().parents[1] / ".local/scene-studio/unreal"
state_root = root / ".prompt-to-scene"
for key in ("a", "c", "d"):
    (state_root / "action-receipts" / (key * 32 + ".json")).unlink(missing_ok=True)
    (state_root / "previews" / (key * 32 + ".png")).unlink(missing_ok=True)
for name in ("native-pass.txt", "native-error.txt"):
    (root / name).unlink(missing_ok=True)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
started = time.monotonic()
stage = 0
handle = None
checking = False


def command(plan, key):
    return actions.execute(
        {
            "operation": "scene_stage",
            "scope": "selected",
            "request_id": key * 32,
            "scene_json": json.dumps(plan),
        },
        state_root,
    )


def finish(error=None):
    if error:
        (root / "native-error.txt").write_text(error)
        unreal.log_error(error)
    else:
        (root / "native-pass.txt").write_text(
            "native camera pixels; trial leaves source/placeholder unchanged; "
            "temporary actors cleaned; adoption; stale undo refused; undo restores original"
        )
    if handle:
        unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    global stage, plan, reference, checking
    if checking:
        return
    checking = True
    try:
        if time.monotonic() - started > 180:
            raise RuntimeError("Native screenshot check timed out")
        actions.process(state_root)
        key = ["a", "c", "d"][stage] if stage < 3 else None
        receipt = state_root / "action-receipts" / ((key or "0") * 32 + ".json")
        if not receipt.is_file():
            return
        result = json.loads(receipt.read_text())
        if result["status"] != "completed":
            raise RuntimeError(result)
        if stage == 0:
            reference = result
            assert any(m["object_id"] == actions.guid(target) for m in reference["materials"])
            (root / "scene-reference.json").write_text(json.dumps(reference, indent=2))
            src = actions.describe(source)
            plan = {
                "mode": "before",
                "plan_id": uuid.uuid4().hex,
                "scene": actions.scene(),
                "asset_id": "chest",
                "model_revision": "f" * 32,
                "target": actions.describe(target),
                "source": src,
                "camera_id": reference["reference_camera_id"],
                "camera": reference["cameras"][0],
                "replace_target": True,
                "placement": {
                    "source_id": src["id"],
                    "asset_id": "chest",
                    "expected": src,
                    "duplicate": False,
                    "position": [0, 0, 0.5],
                    "rotation": [0, 0, 0],
                    "scale": [1, 1, 1],
                    "bounds_min": [-0.5, -0.5, 0],
                    "bounds_max": [0.5, 0.5, 1],
                },
            }
            command(plan, "c")
            stage = 1
        elif stage == 1:
            plan["mode"] = "trial"
            command(plan, "d")
            stage = 2
        else:
            assert source.get_actor_location().y == 400
            assert (
                not source.is_temporarily_hidden_in_editor()
                and not target.is_temporarily_hidden_in_editor()
            )
            assert len(actors.get_all_level_actors()) == actor_count
            assert (state_root / "previews" / ("c" * 32 + ".png")).read_bytes() != (
                state_root / "previews" / ("d" * 32 + ".png")
            ).read_bytes()
            plan["mode"] = "adopt"
            command(plan, "e")
            assert source.get_actor_location().y == 0 and target.is_temporarily_hidden_in_editor()
            assert not target.get_actor_enable_collision()
            plan["mode"] = "undo"
            source.set_actor_location(unreal.Vector(100, 0, 50), False, False)
            refused = False
            try:
                command(plan, "1")
            except ValueError:
                refused = True
            assert refused
            source.set_actor_location(unreal.Vector(0, 0, 50), False, False)
            command(plan, "2")
            assert (
                source.get_actor_location().y == 400
                and not target.is_temporarily_hidden_in_editor()
            )
            assert target.get_actor_enable_collision()
            finish()
    except Exception:
        finish(traceback.format_exc())
    finally:
        checking = False


try:
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels.new_level("/Game/SceneStaging")
    mesh = unreal.load_asset("/Engine/BasicShapes/Cube")
    for i in range(48):
        distant = actors.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(100000 + i * 300, 0, 100000)
        )
        distant.static_mesh_component.set_static_mesh(mesh)
    target = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 50))
    target.static_mesh_component.set_static_mesh(mesh)
    target.set_actor_scale3d(unreal.Vector(2, 1, 1))
    source = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 400, 50))
    source.static_mesh_component.set_static_mesh(mesh)
    source.set_editor_property("tags", ["PTS.Asset:chest"])
    light = actors.spawn_actor_from_class(
        unreal.DirectionalLight, unreal.Vector(0, 0, 500), unreal.Rotator(pitch=-35, yaw=-25)
    )
    location = unreal.Vector(-600, 0, 300)
    camera = actors.spawn_actor_from_class(
        unreal.CameraActor,
        location,
        unreal.MathLibrary.find_look_at_rotation(location, unreal.Vector(0, 0, 50)),
    )
    camera.set_editor_property("tags", ["PTS.GameCamera"])
    camera.camera_component.set_editor_property("aspect_ratio", 1.5)
    actor_count = len(actors.get_all_level_actors())
    actors.set_selected_level_actors([target])
    write_json(state_root / "receipts/chest.json", {"request_id": "f" * 32, "status": "imported"})
    command({"mode": "reference", "camera_id": ""}, "a")
    handle = unreal.register_slate_post_tick_callback(tick)
except Exception:
    finish(traceback.format_exc())
