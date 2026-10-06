"""Exercise project conventions, settled intake, visual metadata and native selective adaptation."""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from prompt_to_scene import core, registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    target = registry.resolve(args.project)
    assert target.root.parent == repo / ".local" and "smoke-" in target.root.name
    root = core.state_root(target.root)
    engine = target.engine
    prefix = "Assets" if engine == "unity" else "/Game"
    paths = [
        prefix + "/PipelineSmoke/Prop" + str(i) + (".prefab" if engine == "unity" else "")
        for i in range(2)
    ]
    reference = prefix + "/PipelineSmoke/Reference" + (".mat" if engine == "unity" else "")
    evidence = []

    async def run():
        for _ in range(600):
            if (root / "pipeline-ready").exists():
                break
            await anyio.sleep(0.2)
        assert (root / "pipeline-ready").exists(), "Start the native pipeline fixture first"
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "prompt_to_scene.app", "--mcp"],
            env=dict(
                os.environ,
                PTS_PROJECT=str(target.project_file or target.root),
                PTS_HOME=str(root / "pipeline-home"),
            ),
        )
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as client,
        ):
            await client.initialize()

            async def call(name, **values):
                result = await client.call_tool(name, values)
                assert not result.isError, result
                data = result.structuredContent or json.loads(result.content[0].text)
                evidence.append(dict(tool=name, values=values, result=data))
                core.atomic_json(target.root / "pipeline-evidence.json", evidence)
                print(engine, name, data.get("status", "ok"), flush=True)
                return data

            async def wait(task):
                for _ in range(40):
                    state = await call(
                        "get_task_status", request_id=task["request_id"], wait_seconds=20
                    )
                    if state["status"] in {"completed", "imported", "error", "cancelled"}:
                        assert state["status"] in {"completed", "imported"}, state
                        return state
                raise AssertionError("Native pipeline task timed out")

            async def native(operation):
                (root / "pipeline-command-done").unlink(missing_ok=True)
                core.atomic_json(root / "pipeline-command.json", {"operation": operation})
                for _ in range(300):
                    error = root / "pipeline-error.txt"
                    assert not error.is_file(), error.read_text() if error.is_file() else ""
                    if (root / "pipeline-command-done").exists():
                        return
                    await anyio.sleep(0.1)
                raise AssertionError("Native verification timeout")

            settings = dict(
                organization={
                    "destination": prefix + "/PipelineOutput",
                    "rules": {"model": {"prefix": "Mesh_"}},
                },
                preparation={"triangle_budget": 20000, "texture_size": 256},
                intake={"folder": "PipelineInbox", "enabled": False, "settle_seconds": 2},
            )
            profile = await call("project_conventions", mode="save", settings=settings)
            assert profile["preparation"]["texture_size"] == 256
            scan = await wait(
                await call("organize_project_assets", mode="scan", scope=prefix + "/PipelineSmoke")
            )
            await call(
                "project_conventions", mode="suggest", scan_id=scan["development"]["scan_id"]
            )
            semantic = await wait(await call("describe_project_assets", paths=[paths[0]]))
            proof = semantic["results"][0]
            image = await client.call_tool(
                "get_asset_evidence", {"evidence_id": proof["request_id"]}
            )
            assert not image.isError and any(c.type == "image" for c in image.content)
            # A fixture user correction verifies metadata/search, not automatic vision accuracy.
            await call(
                "save_asset_description",
                evidence_id=proof["request_id"],
                corrected=True,
                description=dict(
                    name="Blue fixture cube",
                    object_type="cube",
                    materials=["blue"],
                    uses=["pipeline verification 检查方块"],
                    confidence=1.0,
                ),
            )
            index = await wait(await call("search_project_assets"))
            found = await call(
                "search_project_assets", request_id=index["request_id"], query="检查方块"
            )
            assert any(row["path"] == paths[0] for row in found["development"]["entries"])
            preview = await wait(
                await call("adapt_asset_materials", paths=paths, reference=reference)
            )
            plan = await call("adapt_asset_materials", mode="inspect", plan_id=preview["plan_id"])
            assert len(plan["entries"]) == 2 and len(preview["previews"]) == 2, plan
            for pair in preview["previews"]:
                before = root / "previews" / (pair["before"] + ".png")
                after = root / "previews" / (pair["after"] + ".png")
                assert before.read_bytes() != after.read_bytes(), "Native preview did not change"
            await wait(
                await call(
                    "adapt_asset_materials",
                    mode="apply",
                    plan_id=preview["plan_id"],
                    selected=[plan["entries"][0]["id"]],
                )
            )
            await native("verify_apply")
            await wait(await call("adapt_asset_materials", mode="undo", plan_id=preview["plan_id"]))
            await native("verify_undo")
            # Actual file IPC used by the native panels, scoped to one selected model.
            request_id = "9" * 32
            response = root / "panel-results" / (request_id + ".json")
            response.unlink(missing_ok=True)
            core.atomic_json(
                root / "panel-requests" / (request_id + ".json"),
                {"action": "organize_selected", "values": {"paths": [paths[0]]}},
            )
            for _ in range(150):
                if response.is_file():
                    break
                await anyio.sleep(0.2)
            assert response.is_file(), "Native panel service did not respond"
            panel = await wait(json.loads(response.read_text()))
            assert panel["summary"]["move"] == 1, panel
            await wait(
                await call("organize_project_assets", mode="apply", plan_id=panel["plan_id"])
            )
            await wait(await call("organize_project_assets", mode="undo", plan_id=panel["plan_id"]))
            folder = target.root / "PipelineInbox"
            folder.mkdir(exist_ok=True)
            incoming = folder / ("fixture_" + str(int(time.time())) + ".glb")
            shutil.copyfile(repo / ".local/v05-fixtures/fixture.glb", incoming)
            os.utime(incoming, (time.time() - 10,) * 2)
            await call("project_conventions", mode="save", settings={"intake": {"enabled": True}})
            for _ in range(150):
                entries = (await call("manage_asset_inbox"))["entries"]
                if incoming.name in entries:
                    break
                await anyio.sleep(0.3)
            assert incoming.name in entries, "Automatic watcher did not register source"
            imported = await wait(entries[incoming.name]["task"])
            assert imported["import_result"]["status"] == "imported"
            layout = json.loads((root / "locations" / (imported["asset_id"] + ".json")).read_text())
            assert layout["model"].startswith("Models/Mesh_")
            repeated = await call("manage_asset_inbox", mode="scan")
            assert not repeated["tasks"], "Unchanged source was imported twice"
            await call("project_conventions", mode="save", settings={"intake": {"enabled": False}})
            print(
                "PASS",
                engine,
                "profile, native panel IPC, intake, semantic evidence/search, "
                "selective material apply/undo",
                flush=True,
            )

    anyio.run(run)


if __name__ == "__main__":
    main()
