"""Exercise all six v0.7 workflows through real MCP, Blender and the native editor."""

import argparse
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

from prompt_to_scene import core, interactive, registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--editor", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    target = registry.resolve(args.project)
    assert target.root.parent == repo / ".local" and "smoke-" in target.root.name
    registry.install(target)
    root = core.state_root(target.root)
    for name in (
        "development-ready",
        "development-error.txt",
        "development-command.json",
        "development-command-done",
    ):
        (root / name).unlink(missing_ok=True)
    if target.engine == "unity":
        shutil.copyfile(
            repo / "tools/UnityDevelopment.cs", target.root / "Assets/Editor/UnityDevelopment.cs"
        )
        command = [
            args.editor,
            "-batchmode",
            "-projectPath",
            str(target.root),
            "-executeMethod",
            "UnityDevelopment.Run",
            "-logFile",
            str(target.root / "development.log"),
        ]
    else:
        command = [
            args.editor,
            str(target.project_file),
            "-unattended",
            "-nop4",
            "-nosound",
            "-RenderOffscreen",
            "-ExecutePythonScript=" + str(repo / "tools/unreal_development_driver.py"),
            "-abslog=" + str(target.root / "development.log"),
        ]
    evidence = []

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "prompt_to_scene.app", "--mcp"],
            env={
                **os.environ,
                "PTS_PROJECT": str(target.project_file or target.root),
                "PTS_HOME": str(root / "development-home"),
            },
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()

                async def call(name, values):
                    result = await client.call_tool(name, values)
                    assert not result.isError, result
                    data = result.structuredContent or json.loads(result.content[0].text)
                    evidence.append(dict(tool=name, result=data))
                    (target.root / "development-evidence.json").write_text(
                        json.dumps(evidence, indent=2)
                    )
                    print(name, data.get("status", "ok"), flush=True)
                    return data

                async def wait(task, expected="completed"):
                    for _ in range(30):
                        state = await call(
                            "get_task_status", dict(request_id=task["request_id"], wait_seconds=30)
                        )
                        if state["status"] in {"error", "completed", "imported", "cancelled"}:
                            assert state["status"] == expected, state
                            return state
                    raise AssertionError("Native task timed out")

                async def fixture(operation, asset=""):
                    (root / "development-command-done").unlink(missing_ok=True)
                    core.atomic_json(
                        root / "development-command.json", dict(operation=operation, asset_id=asset)
                    )
                    if operation == "stop":
                        return
                    for _ in range(200):
                        error = root / "development-error.txt"
                        assert not error.exists(), error.read_text() if error.exists() else ""
                        if (root / "development-command-done").exists():
                            return
                        await anyio.sleep(0.1)
                    raise AssertionError("Fixture command timed out")

                def position(x, y, z=0):
                    return [x, z, y] if target.engine == "unity" else [x, y, z]

                prefix = "dev_" + str(int(time.time()))
                names = []
                for i, kind in enumerate(("door", "chest", "pickup")):
                    name = prefix + "_" + kind
                    names.append(name)
                    await wait(
                        await call(
                            "create_interactive_prop",
                            dict(kind=kind, asset_id=name, position=position(i * 3, 0)),
                        )
                    )
                door = names[0]
                await wait(
                    await call(
                        "configure_interaction",
                        dict(
                            asset_id=door,
                            kind="door",
                            moving_asset_id=door + "_moving",
                            distance=3.5,
                            pivot=[0.6, 0, 0] if target.engine == "unity" else [0, 0.6, 0],
                            moving_offset=[-0.6, 0, 0]
                            if target.engine == "unity"
                            else [0, -0.6, 0],
                        ),
                    )
                )
                before = await wait(await call("inspect_scene", {}))
                identities = {o["id"] for o in before["assets"] if o["asset_id"] == door}
                await fixture("material")
                material = (
                    "Assets/PTS_Custom.mat"
                    if target.engine == "unity"
                    else "/Game/PromptToScene/LevelMaterials/M_trim"
                )
                await wait(
                    await call(
                        "protect_asset",
                        dict(
                            asset_id=door,
                            mode="set",
                            bindings=[dict(slot="Body", material_path=material)],
                            sockets=[
                                dict(
                                    name="handle", position=position(0.45, 0, 1), rotation=[0, 0, 0]
                                )
                            ],
                        ),
                    )
                )
                # Rebuild only base geometry; same native interaction configuration must survive.
                if target.engine == "unreal":
                    await fixture("legacy_bindings", door)
                await wait(
                    await call(
                        "build_asset",
                        dict(
                            asset_id=door,
                            blender_python=interactive.script(
                                "door", "base", [1.4, 0.14, 2.2], [0.1, 0.12, 0.15]
                            ),
                            collider=False,
                        ),
                    ),
                    "imported",
                )
                await fixture("check_preserved", door)
                # Regeneration must preserve settings and avoid a loose leaf.
                await wait(await call("create_interactive_prop", dict(kind="door", asset_id=door)))
                await fixture("check_preserved", door)
                after = await wait(await call("inspect_scene", {}))
                assert {o["id"] for o in after["assets"] if o["asset_id"] == door} == identities
                assert not any(o["asset_id"] == door + "_moving" for o in after["assets"])
                # Missing protected slot must stop before replacing the native content.
                script = interactive.script(
                    "door", "base", [1.4, 0.14, 2.2], [0.1, 0.12, 0.15]
                ).replace("material('Body'", "material('RenamedBody'")
                failed = await wait(
                    await call(
                        "build_asset", dict(asset_id=door, blender_python=script, collider=False)
                    ),
                    "error",
                )
                assert "Protected" in failed["error"]
                for preset in ("warm_cartoon", "moonlit"):
                    await wait(
                        await call("set_scene_look", dict(preset=preset, position=position(2, 0)))
                    )
                    capture = await wait(await call("set_scene_look", dict(mode="capture")))
                    assert (root / capture["preview"]).stat().st_size > 10000
                    shutil.copyfile(
                        root / capture["preview"], target.root / ("development-" + preset + ".png")
                    )
                plan = dict(
                    position=position(20, 0),
                    modules=[
                        dict(cell=[0, 0, 0], kind="room"),
                        dict(cell=[0, 1, 0], kind="stair", direction=2),
                        dict(cell=[0, 2, 1], kind="room"),
                    ],
                )
                await wait(await call("build_level", dict(level_id=prefix, settings=plan)))
                result = await wait(await call("build_level", dict(level_id=prefix, mode="check")))
                assert result["development"]["passed"]
                await fixture("block")
                result = await wait(await call("build_level", dict(level_id=prefix, mode="check")))
                assert not result["development"]["passed"]
                await fixture("unblock")
                indexed = await wait(await call("search_project_assets", {}))
                found = await call(
                    "search_project_assets",
                    dict(request_id=indexed["request_id"], query=door, limit=10),
                )
                entry = found["development"]["entries"][0]
                await call(
                    "tag_project_asset",
                    dict(
                        path=entry["path"],
                        tags=["wood", "door", "cozy"],
                        notes="Reusable test door",
                        license="MIT",
                        source="Prompt-to-Scene generated test",
                    ),
                )
                image = await wait(
                    await call("reuse_project_asset", dict(path=entry["path"], mode="preview"))
                )
                assert (root / image["preview"]).stat().st_size > 3000
                await wait(
                    await call(
                        "reuse_project_asset", dict(path=entry["path"], position=position(-3, 0))
                    )
                )
                reused = await wait(await call("inspect_scene", {}))
                assert len([o for o in reused["assets"] if o["asset_id"] == door]) == 2
                await wait(await call("set_scene_look", dict(preset="warm_cartoon")))
                # Exercise all three behaviors and clearance in Play/PIE, then return to Edit.
                played = await wait(
                    await call("run_playcheck", dict(asset_ids=names, level_id=prefix, duration=2))
                )
                assert played["development"]["passed"], played
                assert played["development"]["frames"] >= 2
                for screenshot in played["development"]["screenshots"]:
                    assert (root / screenshot).stat().st_size > 3000
                await wait(await call("set_scene_look", dict(mode="restore")))
                await fixture("check_restored")
                await fixture("stop")
                print("PASS: all six native development workflows", flush=True)

    with (target.root / "development-console.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 180
            while not (root / "development-ready").exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(
                        "Editor did not start: " + str(target.root / "development.log")
                    )
                time.sleep(0.2)
            anyio.run(exercise)
            assert process.wait(timeout=60) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    main()
