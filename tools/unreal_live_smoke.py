"""Verify real MCP -> Blender -> automatic UE polling -> exact-request import receipt."""

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

from prompt_to_scene.core import atomic_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unreal", required=True)
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    descriptor = args.project.resolve()
    project = descriptor.parent
    if project.parent != repo / ".local" or not project.name.startswith("unreal-smoke-"):
        raise ValueError("Use a disposable project produced by unreal_smoke_test.py")
    state = project / ".prompt-to-scene"
    if not (state / "initial-passed.json").exists():
        raise ValueError("The initial engine smoke test must pass first")
    shutil.copytree(
        repo / "unreal/PromptToScene", project / "Plugins/PromptToScene", dirs_exist_ok=True
    )
    for name in ("live-ready.json", "live-expected.json", "live-editor-result.json"):
        (state / name).unlink(missing_ok=True)

    async def exercise():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from prompt_to_scene.server import main; main()"],
            env={**os.environ, "PTS_PROJECT": str(descriptor), "PTS_ENGINE": "unreal"},
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()

                async def call(name, arguments):
                    response = await client.call_tool(name, arguments)
                    assert not response.isError, response
                    return response.structuredContent or json.loads(response.content[0].text)

                target = await call("inspect_target", {})
                assert target["engine"] == "unreal"
                request = await call(
                    "build_asset",
                    {
                        "asset_id": "live_cube",
                        "blender_python": (repo / "examples/textured_cube.py").read_text(),
                        "position": [1.5, -2, 0],
                    },
                )
                atomic_json(state / "live-expected.json", {"request_id": request["request_id"]})
                receipt = await call(
                    "get_asset_status",
                    {
                        "asset_id": "live_cube",
                        "request_id": request["request_id"],
                        "wait_seconds": 30,
                    },
                )
                assert receipt["status"] == "imported", receipt
                assert receipt["request_id"] == request["request_id"], receipt
                (project / "live-evidence.json").write_text(json.dumps(receipt, indent=2))

    with (project / "unreal-live.log").open("w") as log:
        editor = subprocess.Popen(
            [
                args.unreal,
                str(descriptor),
                "-unattended",
                "-nop4",
                "-nosplash",
                "-RenderOffscreen",
                "-nosound",
                "-ExecutePythonScript=" + str(repo / "tools/unreal_live_driver.py"),
                "-abslog=" + str(project / "engine-live.log"),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 120
            while not (state / "live-ready.json").exists():
                if editor.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Editor did not become ready; inspect unreal-live.log")
                time.sleep(0.2)
            anyio.run(exercise)
            assert editor.wait(timeout=60) == 0
            result = json.loads((state / "live-editor-result.json").read_text())
            assert result["result"] == "PASS", result
            print(
                "PASS: real MCP build + exact-request wait + automatic Unreal watcher + actor",
                flush=True,
            )
        finally:
            if editor.poll() is None:
                editor.terminate()
                editor.wait(timeout=30)


if __name__ == "__main__":
    main()
