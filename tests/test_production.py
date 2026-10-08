import copy
import hashlib
import json
import os
import sys
from types import SimpleNamespace

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from prompt_to_scene import (
    asset_templates,
    authoring,
    background,
    core,
    development,
    game_art,
    levels,
    production,
    project_library,
    recipes,
    registry,
    scene_dressing,
    sources,
    styles,
    visual_feedback,
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


def test_production_validates_whole_batch_before_launch_and_snapshots_design(project, monkeypatch):
    submitted = []
    monkeypatch.setattr(background, "submit", lambda *args: submitted.append(args) or args[2])
    game_art.configure(project, {"world": "herbalist workshop"})
    with pytest.raises(ValueError):
        production.submit(
            project, [dict(asset_id="a", kind="chair"), dict(asset_id="b", method="custom")]
        )
    assert not submitted
    result = production.submit(project, [dict(asset_id="a", kind="chair")])
    game_art.configure(project, {"world": "changed later"})
    assert result["items"][0]["design"]["context"]["world"] == "herbalist workshop"


def test_resume_does_not_rebuild_successful_assets(project, monkeypatch):
    calls = []
    task = dict(request_id="a" * 32, status="imported")
    monkeypatch.setattr(workflow, "job_status", lambda *args: task)
    monkeypatch.setattr(authoring, "submit_recipe", lambda *args: calls.append(args) or task)
    job = SimpleNamespace(
        project=project,
        state={"asset_0": task},
        check=lambda: None,
        track=lambda t: t,
        wait=lambda t: t,
    )
    job.update = lambda **v: job.state.update(v)
    item = dict(asset_id="chair", method="recipe", kind="chair", design={"style": styles.preset()})
    result = production.run(job, [item], "chair", None, None)
    assert not calls and result["assets"][0]["request_id"] == task["request_id"]


def test_changed_source_cannot_silently_replace_the_saved_plan(project, monkeypatch):
    path = project / "fixture.glb"
    path.write_bytes(b"source version one")
    source = sources.validate_source({"path": str(path)})
    path.write_bytes(b"different content")
    with pytest.raises(ValueError, match="Source changed"):
        sources.submit(project, "fixture", source)


def test_gameplay_dependencies_build_before_attachment(project, monkeypatch):
    calls = []
    task = {"request_id": "a" * 32, "status": "imported"}
    monkeypatch.setattr(authoring, "submit_recipe", lambda p, name, *a: calls.append(name) or task)
    monkeypatch.setattr(
        development, "configure", lambda p, name, **v: calls.append("attach") or task
    )
    job = SimpleNamespace(
        project=project, state={}, check=lambda: None, track=lambda t: t, wait=lambda t: t
    )
    job.update = lambda **v: job.state.update(v)
    rows = [
        dict(asset_id=name, method="recipe", kind="crate", design={"style": styles.preset()})
        for name in ("base", "moving")
    ]
    rows[0]["interaction"] = {"kind": "door", "moving_asset_id": "moving"}
    production.run(job, rows, "custom door", None, None)
    assert calls == ["base", "moving", "attach"]


def test_family_is_visible_before_ai_models_next_asset(project):
    core.atomic_json(
        core.state_root(project) / "design-family.json",
        {"name": "workshop", "style": styles.preset("workshop")},
    )
    assert authoring.catalog(project)["project_style"]["preset"] == "workshop"
    brief = game_art.for_recipe(project, "new_chair", "chair")
    assert brief["family"]["name"] == "workshop"
    styles.save(project, "cozy")
    assert authoring.catalog(project)["design_family"] is None


def test_template_is_versioned_retained_and_stale_sources_fail(project, monkeypatch):
    source = project / "source.blend"
    source.write_bytes(b"fixture: packed source")
    _, recipe = recipes.prepare("chair")
    metadata = {"recipe": recipe, "report": {"parts": {"seat": {}}}}
    info = {
        "current": {"status": "imported", "request_id": "a" * 32},
        "source_blend": str(source),
        "metadata": metadata,
        "script": "# fixture",
    }
    monkeypatch.setattr(workflow, "inspect_asset", lambda *a: info)
    first = asset_templates.save(project, "cozy_chair", "chair", "Cozy wood chair", ["wood"])
    source.write_bytes(b"new revision")
    second = asset_templates.save(project, "cozy_chair", "chair")
    assert first["version"] != second["version"]
    saved, path = asset_templates.read(project, "cozy_chair", first["version"])
    assert saved["source_sha256"] == hashlib.sha256(b"fixture: packed source").hexdigest()
    (path / "source.blend").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        asset_templates.read(project, "cozy_chair", first["version"])
    assert asset_templates.read(project, "cozy_chair")[0]["version"] == second["version"]


def test_resource_settings_are_validated_before_editor_requests(project):
    values = development.interaction_values(
        "ore",
        "resource",
        uses=4,
        event_id="ore_mined",
        interaction_point=[0, 0.8, 0],
        depleted_asset_id="rubble",
    )
    assert values["uses"] == 4 and values["depleted_asset_id"] == "rubble"
    for values in (
        {"uses": True},
        {"uses": 0},
        {"event_id": "../escape"},
        {"interaction_point": [0, float("nan"), 0]},
    ):
        with pytest.raises(ValueError):
            development.interaction_values("ore", "resource", **values)
    with pytest.raises(ValueError):
        development.interaction_values("ore", "pickup", depleted_asset_id="rubble")


def test_matching_uses_described_style_usage_and_budget():
    rows = [
        dict(path="Assets/A", name="a", triangles=200),
        dict(path="Assets/B", name="b", triangles=5000),
    ]
    annotations = {
        p: {"semantic": {"style": "cozy", "materials": ["wood"], "uses": ["storage"]}}
        for p in ("Assets/A", "Assets/B")
    }
    matches = project_library.rank(
        rows, "", annotations, requirements={"materials": ["wood"], "max_triangles": 1000}
    )
    assert len(matches) == 1 and matches[0]["match_reasons"] == ["materials: wood"]


def object_row(name, position, size, asset_id=""):
    return dict(
        id=name,
        name=name,
        asset_id=asset_id,
        position=position,
        scale=[1, 1, 1],
        rotation=[0, 0, 0],
        bounds_min=[p - s / 2 for p, s in zip(position, size)],
        bounds_max=[p + s / 2 for p, s in zip(position, size)],
    )


@pytest.mark.parametrize("engine", ["unity", "unreal"])
def test_furnishing_preserves_walk_route_and_source_instances(engine):
    up = 1 if engine == "unity" else 2
    level = levels.plan(engine, modules=[{"cell": [0, 0, 0], "kind": "room"}], cell_size=6)
    floor = next(b for b in level["boxes"] if b["name"] == "floor_0")
    anchor = object_row("floor_0", floor["position"], floor["size"])
    position = [-20, 0, 0]
    position[up] = 0.5
    prop = object_row("chair_source", position, [1, 1, 1], "chair")
    scene = {"scene": "fixture", "engine": engine, "context": [anchor, prop], "assets": [prop]}
    old = copy.deepcopy(scene)
    result = scene_dressing.plan(scene, level, ["chair"])
    placed = result["placements"][0]
    assert placed["duplicate"] and placed["bounds_min"][up] == pytest.approx(0)
    assert scene == old
    assert abs(placed["position"][0]) > 1 or abs(placed["position"][3 - up]) > 1
    with pytest.raises(ValueError, match="No clear slot"):
        scene_dressing.plan(
            scene,
            level,
            ["chair"],
            protected_zones=[{"bounds_min": [-100, -100, -100], "bounds_max": [100, 100, 100]}],
        )


def test_feedback_rejects_stale_images_and_asset_revision(project, monkeypatch):
    root = core.state_root(project)
    state = dict(
        kind="quality",
        status="completed",
        asset_id="chair",
        asset_revision="a" * 32,
        review_id="b" * 32,
        brief={},
    )
    images = {}
    for stage, revision in (("before", "c" * 32), ("after", "d" * 32)):
        path = root / "previews" / (revision + ".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image fixture " + stage.encode())
        images[stage] = dict(request_id=revision, status="completed")
    monkeypatch.setattr(workflow, "job_status", lambda *args: state)
    monkeypatch.setattr(
        workflow, "inspect_asset", lambda *args: {"current": {"request_id": "a" * 32}}
    )
    monkeypatch.setattr(
        visual_feedback.reviews, "read", lambda *args: {"captures": images, "view": "game"}
    )
    evidence = visual_feedback.evidence(project, "e" * 32)
    saved = visual_feedback.save(
        project, "e" * 32, evidence["token"], "Handles read clearly", True, "Quiet wood grain"
    )
    assert saved["accepted"]
    brief = game_art.plan(project, "new_chair", "new chair", recipe_kind="chair")
    assert brief["visual_preferences"][0]["preference"] == "Quiet wood grain"
    assert authoring.catalog(project)["visual_preferences"][0]["preference"] == "Quiet wood grain"
    (root / "previews" / ("d" * 32 + ".png")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Images changed"):
        visual_feedback.save(project, "e" * 32, evidence["token"], "old observation")


def test_compact_gateway_discovers_contract_and_forwards_existing_tools(project):
    async def exercise():
        config = StdioServerParameters(
            command=sys.executable,
            args=["-m", "prompt_to_scene.app", "--mcp"],
            env={**os.environ, "PTS_PROJECT": str(project), "PTS_COMPACT_TOOLS": "1"},
        )
        async with stdio_client(config) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert {t.name for t in tools.tools} == {
                    "game_workflow",
                    "open_workbench",
                    "workbench_action",
                }
                for args in (
                    {"operation": "describe", "action": "produce"},
                    {"operation": "describe", "action": "set_project_style"},
                    {
                        "operation": "execute",
                        "action": "game_art_direction",
                        "values": {"settings": {"world": "cozy shop"}},
                    },
                ):
                    result = await client.call_tool("game_workflow", args)
                    assert not result.isError, result
                value = await client.call_tool(
                    "game_workflow", {"operation": "execute", "action": "game_art_direction"}
                )
                content = value.structuredContent or json.loads(value.content[0].text)
                assert content["world"] == "cozy shop"

    anyio.run(exercise)
