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
                    "inspect_library",
                    "get_project_style",
                    "set_project_style",
                    "edit_prop_part",
                    "create_prop_set",
                    "create_variants",
                    "get_variants",
                    "choose_variant",
                    "get_studio_preview",
                    "arrange_props",
                    "search_assets",
                    "import_asset",
                    "publish_prepared",
                    "prepare_asset",
                    "create_style_kit",
                    "edit_selected_prop",
                    "capture_review",
                    "get_review",
                    "open_workbench",
                    "workbench_action",
                    "compose_scene",
                    "edit_imported_part",
                    "set_art_brief",
                    "get_art_reference",
                    "review_quality",
                    "repair_quality",
                    "inspect_performance",
                    "apply_usage_preset",
                    "list_generation_providers",
                    "generate_model",
                    "resume_workflow",
                    "create_interactive_prop",
                    "configure_interaction",
                    "protect_asset",
                    "review_asset_update",
                    "set_scene_look",
                    "build_level",
                    "run_playcheck",
                    "search_project_assets",
                    "reuse_project_asset",
                    "tag_project_asset",
                    "organize_project_assets",
                }
                app_tool = next(t for t in catalog.tools if t.name == "open_workbench")
                assert app_tool.meta["ui"]["resourceUri"] == "ui://prompt-to-scene/workbench.html"
                resources = await session.list_resources()
                assert any(
                    str(r.uri) == app_tool.meta["ui"]["resourceUri"] for r in resources.resources
                )
                resource = await session.read_resource(app_tool.meta["ui"]["resourceUri"])
                assert resource.contents[0].mimeType == "text/html;profile=mcp-app"
                assert "ui/initialize" in resource.contents[0].text
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
