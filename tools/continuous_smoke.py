"""v0.15 verification against an isolated, already-open Unity fixture under .local."""

import json
import os
import time
from pathlib import Path

from prompt_to_scene import (
    art_directions,
    core,
    creative_tasks,
    delivery,
    gameplay,
    linked_updates,
    project_adapters,
    workflow,
)

repo = Path(__file__).resolve().parents[1]
base = repo / ".local/iteration-v15"
os.environ["PTS_HOME"] = str(base / "home")
project = str(base / "unity")
root = Path(project) / ".prompt-to-scene"


def until(check, timeout=1200):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (root / "continuous-error.txt").exists():
            raise AssertionError((root / "continuous-error.txt").read_text())
        result = check()
        if result:
            return result
        time.sleep(0.3)
    raise TimeoutError("Native verification stage timed out")


def wait(task):
    def check():
        result = workflow.job_status(project, task["request_id"])
        if result["status"] in workflow.TERMINAL:
            assert result["status"] in {"completed", "imported"}, result
            return result

    result = until(check)
    print(result.get("stage", "Native action complete"), flush=True)
    return result


def command(operation, marker):
    path = root / ("continuous-" + marker)
    path.unlink(missing_ok=True)
    core.atomic_json(root / "continuous-command.json", dict(operation=operation))
    until(path.exists)


tasks = core.read_optional_json(base / "native-tasks.json")
if not tasks:
    context = creative_tasks.context(project)
    plan = creative_tasks.save(
        project,
        "Orbital fabrication station",
        "Make a coherent orbital workshop with inventory and crafting.",
        [
            dict(
                id="kit",
                action="create_art_kit",
                values=dict(prefix="apothecary", kit_id="orbital_workshop"),
                reason="Build seven matching models, three item icons, screens and gameplay",
            )
        ],
        context["context_token"],
    )
    wait(creative_tasks.execute(project, plan["plan_id"], plan["revision"]))
    before = linked_updates.dependencies(project, "apothecary_potion_model")
    plan = linked_updates.plan(
        project, "apothecary_potion_model", next(iter(before["parts"])), {"roughness": 0.65}
    )
    tasks = dict(
        linked=linked_updates.execute(project, plan["update_id"]),
        update_id=plan["update_id"],
        drafts=art_directions.preview(project),
    )
    core.atomic_json(base / "native-tasks.json", tasks)
wait(tasks["linked"])
updated = next(
    r for r in linked_updates.catalog(project)["updates"] if r["update_id"] == tasks["update_id"]
)
assert updated["before"]["model_revision"] != updated["after"]["model_revision"]
assert updated["before"]["items"][0]["item_id"] == updated["after"]["items"][0]["item_id"]
wait(linked_updates.execute(project, tasks["update_id"], undo=True))
restored = next(
    r for r in linked_updates.catalog(project)["updates"] if r["update_id"] == tasks["update_id"]
)
assert (
    restored["restored"]["items"][0]["icon_revision"]
    == restored["before"]["items"][0]["icon_revision"]
)
drafts = wait(tasks["drafts"])
assert len(drafts["candidates"]) == 3
for draft in drafts["candidates"]:
    assert (root / "work" / draft["asset_id"] / draft["request_id"] / "studio.png").is_file()
command("provider", "provider-ready")
inspection = wait(project_adapters.inspect_system(project, "apothecary"))
scan = json.loads(inspection["development"]["plan_json"])
provider = next(p for p in scan["providers"] if p["type"] == "FixtureInventory")
plan = project_adapters.prepare(
    project,
    inspection["request_id"],
    provider["target"],
    dict(health="CurrentHealth", max_health="MaximumHealth"),
)
assert not plan["questions"], plan
wait(project_adapters.install(project, plan["adapter_id"]))
command("adapter", "adapter-passed")
command("second_scene", "second-ready")
wait(gameplay.attach(project, "apothecary"))
command("travel", "travel-passed")
until(lambda: not core.read_optional_json(root / "editor.json").get("playing", False), 60)
command("save", "saved")
built = wait(delivery.build(project, ["Assets/ContinuousA.unity", "Assets/ContinuousB.unity"]))
core.atomic_json(
    base / "unity-evidence.json",
    dict(
        engine="Unity 2022.3.62f3c1 Built-in",
        linked_update=True,
        undo=True,
        actual_direction_previews=drafts["candidates"],
        generated_adapter=plan["adapter_id"],
        atomic_rejection=True,
        migrated_old_save=True,
        backup=True,
        cross_scene_without_autosave=True,
        delivery=built["delivery"],
    ),
)
print("UNITY CONTINUOUS CHECKS PASSED", flush=True)
