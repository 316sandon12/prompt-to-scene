import json
from copy import deepcopy

import pytest

from prompt_to_scene import (
    art_directions,
    art_kits,
    art_samples,
    background,
    core,
    creative_tasks,
    delivery,
    game_art,
    gameplay,
    linked_updates,
    production,
    project_adapters,
    registry,
    workflow,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PTS_PROJECT", raising=False)
    monkeypatch.delenv("PTS_UNITY_PROJECT", raising=False)
    folder = tmp_path / "Game"
    (folder / "Assets").mkdir(parents=True)
    (folder / "ProjectSettings").mkdir()
    registry.connect(str(folder), install_bridge=False)
    return folder


def test_task_rejects_stale_context_cross_project_and_missing_decisions(project, monkeypatch):
    token = creative_tasks.context(project)["context_token"]
    assert creative_tasks.context(project)["context_token"] == token
    step = dict(
        id="set",
        action="create_art_kit",
        values=dict(prefix="camp"),
        reason="Create a coherent playable camp",
    )
    plan = creative_tasks.save(
        project, "Camp", "Build a camp", [step], token, ["Which player view?"]
    )
    with pytest.raises(ValueError, match="missing decisions"):
        creative_tasks.execute(project, plan["plan_id"], plan["revision"])
    with pytest.raises(ValueError, match="task's project"):
        creative_tasks.save(project, "Camp", "", [{**step, "values": {"project": "other"}}], token)
    plan = creative_tasks.save(project, "Camp", "Build a camp", [step], token)
    art_directions.select(project, "orbital_workshop")
    with pytest.raises(ValueError, match="Project changed"):
        creative_tasks.execute(project, plan["plan_id"], plan["revision"])
    with pytest.raises(ValueError, match="context changed"):
        creative_tasks.save(project, "Camp", "", [step], token)


def test_task_executes_once_and_reuses_completed_synchronous_steps(project, monkeypatch):
    token = creative_tasks.context(project)["context_token"]
    step = dict(id="kit", action="create_art_kit", values={}, reason="Create set")
    plan = creative_tasks.save(project, "Set", "", [step], token)
    calls = []
    monkeypatch.setattr(
        background,
        "submit",
        lambda *a, **k: calls.append(a) or {"request_id": "a" * 32, "status": "building"},
    )
    monkeypatch.setattr(
        workflow, "job_status", lambda *a, **k: {"request_id": "a" * 32, "status": "building"}
    )
    creative_tasks.execute(project, plan["plan_id"], plan["revision"])
    creative_tasks.execute(project, plan["plan_id"], plan["revision"])
    assert len(calls) == 1

    class Job:
        state = {}
        project = None

        def check(self):
            pass

        def update(self, **kwargs):
            self.state.update(kwargs)

    job = Job()
    monkeypatch.setattr(
        production,
        "routes",
        lambda: {"create_art_kit": lambda *a, **k: {"status": "completed", "prefix": "existing"}},
    )
    assert creative_tasks.run(job, plan)["results"][0]["status"] == "completed"
    monkeypatch.setattr(production, "routes", lambda: {})
    assert creative_tasks.run(job, plan)["results"][0]["status"] == "completed"


def test_direction_sources_are_compilable_and_theme_does_not_change_project(project):
    original = art_samples.theme(project)
    for kit in art_directions.DIRECTIONS:
        for kind in art_kits.PARTS:
            compile(art_directions.source(kit, kind, {"accent": "#112233"}), kit + kind, "exec")
    selected = art_directions.select(project, "wasteland_workshop", {"accent": "#AABBCC"})
    assert selected["theme"]["accent"] == "#AABBCC"
    assert art_samples.theme(project) == original
    with pytest.raises(ValueError):
        art_directions.select(project, "orbital_workshop", {"accent": "red"})


def test_save_aliases_require_unambiguous_current_destinations(project):
    spec = art_kits.rule_settings("camp")
    spec.update(
        save_version=2,
        item_aliases=[dict(from_id="old_medkit", to_id="camp_potion")],
        rule_aliases=[dict(from_id="old_pickup", to_id="collect_herb")],
    )
    assert gameplay.validate(spec)["save_version"] == 2
    for aliases in (
        [dict(from_id="camp_herb", to_id="camp_potion")],
        [dict(from_id="old", to_id="missing")],
        [dict(from_id="old", to_id="camp_potion"), dict(from_id="older", to_id="camp_potion")],
    ):
        with pytest.raises(ValueError):
            gameplay.validate({**spec, "item_aliases": aliases})
    with pytest.raises(ValueError):
        gameplay.validate({**spec, "persist_on_travel": "yes"})


def test_linked_update_conflicts_and_shared_icon_protection(project, monkeypatch):
    root = game_art.root(project)
    model = {
        "current": {"status": "imported", "request_id": "a" * 32},
        "metadata": {"report": {"parts": {"body": {"locks": {}}}}},
    }
    monkeypatch.setattr(workflow, "inspect_asset", lambda *a: deepcopy(model))
    item = dict(
        item_id="potion", model_asset_id="bottle", icon_asset_id="potion_icon", revision="b" * 32
    )
    core.atomic_json(root / "game-items/potion.json", item)
    core.atomic_json(root / "image-receipts/potion_icon.json", dict(revision="c" * 32))
    core.atomic_json(
        root / "game-screens/inventory.json",
        dict(screen_id="inventory", item_ids=["potion"], revision="d" * 32),
    )
    plan = linked_updates.plan(project, "bottle", "body", {"roughness": 0.3})
    assert len(plan["before"]["screens"]) == 1
    core.atomic_json(root / "game-items/potion.json", {**item, "revision": "e" * 32})
    with pytest.raises(ValueError, match="changed"):
        linked_updates.execute(project, plan["update_id"])
    core.atomic_json(
        root / "game-items/other.json", {**item, "item_id": "other", "model_asset_id": "other"}
    )
    with pytest.raises(ValueError, match="shared"):
        linked_updates.plan(project, "bottle", "body", {"roughness": 0.3})
    assert linked_updates.plan(project, "bottle", "body", {"roughness": 0.3}, False)


def test_adapter_requires_actual_public_api_and_no_private_guessing(project, monkeypatch):
    provider = dict(
        target="native-id",
        type="Inventory",
        compatible=False,
        quantity=["Count"],
        health=["HP", "MaxHP"],
        max_health=["HP", "MaxHP"],
        commit=["Commit"],
    )
    monkeypatch.setattr(
        workflow,
        "job_status",
        lambda *a, **k: dict(
            status="completed",
            development={"plan_json": json.dumps(dict(flow_id="camp", providers=[provider]))},
        ),
    )
    plan = project_adapters.prepare(project, "a" * 32, "native-id")
    assert len(plan["questions"]) == 2 and plan["mapping"]["commit"] == "Commit"
    with pytest.raises(ValueError, match="missing interfaces"):
        project_adapters.install(project, plan["adapter_id"])
    plan = project_adapters.prepare(
        project, "a" * 32, "native-id", dict(health="HP", max_health="MaxHP")
    )
    assert not plan["questions"]
    with pytest.raises(ValueError):
        project_adapters.prepare(project, "a" * 32, "uninspected")


def test_delivery_cleanup_preserves_player_and_refuses_active_or_unowned(project, monkeypatch):
    name = "a" * 32
    root = project / ".local/pts-deliveries" / name
    core.atomic_json(root / "owner.json", dict(request_id=name))
    (root / "build.log").write_text("log")
    (root / "Player.app").mkdir()
    (root / "Player.app/game").write_text("runtime")
    monkeypatch.setattr(workflow, "job_status", lambda *a: dict(status="building"))
    with pytest.raises(ValueError):
        delivery.cleanup(project, name)
    monkeypatch.setattr(workflow, "job_status", lambda *a: dict(status="completed"))
    assert delivery.cleanup(project, name)["removed_bytes"] == 3
    assert (root / "Player.app/game").read_text() == "runtime"


class DeliveryJob:
    id = "f" * 32

    def __init__(self, project):
        self.project = project
        self.root = game_art.root(project)
        self.state = {}

    def update(self, **kwargs):
        self.state.update(kwargs)

    def check(self):
        pass


def test_unity_delivery_preserves_native_player_path_and_platform(project, monkeypatch):
    job = DeliveryJob(project)
    native = dict(engine="unity", output="Player.app", platform="StandaloneOSX", built=True)
    monkeypatch.setattr(
        delivery.creations,
        "step",
        lambda *a: dict(development=dict(plan_json=json.dumps(native))),
    )
    receipt = delivery.run(job, ["Assets/Main.unity"], True)["delivery"]
    assert receipt["output"] == native["output"]
    assert receipt["platform"] == native["platform"]
    assert receipt["runtime_verified"] is False


def test_ue_delivery_requires_actual_game_executable_and_keeps_its_data(project, monkeypatch):
    from types import SimpleNamespace

    job = DeliveryJob(project)
    target = SimpleNamespace(root=project, project_file=project / "Game.uproject", engine="unreal")
    monkeypatch.setattr(registry, "resolve", lambda *a: target)
    monkeypatch.setattr(delivery.sys, "platform", "darwin")
    engine = project / "Engine"
    uat = engine / "Build/BatchFiles/RunUAT.sh"
    uat.parent.mkdir(parents=True)
    uat.touch()
    native = dict(engine="unreal", engine_root=str(engine), scenes=["/Game/Main"])
    monkeypatch.setattr(
        delivery.creations,
        "step",
        lambda *a: dict(development=dict(plan_json=json.dumps(native))),
    )

    class Finished:
        pid = 123
        returncode = 0

        def __init__(self, *args, **kwargs):
            pass

        def poll(self):
            return 0

    monkeypatch.setattr(delivery.subprocess, "Popen", Finished)
    root = project / ".local/pts-deliveries" / job.id
    reporter = root / "staging/Mac/CrashReportClient.app/Contents/MacOS/CrashReportClient"
    reporter.parent.mkdir(parents=True)
    reporter.write_bytes(b"crash reporter is not the game")
    with pytest.raises(RuntimeError, match="did not stage a player executable"):
        delivery.run(job, ["/Game/Main"], True)
    assert not (job.root / "deliveries" / (job.id + ".json")).exists()
    executable = root / "staging/Mac/Game.app/Contents/MacOS/Game"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"game executable")
    data = root / "staging/Mac/Game/Content/Paks/Game.pak"
    data.parent.mkdir(parents=True)
    data.write_bytes(b"packaged game data")
    receipt = delivery.run(job, ["/Game/Main"], True)["delivery"]
    assert receipt["entrypoint"] == str(root / "player/Mac/Game.app/Contents/MacOS/Game")
    assert (root / "player/Mac/Game/Content/Paks/Game.pak").read_bytes() == b"packaged game data"
    assert not (root / "staging").exists()
    assert receipt["built"] and receipt["runtime_verified"] is False


def test_launch_rejects_unowned_paths_and_opens_packaged_ue_map(project, monkeypatch):
    from types import SimpleNamespace

    name = "e" * 32
    root = project / ".local/pts-deliveries" / name
    receipt_path = game_art.root(project) / "deliveries" / (name + ".json")
    executable = root / "player/Game"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"player")
    receipt = dict(built=True, engine="unreal", entrypoint=str(executable), scenes=["/Game/Main"])
    core.atomic_json(receipt_path, receipt)
    with pytest.raises(ValueError, match="completed player"):
        delivery.launch(project, name)
    core.atomic_json(root / "owner.json", dict(request_id=name))
    core.atomic_json(receipt_path, {**receipt, "entrypoint": str(project / "outside")})
    with pytest.raises(ValueError, match="outside"):
        delivery.launch(project, name)
    core.atomic_json(receipt_path, receipt)
    calls = []
    monkeypatch.setattr(
        delivery.subprocess,
        "Popen",
        lambda args, **kwargs: calls.append(args) or SimpleNamespace(pid=1234),
    )
    result = delivery.launch(project, name)
    assert calls[0][:2] == [str(executable), "/Game/Main"]
    assert result["pid"] == 1234 and result["runtime_verified"] is False
    assert core.read_optional_json(root / "launch.json")["executable"] == str(executable)
