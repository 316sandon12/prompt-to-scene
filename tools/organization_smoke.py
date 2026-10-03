"""Run native scan/plan/rename/reference checks, restart the editor and undo via real MCP."""

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from prompt_to_scene import core, registry


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
    prefix = "Assets" if target.engine == "unity" else "/Game"
    folder = prefix + "/OrganizationSmoke_" + str(int(time.time()))
    destination = prefix + "/OrganizationOutput_" + str(int(time.time()))
    fixture = dict(folder=folder, destination=destination, fresh=True)
    evidence = []
    if target.engine == "unity":
        shutil.copyfile(
            repo / "tools/UnityOrganization.cs", target.root / "Assets/Editor/UnityOrganization.cs"
        )
        command = [
            args.editor,
            "-batchmode",
            "-projectPath",
            str(target.root),
            "-executeMethod",
            "UnityOrganization.Run",
            "-logFile",
            str(target.root / "organization.log"),
        ]
    else:

        def chunk(kind, data):
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data))
            )

        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
        png += chunk(
            b"IDAT", zlib.compress(b"\0" + b"\xcc\x88\x44" * 2 + b"\0" + b"\xcc\x88\x44" * 2)
        ) + chunk(b"IEND", b"")
        (root / "organization-texture.png").write_bytes(png)
        command = [
            args.editor,
            str(target.project_file),
            "-unattended",
            "-nop4",
            "-nosound",
            "-RenderOffscreen",
            "-ExecutePythonScript=" + str(repo / "tools/unreal_organization_driver.py"),
            "-abslog=" + str(target.root / "organization.log"),
        ]

    async def exercise(client, phase, plan_id=None):
        async def call(name, values):
            result = await client.call_tool(name, values)
            assert not result.isError, result
            data = result.structuredContent or json.loads(result.content[0].text)
            evidence.append(dict(tool=name, result=data))
            (target.root / "organization-evidence.json").write_text(json.dumps(evidence, indent=2))
            print(name, values.get("mode", ""), data.get("status", "ok"), flush=True)
            return data

        async def wait(task, expected="completed"):
            for _ in range(20):
                result = await call(
                    "get_task_status", dict(request_id=task["request_id"], wait_seconds=30)
                )
                if result["status"] in {"error", "completed", "cancelled"}:
                    assert result["status"] == expected, result
                    return result
            raise AssertionError("Native organization timed out")

        async def native(operation, **values):
            (root / "organization-command-done").unlink(missing_ok=True)
            core.atomic_json(
                root / "organization-command.json", dict(operation=operation, **values)
            )
            if operation == "save_stop":
                return
            for _ in range(300):
                error = root / "organization-error.txt"
                assert not error.exists(), error.read_text() if error.exists() else ""
                if (root / "organization-command-done").exists():
                    return
                await anyio.sleep(0.1)
            raise AssertionError("Native fixture command timed out: " + operation)

        async def preview(scope=folder):
            task = await call("organize_project_assets", dict(mode="scan", scope=scope))
            await wait(task)
            return await call(
                "organize_project_assets",
                dict(
                    mode="plan", scan_id=task["request_id"], settings=dict(destination=destination)
                ),
            )

        if phase == 0:
            stale = await preview()
            assert stale["summary"]["move"] >= 14, stale["summary"]
            assert stale["summary"]["skip"] >= 1
            assert stale["summary"]["collisions_resolved"] >= 2
            await native("mutate")
            rejected = await wait(
                await call("organize_project_assets", dict(mode="apply", plan_id=stale["plan_id"])),
                "error",
            )
            assert "changed since preview" in rejected["error"], rejected
            await native("check_restored")
            cancelled_plan = await preview()
            await native("cancel_after_moves", plan_id=cancelled_plan["plan_id"])
            cancelled = await wait(
                await call(
                    "organize_project_assets", dict(mode="apply", plan_id=cancelled_plan["plan_id"])
                ),
                "cancelled",
            )
            assert cancelled["development"]["organization_status"] == "cancelled", cancelled
            cancelled_journal = core.read_optional_json(
                root / "organization/journals" / (cancelled_plan["plan_id"] + ".json")
            )
            assert len(cancelled_journal["events"]) >= 2, "Cancellation must follow actual moves"
            assert all(e["current"] == e["source"] for e in cancelled_journal["entries"])
            await native("check_restored")
            plan = await preview()
            original = next(r for r in plan["entries"] if r["kind"] == "model")["source"]
            await call(
                "tag_project_asset",
                dict(
                    path=original,
                    tags=["organization-fixture"],
                    license="fixture",
                    notes="retained credit",
                ),
            )
            applied = await wait(
                await call("organize_project_assets", dict(mode="apply", plan_id=plan["plan_id"]))
            )
            assert applied["development"]["changed"] == plan["summary"]["move"]
            again = await wait(
                await call("organize_project_assets", dict(mode="apply", plan_id=plan["plan_id"]))
            )
            assert again["development"]["changed"] == 0
            annotations = core.read_optional_json(root / "project-library.json")
            moved = next(r for r in plan["entries"] if r["source"] == original)["destination"]
            assert annotations[moved]["notes"] == "retained credit" and original not in annotations
            await native("check_moved")
            second = await preview(destination)
            assert second["summary"]["move"] == 0, second
            await native("save_stop")
            return plan["plan_id"]
        await native("check_moved")
        await native("block_undo")
        blocked = await wait(
            await call("organize_project_assets", dict(mode="undo", plan_id=plan_id)), "error"
        )
        assert "occupied" in blocked["error"], blocked
        await native("check_moved")
        await native("unblock_undo")
        await wait(await call("organize_project_assets", dict(mode="undo", plan_id=plan_id)))
        await native("check_restored")
        record = await call("organize_project_assets", dict(mode="inspect", plan_id=plan_id))
        assert record["status"] == "undone"
        await native("save_stop")
        return plan_id

    async def run():
        plan_id = None
        for phase in range(2):
            fixture["fresh"] = phase == 0
            core.atomic_json(root / "organization-fixture.json", fixture)
            for file in (
                "organization-ready",
                "organization-error.txt",
                "organization-command.json",
                "organization-command-done",
            ):
                (root / file).unlink(missing_ok=True)
            with (target.root / ("organization-console-" + str(phase) + ".log")).open("w") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                try:
                    for _ in range(1800):
                        if (root / "organization-ready").exists():
                            break
                        if process.poll() is not None:
                            raise AssertionError(
                                "Editor exited before fixture ready; see organization.log"
                            )
                        await anyio.sleep(0.1)
                    else:
                        raise AssertionError("Editor did not become ready")
                    params = StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "prompt_to_scene.app", "--mcp"],
                        env={
                            **os.environ,
                            "PTS_PROJECT": str(target.project_file or target.root),
                            "PTS_HOME": str(root / "organization-home"),
                        },
                    )
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as client:
                            await client.initialize()
                            plan_id = await exercise(client, phase, plan_id)
                    for _ in range(900):
                        if process.poll() is not None:
                            break
                        await anyio.sleep(0.1)
                    assert process.poll() == 0, process.poll()
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=30)
        print(
            "PASS: native naming/classification, collisions, stale-plan rejection, "
            "references, partial-work cancellation/rollback, restart and undo",
            flush=True,
        )

    anyio.run(run)


if __name__ == "__main__":
    main()
