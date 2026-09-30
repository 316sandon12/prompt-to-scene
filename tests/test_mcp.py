import json
import os
import sys

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.parametrize("engine", ["unity", "unreal"])
def test_real_stdio_tool_discovery_and_error_reporting(tmp_path, engine):
    if engine == "unity":
        (tmp_path / "Assets").mkdir()
        (tmp_path / "ProjectSettings").mkdir()
    else:
        (tmp_path / "Test.uproject").write_text(json.dumps({"FileVersion": 3}))

    async def exercise():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from prompt_to_scene.server import main; main()"],
            env={**os.environ, "PTS_PROJECT": str(tmp_path), "PTS_ENGINE": engine},
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                catalog = await session.list_tools()
                assert {tool.name for tool in catalog.tools} == {
                    "inspect_target",
                    "build_asset",
                    "publish_blend",
                    "get_asset_status",
                    "list_projects",
                    "connect_project",
                    "create_prop",
                    "inspect_asset",
                    "revise_prop",
                    "get_task_status",
                    "cancel_task",
                    "inspect_scene",
                    "edit_scene",
                    "undo_scene_edit",
                    "restore_asset",
                    "get_preview",
                }
                result = await session.call_tool("get_asset_status", {"asset_id": "crate"})
                assert not result.isError
                payload = result.structuredContent or json.loads(result.content[0].text)
                assert payload["status"] == "unknown"
                rejected = await session.call_tool("get_asset_status", {"asset_id": "../escape"})
                assert rejected.isError
                no_revision = await session.call_tool(
                    "get_asset_status",
                    {
                        "asset_id": "crate",
                        "wait_seconds": 1,
                    },
                )
                assert no_revision.isError

    anyio.run(exercise)
