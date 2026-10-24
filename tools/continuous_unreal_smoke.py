"""Verify v0.15 with the normal Blueprint-only UE plugin and an actual packaged player."""

import json
import os
import time
from pathlib import Path

from prompt_to_scene import art_kits, core, delivery, gameplay, project_adapters, workflow

base = Path(__file__).resolve().parents[1] / ".local/iteration-v15"
os.environ["PTS_HOME"] = str(base / "home")
project = str(base / "unreal/Continuous.uproject")
root = base / "unreal/.prompt-to-scene"


def until(check, timeout=1200):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for name in ("continuous-error.txt", "gameplay-error.txt"):
            if (root / name).exists():
                raise AssertionError((root / name).read_text())
        result = check()
        if result:
            return result
        time.sleep(0.3)
    raise TimeoutError("UE verification timed out")


def wait(task):
    def check():
        row = workflow.job_status(project, task["request_id"])
        if row["status"] in workflow.TERMINAL:
            assert row["status"] == "completed", row
            return row

    result = until(check)
    print(result.get("stage", "Native UE action complete"), flush=True)
    return result


def command(operation, marker):
    path = root / ("continuous-" + marker)
    path.unlink(missing_ok=True)
    core.atomic_json(root / "continuous-command.json", dict(operation=operation))
    until(path.exists)


# The legacy suite also proves old flows/UI work with the newly compiled parent templates.
if not (root / "art-kits/apothecary.json").exists():
    wait(art_kits.create(project, kit_id="wasteland_workshop"))
command("save", "saved")
(root / "gameplay-command-done").unlink(missing_ok=True)
core.atomic_json(root / "gameplay-command.json", dict(operation="play"))
until((root / "gameplay-command-done").exists)
assert (root / "gameplay-play-passed").exists()
print("Native UI, atomic gameplay and foreign-save checks passed", flush=True)
command("provider", "provider-ready")
inspection = wait(project_adapters.inspect_system(project, "apothecary"))
provider = json.loads(inspection["development"]["plan_json"])["providers"][0]
plan = project_adapters.prepare(project, inspection["request_id"], provider["target"])
assert not plan["questions"]
wait(project_adapters.install(project, plan["adapter_id"]))
command("adapter", "adapter-passed")
command("second_scene", "second-ready")
wait(gameplay.attach(project, "apothecary"))
command("travel", "travel-passed")
command("save", "saved")
build = wait(delivery.build(project, ["/Game/GameplayFixture", "/Game/ContinuousB"]))
core.atomic_json(
    base / "unreal-evidence.json",
    dict(
        engine="UE 5.7.2",
        normal_plugin_only=True,
        legacy_gameplay=True,
        adapter_binding=True,
        save_migration=True,
        migration_backup=True,
        level_travel=True,
        delivery=build["delivery"],
    ),
)
print("UNREAL CONTINUOUS CHECKS PASSED", flush=True)
