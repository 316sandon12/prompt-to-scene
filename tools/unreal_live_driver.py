"""Keep a disposable Unreal test editor alive; the plugin's normal tick consumes requests."""

import json
import time
from pathlib import Path

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
assert (root / "initial-passed.json").exists(), "Run only inside the isolated smoke project"
assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level("/Game/Smoke")
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "live-ready.json").write_text('{"ready": true}')
deadline = time.monotonic() + 120


def finish(result):
    (root / "live-editor-result.json").write_text(json.dumps(result))
    unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def check(_delta):
    try:
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for the normal editor watcher")
        expected = root / "live-expected.json"
        receipt_file = root / "receipts/live_cube.json"
        if not expected.exists() or not receipt_file.exists():
            return
        revision = json.loads(expected.read_text())["request_id"]
        receipt = json.loads(receipt_file.read_text())
        if receipt.get("request_id") != revision:
            return
        assert receipt["status"] == "imported", receipt
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
        instances = [a for a in actors if "PTS.Asset:live_cube" in map(str, a.tags)]
        assert len(instances) == 1, "Automatic placement missing or duplicated"
        location = instances[0].get_actor_location()
        assert abs(location.x - 150) < 0.01 and abs(location.y + 200) < 0.01
        assert abs(location.z) < 0.01
        assert instances[0].static_mesh_component.static_mesh.get_num_triangles(0) == 12
        finish({"result": "PASS", "request_id": revision, "actor_count": len(instances)})
    except Exception as error:
        finish({"result": "FAIL", "error": str(error)})


handle = unreal.register_slate_post_tick_callback(check)
