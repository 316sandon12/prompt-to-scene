import json
import os
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_tool_discovery_and_error_reporting(tmp_path):
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()

    async def exercise():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from prompt_to_scene.server import main; main()"],
            env={**os.environ, "PTS_UNITY_PROJECT": str(tmp_path)},
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
                }
                result = await session.call_tool("get_asset_status", {"asset_id": "crate"})
                assert not result.isError
                payload = result.structuredContent or json.loads(result.content[0].text)
                assert payload["status"] == "unknown"
                rejected = await session.call_tool("get_asset_status", {"asset_id": "../escape"})
                assert rejected.isError

    anyio.run(exercise)
