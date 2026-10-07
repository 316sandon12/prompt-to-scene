import copy
from types import SimpleNamespace

import pytest

from prompt_to_scene import (
    authoring,
    core,
    design,
    game_art,
    generation,
    recipes,
    registry,
    style_matching,
    styles,
    workbench,
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


def test_game_context_is_partial_project_scoped_and_validated(project, tmp_path):
    assert game_art.for_recipe(project, "cabinet", "cabinet") is None
    game_art.configure(project, {"world": "山间小镇", "gameplay": "经营、收集"})
    result = workbench.dispatch("game_art", {"settings": {"view": "first_person"}})
    assert result["world"] == "山间小镇" and result["gameplay"] == "经营、收集"
    other = tmp_path / "Other"
    (other / "Assets").mkdir(parents=True)
    (other / "ProjectSettings").mkdir()
    assert not game_art.configure(other)["world"]
    for settings in ({"view": "VR"}, {"unknown": "x"}, {"world": 1}, {"world": "x" * 2001}):
        with pytest.raises(ValueError):
            game_art.configure(project, settings)
    assert game_art.configure(project)["view"] == "first_person"


def test_context_brief_snapshot_and_custom_routing(project):
    game_art.configure(project, {"world": "荒废的火车站", "construction": "salvaged"})
    brief = game_art.plan(
        project,
        "console",
        "用旧收音机改造的车站终端",
        role="interactable",
        decisions={"structure": "倾斜控制台与可维修的独立侧板"},
    )
    game_art.configure(project, {"world": "未来空间站", "construction": "machined"})
    assert game_art.plan(project, "console")["context"]["world"] == "荒废的火车站"
    assert brief["treatment"]["emphasize_hardware"]
    with pytest.raises(ValueError, match="custom modeling"):
        game_art.for_recipe(project, "console", "cabinet")
    brief["context"]["world"] = "mutated"
    assert game_art.saved_plan(project, "console")["context"]["world"] == "荒废的火车站"


@pytest.mark.parametrize("kind", design.DEFAULTS)
def test_all_contextual_recipes_remain_editable_at_every_detail_level(project, kind):
    for craft in game_art.CONSTRUCTION:
        for view in ("top_down", "first_person"):
            game_art.configure(project, {"construction": craft, "view": view})
            brief = game_art.plan(project, kind, kind, recipe_kind=kind)
            for variant in range(3):
                _, recipe = recipes.prepare(kind, {"variant": variant}, art_design=brief)
                items = design.plan(recipe)
                assert set(i["part"] for i in items) == set(design.PARTS[kind])
                assert all(all(s > 0 for s in i["size"]) for i in items)
                assert all(i["surface"]["grain"] for i in items)
            # A locked structural part must retain the detailed shape after global size changes.
            part = "doors" if kind == "cabinet" else design.PARTS[kind][0]
            _, locked = recipes.edit_part(recipe, part, lock_geometry=True, lock_material=True)
            _, revised = recipes.revise(locked, {"width": 1.9}, style=styles.preset("workshop"))
            assert revised["part_hashes"][part] == recipe["part_hashes"][part]
            old_surfaces = [i["surface"] for i in design.plan(recipe) if i["part"] == part]
            new_surfaces = [i["surface"] for i in design.plan(revised) if i["part"] == part]
            assert old_surfaces == new_surfaces


def test_construction_and_view_change_actual_geometry_not_only_labels(project):
    hashes, counts = [], []
    for craft in game_art.CONSTRUCTION:
        game_art.configure(project, {"construction": craft, "view": "first_person"})
        brief = game_art.plan(project, "storage", "storage", recipe_kind="cabinet")
        _, recipe = recipes.prepare("cabinet", art_design=brief)
        hashes.append(recipe["part_hashes"])
    assert len({str(h) for h in hashes}) == 3
    for view in ("top_down", "first_person"):
        game_art.configure(project, {"view": view})
        brief = game_art.plan(project, "storage", "storage", recipe_kind="cabinet")
        _, recipe = recipes.prepare("cabinet", art_design=brief)
        counts.append(len(design.plan(recipe)))
    assert counts[0] < counts[1]


def test_custom_build_has_preparation_and_retains_design_at_submission(project, monkeypatch):
    game_art.configure(project, {"world": "moon workshop"})
    brief = game_art.plan(project, "device", "wooden telescope", role="hero")
    monkeypatch.setattr(core, "blender_path", lambda: "/fixture/blender")
    monkeypatch.setattr(workflow, "launch_worker", lambda *_: SimpleNamespace(pid=123))
    task = authoring.build_custom(project, "device", "# bpy fixture", collider=False)
    path = core.state_root(project) / "jobs" / task["request_id"] / "spec.json"
    game_art.configure(project, {"world": "new setting"})
    game_art.plan(project, "device", "a different brief")
    spec = core.read_optional_json(path)
    assert spec["provenance"]["art_design"] == brief
    assert spec["preparation"]["collision"] == "none"
    assert (
        spec["preparation"]["texture_size"]
        == styles.QUALITY[brief["style"]["quality"]]["texture_size"]
    )


def test_recipe_create_inherits_plan_without_reinterpreting_history(project, monkeypatch):
    game_art.configure(project, {"world": "cozy village", "view": "first_person"})
    brief = game_art.plan(project, "cabinet", "herbalist cabinet", recipe_kind="cabinet")
    styles.save(project, "workshop")
    monkeypatch.setattr(authoring, "submit_recipe", lambda p, name, script, recipe, *a: recipe)
    recipe = authoring.create(project, "cabinet", "cabinet")
    assert recipe["style"] == brief["style"]
    assert recipe["art_design"]["context"]["world"] == "cozy village"
    original = copy.deepcopy(recipe)
    _, recolored = recipes.edit_part(recipe, "doors", {"color": [0.1, 0.2, 0.3]})
    assert recipe == original
    assert recolored["part_hashes"] == original["part_hashes"]


def test_provider_budget_preserves_full_request_and_exposes_omitted_context(project):
    game_art.configure(project, {"world": "small village", "gameplay": "collect herbs"})
    brief = game_art.plan(project, "cabinet", "herbalist cabinet")
    prompt, _ = game_art.provider_prompt("a green cabinet", brief)
    assert "small village" in prompt and "collect herbs" in prompt and len(prompt) <= 800
    full = "x" * 800
    prompt, shortened = game_art.provider_prompt(full, brief)
    assert prompt == full and "World" in shortened


def test_explicit_redesign_preserves_locks_and_does_not_rewrite_old_recipe(project, monkeypatch):
    game_art.configure(project, {"construction": "handcrafted"})
    old = game_art.plan(project, "cabinet", "carpenter cabinet", recipe_kind="cabinet")
    _, recipe = recipes.prepare("cabinet", art_design=old)
    _, recipe = recipes.edit_part(recipe, "doors", lock_geometry=True, lock_material=True)
    game_art.configure(project, {"construction": "machined"})
    game_art.plan(project, "cabinet", "converted workshop cabinet", recipe_kind="cabinet")
    monkeypatch.setattr(authoring, "current_recipe", lambda *a: ({"metadata": {}}, recipe))
    monkeypatch.setattr(authoring, "submit_recipe", lambda p, name, script, updated, **k: updated)
    unchanged = authoring.revise(project, "cabinet")
    changed = authoring.revise(project, "cabinet", apply_design=True)
    assert unchanged["art_design"]["context"]["construction"] == "handcrafted"
    assert changed["art_design"]["context"]["construction"] == "machined"
    assert changed["part_hashes"]["doors"] == recipe["part_hashes"]["doors"]
    assert changed["part_hashes"]["legs"] != recipe["part_hashes"]["legs"]
    assert recipe["art_design"]["context"]["construction"] == "handcrafted"


def test_generation_snapshots_the_actual_enriched_prompt_before_launch(project, monkeypatch):
    game_art.configure(project, {"world": "woodland", "gameplay": "sell herbs"})
    monkeypatch.setattr(generation, "Adapter", lambda *a: None)
    monkeypatch.setattr(generation.background, "submit", lambda project, kind, args, name: args)
    spec = generation.submit(project, "herb_box", "A cabinet")
    game_art.configure(project, {"world": "spaceport"})
    assert "woodland" in spec["effective_prompt"]
    assert "spaceport" not in spec["effective_prompt"]
    assert spec["prompt"] == "A cabinet"
    assert spec["art_design"]["context"]["gameplay"] == "sell herbs"


def style_reference(project):
    from prompt_to_scene import quality

    image = project / "reference.png"
    image.write_bytes(b"reference image fixture")
    quality.set_brief(project, image_path=str(image))
    return style_matching.inspect(project, use_reference=True)


def style_analysis(**changes):
    return {
        "observations": "Rounded edges, muted green paint and matte timber",
        "shape_language": "Stocky forms with soft corners",
        "confidence": 0.85,
        "palette": {"paint": "#668877"},
        "roundness": 0.8,
        "roughness": {"paint": 0.78},
        "detail": "readable",
        **changes,
    }


def test_reference_matching_changes_real_material_and_design_defaults(project):
    source = style_reference(project)
    before = styles.read(project)
    result = style_matching.apply(project, source["source_token"], style_analysis())
    assert result["status"] == "applied"
    assert styles.read(project)["palette"]["wood"] == before["palette"]["wood"]
    # sRGB 0x66 converts to ~0.132868 linear, not 0.4.
    assert styles.read(project)["palette"]["paint"][0] == pytest.approx(0.1328683, abs=0.00001)
    brief = game_art.for_recipe(project, "chair", "chair")
    _, recipe = recipes.prepare("chair", style=styles.read(project), art_design=brief)
    pieces = design.plan(recipe)
    assert all(i["surface"]["roughness"] == 0.78 for i in pieces if i["material"] == "paint")
    assert all(i["surface"]["quiet"] for i in pieces)
    assert brief["style_reference"]["source_token"] == source["source_token"]
    assert "Stocky" in brief["context"]["style_notes"]


def test_uncertain_or_changed_reference_cannot_overwrite_current_style(project):
    from pathlib import Path

    source = style_reference(project)
    before = styles.read(project)
    assert (
        style_matching.apply(project, source["source_token"], style_analysis(confidence=0.2))[
            "status"
        ]
        == "uncertain"
    )
    assert styles.read(project) == before
    Path(source["sources"][0]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="evidence changed"):
        style_matching.apply(project, source["source_token"], style_analysis())
    assert styles.read(project) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"palette": {"paint": "green"}},
        {"roughness": {"paint": 2}},
        {"taper": 0.1},
        {"detail": "infinite"},
    ],
)
def test_invalid_style_inference_does_not_partially_apply(project, changes):
    source = style_reference(project)
    before = styles.read(project)
    with pytest.raises(ValueError):
        style_matching.apply(project, source["source_token"], style_analysis(**changes))
    assert styles.read(project) == before
