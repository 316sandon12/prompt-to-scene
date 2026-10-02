import json

import pytest

from prompt_to_scene import core, development, levels, project_library, registry, workbench


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "Project"
    (root / "Assets").mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    monkeypatch.setenv("PTS_PROJECT", str(root))
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    return root


def envelope(project, task):
    value = json.loads(
        (core.state_root(project) / "actions" / (task["request_id"] + ".json")).read_text()
    )
    assert value["operation"] == "develop"
    return value, json.loads(value["development_json"])


@pytest.mark.parametrize("engine", ["unity", "unreal"])
def test_level_connects_room_stair_upper_landing_in_engine_units(engine):
    plan = levels.plan(
        engine,
        modules=[
            dict(cell=[0, 0, 0], kind="room"),
            dict(cell=[0, 1, 0], kind="stair", direction=2),
            dict(cell=[0, 2, 1], kind="room"),
        ],
    )
    assert plan["reachable_modules"] == [0, 1, 2]
    assert len(plan["connections"]) == 2
    up = 1 if engine == "unity" else 2
    assert max(p["position"][up] for p in plan["checkpoints"]) == pytest.approx(3.025)
    steps = [b for b in plan["boxes"] if b["name"].startswith("stair")]
    assert len(steps) == 14
    assert all(b["size"][up] > 0 for b in steps)
    assert max(b["position"][up] + b["size"][up] / 2 for b in steps) == pytest.approx(3)


@pytest.mark.parametrize(
    "settings,match",
    [
        (
            {"modules": [dict(cell=[0, 0, 0], kind="room"), dict(cell=[3, 0, 0], kind="room")]},
            "Disconnected",
        ),
        ({"door_width": 0.6}, "clearance"),
        ({"door_height": 1.8}, "clearance"),
        ({"modules": [dict(cell=[0, 0, 0], kind="stair", direction=2)]}, "stair ends"),
        (
            {"modules": [dict(cell=[0, 0, 0], kind="room"), dict(cell=[0, 0, 0], kind="corridor")]},
            "same grid",
        ),
        ({"modules": [dict(cell=[0, 0, 0], kind="room", direction=90)]}, "Direction"),
        ({"yaw": float("nan")}, "Yaw"),
        ({"player_radius": 0.8, "player_height": 1.2}, "diameter"),
    ],
)
def test_invalid_levels_fail_before_native_mutation(project, settings, match):
    with pytest.raises(ValueError, match=match):
        levels.build(None, "test", **settings)
    assert not (core.state_root(project) / "actions").exists()


def test_level_plan_is_read_only_and_native_build_has_same_geometry(project):
    plan = levels.build(None, "room", mode="plan", yaw=37, position=[5, 0, 9])
    assert not (core.state_root(project) / "actions").exists()
    task = levels.build(None, "room", yaw=37, position=[5, 0, 9])
    _, request = envelope(project, task)
    assert request["boxes"] == plan["boxes"]
    assert request["checkpoints"] == plan["checkpoints"]


def test_native_interaction_and_protection_contract(project):
    task = development.configure(None, "door", "door", "leaf", pivot=[-0.6, 0, 0], distance=3.5)
    e, c = envelope(project, task)
    assert e["scope"] == "asset" and c["moving_asset_id"] == "leaf" and c["distance"] == 3.5
    with pytest.raises(ValueError, match="separate"):
        development.configure(None, "door", "door", "door")
    with pytest.raises(ValueError, match="requires|needs"):
        development.configure(None, "door", "chest")
    with pytest.raises(ValueError, match="unique"):
        development.protection(
            None, "door", bindings=[dict(slot="Body", material_path="Assets/a.mat")] * 2
        )
    task = workbench.dispatch(
        "protection",
        dict(asset_id="door", mode="set", sockets=[dict(name="handle", position=[1, 0, 1])]),
    )
    _, c = envelope(project, task)
    assert c["sockets"][0]["rotation"] == [0, 0, 0]


def test_candidate_review_uses_retained_manifest_not_current_native_success(project):
    candidate = "a" * 32
    path = core.state_root(project) / "work/door" / candidate / "request.json"
    core.atomic_json(
        path, dict(asset_id="door", materials=[dict(name="NewSlot")], object_names=["FrameLeft"])
    )
    task = development.review_update(None, "door", candidate)
    _, c = envelope(project, task)
    assert c["slots"] == ["NewSlot"]
    assert c["object_names"] == ["FrameLeft"]
    with pytest.raises(ValueError, match="finished"):
        development.review_update(None, "door", "b" * 32)


def test_playcheck_is_bounded_and_keeps_explicit_asset_scope(project):
    with pytest.raises(ValueError, match="Choose"):
        development.playcheck(None)
    with pytest.raises(ValueError, match="duration"):
        development.playcheck(None, ["door"], duration=30)
    _, c = envelope(project, development.playcheck(None, ["door", "door"], duration=2))
    assert c["asset_ids"] == ["door"] and c["duration"] == 2


def test_library_ranks_chinese_aliases_saved_tags_size_and_unknown_license():
    entries = [
        dict(path="Assets/box.prefab", name="wood_crate", size=[1, 1, 1]),
        dict(path="Assets/door.prefab", name="wood_door", size=[1, 2, 0.2]),
        dict(path="Assets/stone.prefab", name="stone", size=[1, 1, 1]),
    ]
    found = project_library.rank(entries, "木门", size=2)
    assert found[0]["name"] == "wood_door"
    assert "Unknown" in found[0]["license"]
    annotations = {"Assets/stone.prefab": dict(tags=["cozy"], license="CC0-1.0")}
    found = project_library.rank(entries, "cozy", annotations)
    assert found[0]["path"] == "Assets/stone.prefab" and found[0]["license"] == "CC0-1.0"


def test_library_indexes_native_then_resolves_saved_annotations_without_resubmitting(project):
    task = project_library.search(None, "cozy")
    _, data = envelope(project, task)
    assert data["mode"] == "index"
    core.atomic_json(
        core.state_root(project) / "action-receipts" / (task["request_id"] + ".json"),
        dict(
            status="completed",
            request_id=task["request_id"],
            development=dict(
                command="library", entries=[dict(path="Assets/door.prefab", name="Door")]
            ),
        ),
    )
    project_library.annotate(None, "Assets/door.prefab", tags=["cozy"])
    result = project_library.search(None, "cozy", task["request_id"])
    assert len(result["development"]["entries"]) == 1
    assert len(list((core.state_root(project) / "actions").glob("*.json"))) == 1
    with pytest.raises(ValueError, match="inside"):
        project_library.reuse(None, "Assets/../../secret", mode="preview")


def test_install_includes_runtime_interaction_and_ue_blueprint(project, tmp_path):
    registry.install(registry.resolve(str(project)))
    assert (project / "Packages/com.prompttoscene.bridge/Runtime/Interaction.cs").is_file()
    ue = tmp_path / "Unreal"
    ue.mkdir()
    (ue / "Test.uproject").write_text('{"FileVersion":3}')
    registry.install(registry.resolve(str(ue)))
    assert (
        ue / "Plugins/PromptToScene/Content/Templates/BP_PTSInteraction.uasset"
    ).stat().st_size > 1000
    assert not (ue / "Plugins/PromptToScene/Source").exists()


def test_resume_interactive_retries_failed_children_but_keeps_imported_mesh(project, monkeypatch):
    from prompt_to_scene import workflow

    class Job:
        id = "e" * 32
        root = core.state_root(project)
        state = {
            "base_task": {"request_id": "a" * 32},
            "moving_task": {"request_id": "b" * 32},
            "configure_task": {"request_id": "c" * 32},
        }

        def update(self, **values):
            self.state.update(values)

        def track(self, task):
            return task

        def wait(self, task):
            return {**task, "status": "completed"}

    job = Job()
    job.project = str(project)
    monkeypatch.setattr(
        workflow,
        "job_status",
        lambda p, r: {"status": {"a": "error", "b": "imported", "c": "cancelled"}[r[0]]},
    )
    builds, config = [], []
    monkeypatch.setattr(
        workflow, "submit", lambda *args: builds.append(args[1]) or {"request_id": "d" * 32}
    )
    monkeypatch.setattr(
        development, "configure", lambda *a, **kw: config.append(kw) or {"request_id": "f" * 32}
    )
    development.run_interactive(job, "door", "door", [1.2, 0.14, 2.2], None, [0.3, 0.1, 0.05])
    assert builds == ["door"]
    assert config[0]["preserve_configuration"]
    assert config[0]["pivot"] == [0.6, 0, 0] and config[0]["moving_offset"] == [-0.6, 0, 0]


def test_workbench_retains_last_imported_asset_and_native_play_result(project, monkeypatch):
    from prompt_to_scene import setup

    root = core.state_root(project)
    success = dict(asset_id="door", request_id="a" * 32, status="imported")
    core.atomic_json(root / "history/door" / ("a" * 32 + ".json"), success)
    core.atomic_json(
        root / "receipts/door.json", dict(asset_id="door", request_id="b" * 32, status="error")
    )
    core.atomic_json(root / "receipts/door_moving.json", {**success, "asset_id": "door_moving"})
    core.atomic_json(root / "interactions/door.json", dict(moving_asset_id="door_moving"))
    core.atomic_json(
        root / "action-receipts" / ("c" * 32 + ".json"),
        dict(
            request_id="c" * 32,
            status="completed",
            development=dict(command="playcheck", passed=True),
        ),
    )
    monkeypatch.setattr(setup.clients, "inventory", lambda: {})
    monkeypatch.setattr(setup.registry, "discover", lambda: [])
    monkeypatch.setattr(setup.registry, "find_blender", lambda: None)
    state = setup.state()
    assert state["assets"] == [success]
    assert state["tasks"][0]["development"]["passed"]


def test_project_asset_provenance_survives_empty_annotation(project):
    root = core.state_root(project)
    revision, index = "a" * 32, "b" * 32
    core.atomic_json(
        root / "history/vase" / (revision + ".json"), dict(status="imported", request_id=revision)
    )
    core.atomic_json(
        root / "work/vase" / revision / "asset.json",
        dict(provenance=dict(license="CC0-1.0", url="https://polyhaven.com/a/example")),
    )
    core.atomic_json(
        root / "action-receipts" / (index + ".json"),
        dict(
            status="completed",
            development=dict(
                command="library",
                entries=[
                    dict(asset_id="vase", name="vase", path="Assets/vase.prefab", tags=["ceramic"])
                ],
            ),
        ),
    )
    project_library.annotate(None, "Assets/vase.prefab", tags=["cozy"])
    entry = project_library.search(None, "cozy", index)["development"]["entries"][0]
    assert entry["license"] == "CC0-1.0"
    assert entry["tags"] == ["ceramic", "cozy"]
    assert entry["source"].startswith("https://polyhaven.com/")


def test_play_screenshots_are_available_to_normal_mcp_clients(project):
    import asyncio

    from prompt_to_scene import server

    root, request_id = core.state_root(project), "d" * 32
    screenshots = ["previews/" + request_id + suffix + ".png" for suffix in ("", "_before")]
    for path in screenshots:
        file = root / path
        file.parent.mkdir(exist_ok=True, parents=True)
        file.write_bytes(b"PNG fixture")
    core.atomic_json(
        root / "action-receipts" / (request_id + ".json"),
        dict(status="completed", development=dict(command="playcheck", screenshots=screenshots)),
    )
    assert asyncio.run(server.get_preview(request_id=request_id)).data == b"PNG fixture"
    assert (
        asyncio.run(server.get_preview(request_id=request_id, view="before")).data == b"PNG fixture"
    )
    core.atomic_json(
        root / "action-receipts" / (request_id + ".json"),
        dict(status="completed", development=dict(command="playcheck", screenshots=[])),
    )
    with pytest.raises(ValueError, match="not a preview"):
        asyncio.run(server.get_preview(request_id=request_id))
