"""Exercise the distributed executable without Python in the child's environment."""

import argparse
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--blender", help="Also verify a detached packaged Blender job locally")
    args = parser.parse_args()
    binary = str(args.executable.resolve())
    with tempfile.TemporaryDirectory(prefix="pts package test ") as directory:
        home = Path(directory)
        project = home / "Unity Project"
        (project / "Assets").mkdir(parents=True)
        (project / "ProjectSettings").mkdir()
        environment = {
            **os.environ,
            "PTS_HOME": str(home / "settings"),
            "PTS_SETUP_URL_FILE": str(home / "url.txt"),
        }
        environment.pop("PTS_PROJECT", None)
        environment.pop("PTS_UNITY_PROJECT", None)
        environment.pop("PYTHONPATH", None)
        if args.blender:
            environment["PTS_BLENDER"] = args.blender
        submitted = []

        async def protocol():
            parameters = StdioServerParameters(command=binary, args=["--mcp"], env=environment)
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    assert len((await client.list_tools()).tools) == 65
                    resource = await client.read_resource("ui://prompt-to-scene/workbench.html")
                    assert "ui/initialize" in resource.contents[0].text
                    assert "repairButton" in resource.contents[0].text
                    response = await client.call_tool(
                        "connect_project", {"project_path": str(project)}
                    )
                    assert not response.isError, response
                    assert (
                        project / "Packages/com.prompttoscene.bridge/Editor/SceneActions.cs"
                    ).is_file()
                    assert (
                        project / "Packages/com.prompttoscene.bridge/Runtime/Interaction.cs"
                    ).is_file()
                    assert (
                        project / "Packages/com.prompttoscene.bridge/Editor/AssetOrganization.cs"
                    ).is_file()
                    organized = await client.call_tool(
                        "organize_project_assets", {"mode": "history"}
                    )
                    assert not organized.isError, organized
                    profile = await client.call_tool("project_conventions", {})
                    assert not profile.isError, profile
                    assert (
                        project / "Packages/com.prompttoscene.bridge/Editor/WorkshopWindow.cs"
                    ).is_file()
                    assert (project / ".prompt-to-scene/launcher.json").is_file()
                    unreal_project = home / "Unreal Project"
                    unreal_project.mkdir()
                    (unreal_project / "Test.uproject").write_text('{"FileVersion":3}')
                    response = await client.call_tool(
                        "connect_project", {"project_path": str(unreal_project)}
                    )
                    assert not response.isError, response
                    assert (
                        unreal_project
                        / "Plugins/PromptToScene/Content/Templates/BP_PTSInteraction.uasset"
                    ).stat().st_size > 1000
                    assert not (unreal_project / "Plugins/PromptToScene/Source").exists()
                    assert (
                        unreal_project
                        / "Plugins/PromptToScene/Content/Templates/EUW_PTSWorkshop.uasset"
                    ).stat().st_size > 1000
                    assert (
                        unreal_project
                        / "Plugins/PromptToScene/Content/Python"
                        / "prompt_to_scene_unreal/organization.py"
                    ).is_file()
                    response = await client.call_tool(
                        "connect_project", {"project_path": str(project)}
                    )
                    assert not response.isError, response
                    response = await client.call_tool("inspect_library", {})
                    assert not response.isError, response
                    catalog = response.structuredContent or json.loads(response.content[0].text)
                    assert len(catalog["recipes"]) == 9
                    if args.blender:
                        response = await client.call_tool(
                            "set_project_style", {"preset": "cozy", "quality": "mobile"}
                        )
                        assert not response.isError, response
                        response = await client.call_tool(
                            "create_prop", {"kind": "chair", "asset_id": "packaged_chair"}
                        )
                        assert not response.isError, response
                        submitted.append(
                            response.structuredContent or json.loads(response.content[0].text)
                        )

        anyio.run(protocol)
        # Native panels launch the frozen core without Python or an MCP client.
        native_root = project / ".prompt-to-scene"
        (native_root / "editor.json").write_text("{}")
        request_id = "1" * 32
        (native_root / "panel-requests").mkdir(exist_ok=True)
        (native_root / "panel-requests" / (request_id + ".json")).write_text(
            json.dumps({"action": "profile", "values": {"mode": "read"}})
        )
        service = subprocess.Popen(
            [binary, "--editor-service", str(project)],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            output = native_root / "panel-results" / (request_id + ".json")
            deadline = time.monotonic() + 45
            while not output.exists() and time.monotonic() < deadline and service.poll() is None:
                time.sleep(0.1)
            assert output.exists(), "Frozen native panel service did not answer"
            assert json.loads(output.read_text())["schema_version"] == 1
        finally:
            service.terminate()
            service.communicate(timeout=10)
        if submitted:
            # The MCP parent has exited. Its detached child must survive its extraction cleanup.
            revision = submitted[0]["request_id"]
            state_file = project / ".prompt-to-scene/jobs" / revision / "state.json"
            deadline = time.monotonic() + 600
            while True:
                state = json.loads(state_file.read_text())
                if state["status"] != "building":
                    assert state["status"] == "queued", state
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Detached packaged worker did not finish")
                time.sleep(0.1)
            work = project / ".prompt-to-scene/work/packaged_chair" / revision
            report = json.loads((work / "report.json").read_text())
            assert report["texture_count"] >= 10, report
            assert (work / "studio.png").stat().st_size > 5000
            assert (work / "blender_recipe.py").is_file()
            assert (work / "blender_prepare.py").is_file()
            assert (work / "blender_cache.py").is_file()
            assert (work / "blender_edit.py").is_file()
            assert (work / "lod_1.fbx").is_file()

            async def intake():
                parameters = StdioServerParameters(command=binary, args=["--mcp"], env=environment)
                async with stdio_client(parameters) as (read, write):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        response = await client.call_tool(
                            "import_asset",
                            {
                                "asset_id": "packaged_external",
                                "source": {"path": str(work / "source.blend")},
                                "settings": {"texture_size": 256},
                                "preview_only": True,
                            },
                        )
                        assert not response.isError, response
                        return response.structuredContent or json.loads(response.content[0].text)

            task = anyio.run(intake)
            state_file = project / ".prompt-to-scene/jobs" / task["request_id"] / "state.json"
            deadline = time.monotonic() + 600
            while True:
                state = json.loads(state_file.read_text())
                if state["status"] != "building":
                    assert state["status"] == "completed", state
                    assert "before.png" in state["previews"]
                    assert state["report"]["preparation"]["budget_passed"]
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Packaged external intake did not finish")
                time.sleep(0.1)
        child = subprocess.Popen([binary, "--setup", "--no-browser"], env=environment)
        try:
            deadline = time.monotonic() + 30
            while not (home / "url.txt").exists():
                if child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Packaged setup failed to launch")
                time.sleep(0.1)
            origin, token = (home / "url.txt").read_text().split("/#")
            with urllib.request.urlopen(origin) as response:
                assert b"Prompt-to-Scene" in response.read()
            with urllib.request.urlopen(origin + "/workshop.js") as response:
                assert response.headers["Content-Type"].startswith("text/javascript")
                assert b"importSource" in response.read()
            for route, marker in (
                ("/workbench", b"qualityButton"),
                ("/workbench.js", b"ui/initialize"),
            ):
                with urllib.request.urlopen(origin + route) as response:
                    assert marker in response.read()
            request = urllib.request.Request(origin + "/api/state", headers={"X-PTS-Token": token})
            with urllib.request.urlopen(request) as response:
                assert json.load(response)["active"] == str(project.resolve())
        finally:
            child.terminate()
            child.wait(timeout=20)
    print("PASS: packaged stdio, tool discovery, embedded bridge and setup UI")


if __name__ == "__main__":
    main()
