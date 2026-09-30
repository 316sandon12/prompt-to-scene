"""Real MCP, Blender and editor evidence for art direction, parts and contextual arrangement."""

import argparse
import base64
import hashlib
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
    parser.add_argument("--variants", action="store_true")
    parser.add_argument("--preparation", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    target = registry.resolve(str(args.project))
    project = target.root
    if project.parent != repo / ".local" or "smoke-" not in project.name:
        raise ValueError("Use an isolated smoke project")
    registry.install(target)
    root = core.state_root(project)
    for name in (
        "authoring-ready",
        "authoring-error.txt",
        "authoring-command.json",
        "authoring-command-done",
    ):
        (root / name).unlink(missing_ok=True)
    if target.engine == "unity":
        shutil.copyfile(
            repo / "tools/UnityAuthoring.cs", project / "Assets/Editor/UnityAuthoring.cs"
        )
        command = [
            args.editor,
            "-batchmode",
            "-projectPath",
            str(project),
            "-executeMethod",
            "UnityAuthoring.Run",
            "-logFile",
            str(project / "authoring.log"),
        ]
    else:
        command = [
            args.editor,
            str(target.project_file),
            "-unattended",
            "-nop4",
            "-nosound",
            "-RenderOffscreen",
            "-ExecutePythonScript=" + str(repo / "tools/unreal_authoring_driver.py"),
            "-abslog=" + str(project / "authoring.log"),
        ]
    prefix = "art_" + str(int(time.time()))
    evidence = []

    async def exercise():
        environment = {
            **os.environ,
            "PTS_PROJECT": str(target.project_file or project),
            "PTS_HOME": str(root / "isolated-client-home"),
        }
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "prompt_to_scene.app", "--mcp"], env=environment
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()

                async def call(name, values):
                    result = await client.call_tool(name, values)
                    assert not result.isError, result
                    payload = result.structuredContent or json.loads(result.content[0].text)
                    evidence.append({"tool": name, "result": payload})
                    print(name, payload.get("status", "ok"), flush=True)
                    return payload

                async def wait(task, expected="imported"):
                    for _ in range(30):
                        state = await call(
                            "get_task_status",
                            {"request_id": task["request_id"], "wait_seconds": 30},
                        )
                        if state["status"] in {"imported", "completed", "error", "cancelled"}:
                            assert state["status"] == expected, state
                            return state
                    raise AssertionError("Task timed out")

                async def fixture(operation, asset):
                    (root / "authoring-command-done").unlink(missing_ok=True)
                    core.atomic_json(
                        root / "authoring-command.json", {"operation": operation, "asset_id": asset}
                    )
                    if operation == "stop":
                        return
                    for _ in range(100):
                        error = root / "authoring-error.txt"
                        assert not error.exists(), error.read_text() if error.exists() else ""
                        if (root / "authoring-command-done").exists():
                            return
                        await anyio.sleep(0.1)
                    raise AssertionError("Fixture command timed out")

                async def scene():
                    state = await call("inspect_scene", {})
                    return await wait(state, "completed") if state["status"] == "queued" else state

                def position(x, y):
                    return [x, 0, y] if target.engine == "unity" else [x, y, 0]

                if args.preparation:
                    from preparation_checks import exercise_preparation

                    await exercise_preparation(
                        client, call, wait, fixture, scene, position, target, prefix
                    )
                    (project / "preparation-evidence.json").write_text(
                        json.dumps(evidence, indent=2)
                    )
                    await fixture("stop", prefix)
                    return

                lib = await call("inspect_library", {})
                assert len(lib["recipes"]) == 9
                await call("set_project_style", {"preset": "cozy", "quality": "mobile"})
                table, chair, stool = [prefix + "_" + k for k in ("table", "chair", "stool")]
                tasks = await call(
                    "create_prop_set",
                    {
                        "items": [
                            {"kind": "table", "asset_id": table, "position": position(0, 0)},
                            {"kind": "chair", "asset_id": chair, "position": position(6, 6)},
                            {"kind": "stool", "asset_id": stool, "position": position(10, 10)},
                        ]
                    },
                )
                assert tasks["status"] == "building"
                imported = [await wait(t) for t in tasks["tasks"]]
                for name in (table, chair, stool):
                    await fixture("check", name)
                # Bind an already imported project material; the adapter must reuse it unchanged.
                await fixture("capture_material", table)
                reference = json.loads((root / "authoring-material.json").read_text())
                digest = hashlib.sha256(Path(reference["file"]).read_bytes()).hexdigest()
                await call(
                    "set_project_style",
                    {
                        "reference_asset": table,
                        "overrides": {"material_bindings": {"wood": reference["path"]}},
                    },
                )
                reused = "reuse_" + prefix
                await wait(
                    await call(
                        "create_prop",
                        {"kind": "bench", "asset_id": reused, "position": position(20, 20)},
                    )
                )
                await fixture("check_reuse", reused)
                assert hashlib.sha256(Path(reference["file"]).read_bytes()).hexdigest() == digest, (
                    "Reused project material was modified"
                )
                await call("set_project_style", {"preset": "cozy", "quality": "mobile"})
                await fixture("select", chair)
                info = await call("inspect_asset", {"asset_id": chair})
                original = info["report"]["parts"]
                tint = await call(
                    "edit_scene",
                    {
                        "operation": "tint",
                        "values": {"material": "Wood", "color": [0.3, 0.12, 0.04]},
                    },
                )
                if tint["status"] == "queued":
                    tint = await wait(tint, "completed")
                assert tint["status"] == "completed", tint
                before = (await scene())["selected"][0]
                revised = await wait(
                    await call(
                        "edit_prop_part",
                        {"asset_id": chair, "part": "backrest", "changes": {"scale": [1, 1, 1.15]}},
                    )
                )
                native_key = "prefab_guid" if target.engine == "unity" else "actor_guid"
                assert revised[native_key] == imported[1][native_key]
                current = (await scene())["assets"]
                current = next(o for o in current if o["id"] == before["id"])
                material_key = "renderers" if target.engine == "unity" else "materials"
                assert current[material_key] == before[material_key], "Tint lost during part edit"
                after = (await call("inspect_asset", {"asset_id": chair}))["report"]["parts"]
                for part in original:
                    assert (original[part]["geometry_hash"] == after[part]["geometry_hash"]) == (
                        part != "backrest"
                    )
                await fixture("select", table)
                arranged = await call(
                    "arrange_props",
                    {"items": [{"asset_id": chair, "count": 4}], "relation": "around"},
                )
                if arranged["status"] == "queued":
                    arranged = await wait(arranged, "completed")
                assert arranged["status"] == "completed", arranged
                assert len([o for o in (await scene())["assets"] if o["asset_id"] == chair]) == 4
                undone = await call("undo_scene_edit", {"undo_id": arranged["undo_id"]})
                if undone["status"] == "queued":
                    undone = await wait(undone, "completed")
                assert undone["status"] == "completed", undone
                assert len([o for o in (await scene())["assets"] if o["asset_id"] == chair]) == 1
                for items, relation in (
                    ([{"asset_id": chair, "count": 4}], "around"),
                    ([{"asset_id": stool}], "under"),
                ):
                    task = await call(
                        "arrange_props", {"items": items, "relation": relation, "fit": True}
                    )
                    if task["status"] == "queued":
                        task = await wait(task, "completed")
                    assert task["status"] == "completed", task
                if args.variants:
                    before_count = len((await scene())["assets"])
                    study = await call(
                        "create_variants",
                        {"kind": "cabinet", "asset_id": prefix + "_chosen", "count": 2},
                    )
                    for candidate in study["candidates"]:
                        await wait(candidate, "completed")
                    study = await call("get_variants", {"study_id": study["study_id"]})
                    assert study["status"] == "completed"
                    assert len((await scene())["assets"]) == before_count, "Draft leaked into scene"
                    preview = await client.call_tool(
                        "get_studio_preview",
                        {
                            "asset_id": study["candidates"][0]["asset_id"],
                            "request_id": study["candidates"][0]["request_id"],
                        },
                    )
                    assert any(c.type == "image" for c in preview.content), preview
                    await wait(
                        await call(
                            "choose_variant",
                            {
                                "study_id": study["study_id"],
                                "index": 1,
                                "position": position(-3, 0),
                            },
                        )
                    )
                await fixture("select_all", prefix)
                preview = await client.call_tool("get_preview", {})
                for _ in range(4):
                    images = [c for c in preview.content if c.type == "image"]
                    if images:
                        break
                    pending = preview.structuredContent or json.loads(preview.content[0].text)
                    assert pending["status"] == "queued", pending
                    preview = await client.call_tool(
                        "get_preview", {"request_id": pending["request_id"]}
                    )
                assert images, preview
                (project / "authoring-preview.png").write_bytes(base64.b64decode(images[0].data))
                (project / "authoring-evidence.json").write_text(json.dumps(evidence, indent=2))
                await fixture("stop", table)

    with (project / "authoring-launch.log").open("w") as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 240
            while not (root / "authoring-ready").exists():
                if child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Editor did not become ready; inspect authoring.log")
                time.sleep(0.25)
            anyio.run(exercise)
            child.wait(timeout=60)
            assert child.returncode == 0
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    print(
        "PASS: native "
        + target.engine
        + " authoring, PBR, semantic edits, layout/undo and previews",
        flush=True,
    )


if __name__ == "__main__":
    main()
