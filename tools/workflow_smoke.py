"""Real MCP + Blender + engine: selection, edit/undo, recipes, restore, image, cancel."""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from prompt_to_scene import core, registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--editor", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    target = registry.resolve(str(args.project))
    project = target.root
    if project.parent != repo / ".local" or "smoke-" not in project.name:
        raise ValueError("Use a disposable project created by the engine smoke test")
    registry.install(target)
    root = core.state_root(project)
    for name in (
        "workflow-ready",
        "workflow-command-done",
        "workflow-command.json",
        "workflow-error.txt",
    ):
        (root / name).unlink(missing_ok=True)
    if target.engine == "unity":
        shutil.copyfile(repo / "tools/UnityWorkflow.cs", project / "Assets/Editor/UnityWorkflow.cs")
        command = [
            args.editor,
            "-batchmode",
            "-projectPath",
            str(project),
            "-executeMethod",
            "UnityWorkflow.Run",
            "-logFile",
            str(project / "workflow.log"),
        ]
    else:
        command = [
            args.editor,
            str(target.project_file),
            "-unattended",
            "-nop4",
            "-nosound",
            "-RenderOffscreen",
            "-ExecutePythonScript=" + str(repo / "tools/unreal_workflow_driver.py"),
            "-abslog=" + str(project / "workflow.log"),
        ]
    evidence = []
    name = "workflow_" + str(int(time.time()))

    async def exercise():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "prompt_to_scene.app", "--mcp"],
            env={**os.environ, "PTS_PROJECT": str(args.project.resolve())},
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()

                async def call(tool, values):
                    result = await client.call_tool(tool, values)
                    assert not result.isError, result
                    payload = result.structuredContent or json.loads(result.content[0].text)
                    evidence.append({"tool": tool, "result": payload})
                    return payload

                async def wait(task, expected="imported"):
                    for _ in range(8):
                        result = await call(
                            "get_task_status",
                            {"request_id": task["request_id"], "wait_seconds": 30},
                        )
                        if result["status"] in {"imported", "error", "cancelled", "completed"}:
                            assert result["status"] == expected, result
                            return result
                    raise AssertionError("Task did not finish")

                async def fixture(operation):
                    done = root / "workflow-command-done"
                    done.unlink(missing_ok=True)
                    core.atomic_json(
                        root / "workflow-command.json", {"operation": operation, "asset_id": name}
                    )
                    for _ in range(100):
                        assert not (root / "workflow-error.txt").exists(), (
                            root / "workflow-error.txt"
                        ).read_text()
                        if done.exists():
                            return
                        await anyio.sleep(0.1)
                    raise AssertionError("Fixture command timed out")

                async def scene():
                    state = await call("inspect_scene", {})
                    if state["status"] == "queued":
                        state = await wait(state, "completed")
                    assert state["status"] == "completed", state
                    return state

                initial = await wait(
                    await call(
                        "create_prop", {"kind": "crate", "asset_id": name, "collider": False}
                    )
                )
                objects = (await scene())["selected"]
                assert len(objects) == 1 and objects[0]["asset_id"] == name, objects
                axis = 1 if target.engine == "unity" else 2
                assert abs(objects[0]["position"][axis] - 1) < 0.03, "Auto ground placement failed"
                await fixture("duplicate")
                state = await scene()
                baseline = {o["id"]: o for o in state["assets"] if o["asset_id"] == name}
                assert len(baseline) == 2
                chosen = state["selected"][0]["id"]
                moved = await call(
                    "edit_scene",
                    {"operation": "transform", "values": {"move": [1, 0, 0], "scale": [1.2, 1, 1]}},
                )
                if moved["status"] == "queued":
                    moved = await wait(moved, "completed")
                assert moved["status"] == "completed", moved
                state = await scene()
                for obj in state["assets"]:
                    if obj["id"] in baseline:
                        expected = baseline[obj["id"]]["position"][0] + (
                            1 if obj["id"] == chosen else 0
                        )
                        assert abs(obj["position"][0] - expected) < 0.01
                undo = await call("undo_scene_edit", {"undo_id": moved["undo_id"]})
                assert undo["status"] == "completed", undo
                tint = await call(
                    "edit_scene",
                    {
                        "operation": "tint",
                        "values": {"color": [0.02, 0.7, 0.1], "material": "Wood"},
                    },
                )
                assert tint["status"] == "completed", tint
                tinted = {o["id"]: o for o in (await scene())["assets"] if o["asset_id"] == name}
                materials = "renderers" if target.engine == "unity" else "materials"
                assert tinted[chosen][materials] != baseline[chosen][materials]
                for key in baseline.keys() - {chosen}:
                    assert tinted[key][materials] == baseline[key][materials], (
                        "Tint leaked to other instance"
                    )
                revision = await wait(
                    await call("revise_prop", {"asset_id": name, "parameters": {"height": 1.4}})
                )
                key = "prefab_guid" if target.engine == "unity" else "actor_guid"
                assert revision[key] == initial[key]
                state = await scene()
                assert {o["id"] for o in state["selected"]} == {chosen}, (
                    "Revision changed selection"
                )
                assert {o["id"] for o in state["assets"] if o["asset_id"] == name} == set(baseline)
                current = next(o for o in state["assets"] if o["id"] == chosen)
                assert current[materials] == tinted[chosen][materials], (
                    "Instance tint lost on revision"
                )
                restored = await wait(
                    await call(
                        "restore_asset", {"asset_id": name, "revision": initial["request_id"]}
                    )
                )
                assert abs(restored["bounds_size"][axis] - initial["bounds_size"][axis]) < 0.01
                await fixture("check")
                undo = await call("undo_scene_edit", {"undo_id": tint["undo_id"]})
                assert undo["status"] == "completed", undo
                preview = await client.call_tool("get_preview", {"asset_id": name})
                for _ in range(3):
                    images = [part for part in preview.content if part.type == "image"]
                    if images:
                        break
                    pending = preview.structuredContent or json.loads(preview.content[0].text)
                    assert pending["status"] == "queued", pending
                    preview = await client.call_tool(
                        "get_preview", {"request_id": pending["request_id"]}
                    )
                assert images and not preview.isError, preview
                image = base64.b64decode(images[0].data)
                assert image.startswith(b"\x89PNG\r\n\x1a\n") and len(image) > 10000
                (project / "workflow-preview.png").write_bytes(image)
                bad = await call(
                    "build_asset",
                    {"asset_id": name + "_cancel", "blender_python": "import time\ntime.sleep(90)"},
                )
                await call("cancel_task", {"request_id": bad["request_id"]})
                await wait(bad, "cancelled")
                (project / "workflow-evidence.json").write_text(json.dumps(evidence, indent=2))
                core.atomic_json(root / "workflow-command.json", {"operation": "stop"})

    with (project / "workflow-console.log").open("w") as log:
        editor = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 180
            while not (root / "workflow-ready").exists():
                if editor.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(
                        "Editor failed to start; inspect " + str(project / "workflow.log")
                    )
                time.sleep(0.2)
            anyio.run(exercise)
            assert editor.wait(timeout=60) == 0
            print(
                "PASS: " + target.engine + " complete interactive workflow; " + str(project),
                flush=True,
            )
        finally:
            if editor.poll() is None:
                editor.terminate()
                editor.wait(timeout=30)


if __name__ == "__main__":
    main()
