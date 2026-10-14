import json
from copy import deepcopy

import pytest
from PIL import Image

from prompt_to_scene import (
    art_kits,
    asset_recommendations,
    background,
    core,
    creations,
    game_art,
    gameplay,
    production,
    registry,
    semantics,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PTS_PROJECT", raising=False)
    monkeypatch.delenv("PTS_UNITY_PROJECT", raising=False)
    path = tmp_path / "Game"
    (path / "Assets").mkdir(parents=True)
    (path / "ProjectSettings").mkdir()
    registry.connect(str(path), install_bridge=False)
    settings = art_kits.rule_settings("apothecary")
    for name in settings["item_ids"]:
        core.atomic_json(game_art.root(path) / "game-items" / (name + ".json"), {"item_id": name})
    for name in settings["screen_ids"]:
        core.atomic_json(
            game_art.root(path) / "game-screens" / (name + ".json"), {"screen_id": name}
        )
    return path


def payload(project, task):
    request = core.read_optional_json(
        game_art.root(project) / "actions" / (task["request_id"] + ".json")
    )
    return json.loads(json.loads(request["development_json"])["content_json"])


def test_native_flow_revisions_and_project_save_namespace(project):
    settings = art_kits.rule_settings("apothecary")
    first = payload(project, gameplay.configure(project, "main", settings))
    core.atomic_json(game_art.root(project) / "gameplay/main.json", first)
    second = payload(project, gameplay.configure(project, "main", settings, first["revision"]))
    assert second["save_key"] == first["save_key"]
    assert second["expected_revision"] == first["revision"] != second["revision"]
    settings["slot"] = "new_game"
    assert (
        payload(project, gameplay.configure(project, "main", settings))["save_key"]
        != first["save_key"]
    )
    with pytest.raises(ValueError, match="changed"):
        gameplay.configure(project, "main", settings, "stale")
    settings["item_ids"].append("missing")
    with pytest.raises(ValueError, match="linked"):
        gameplay.configure(project, "main", settings)


def test_collect_craft_heal_and_failures_are_atomic():
    config = art_kits.rule_settings("apothecary")
    state = {"inventory": {}, "health": 40, "completed": []}
    rejected = gameplay.evaluate(config, state, "craft_potion")
    assert not rejected["success"] and rejected["state"] == state
    for key in ("collect_herb", "collect_bottle", "craft_potion", "use_potion"):
        result = gameplay.evaluate(config, state, key)
        assert result["success"]
        state = result["state"]
    assert state["inventory"] == {
        "apothecary_herb": 4,
        "apothecary_bottle": 2,
        "apothecary_potion": 0,
    }
    assert state["health"] == 70
    assert not gameplay.evaluate(config, state, "collect_herb")["success"]
    state["inventory"]["apothecary_potion"] = 1
    full = deepcopy(state)
    full["health"] = 100
    assert gameplay.evaluate(config, full, "use_potion")["state"] == full
    capped = gameplay.evaluate(config, state, "craft_potion", {"apothecary_potion": 1})
    assert not capped["success"] and capped["state"] == state


def test_prerequisites_and_key_consumption():
    config = {
        "item_ids": ["key"],
        "rules": [
            {"rule_id": "find_key", "once": True, "rewards": [{"item_id": "key", "quantity": 1}]},
            {
                "rule_id": "unlock",
                "once": True,
                "requires": ["find_key"],
                "costs": [{"item_id": "key", "quantity": 1}],
            },
        ],
    }
    assert gameplay.evaluate(config, {}, "unlock")["reason"] == "prerequisite"
    state = gameplay.evaluate(config, {}, "find_key")["state"]
    state = gameplay.evaluate(config, state, "unlock")["state"]
    assert state["inventory"]["key"] == 0 and "unlock" in state["completed"]
    config["rules"][0]["requires"] = ["unlock"]
    with pytest.raises(ValueError, match="cycle"):
        gameplay.validate(config)


@pytest.mark.parametrize(
    "change",
    [
        {"heal": float("nan")},
        {"heal": -1},
        {"once": "yes"},
        {"costs": [{"item_id": "apothecary_herb", "quantity": True}]},
        {"costs": [{"item_id": "unknown", "quantity": 1}]},
        {"trigger": "execute_code"},
        {"requires": ["unknown"]},
        {"asset_id": "../unsafe"},
        {"pickup_id": "apothecary_herb"},
    ],
)
def test_rules_reject_ambiguous_or_unsafe_inputs(change):
    config = art_kits.rule_settings("apothecary")
    config["rules"][0].update(change)
    with pytest.raises(ValueError):
        gameplay.validate(config)


def test_adapters_require_explicit_native_target(project):
    inspected = payload(project, gameplay.adapters(project, "main"))
    assert inspected == {"flow_id": "main", "target": ""}
    with pytest.raises(ValueError):
        gameplay.adapters(project, "main", "bind")
    bound = payload(project, gameplay.adapters(project, "main", "bind", "native-target"))
    assert bound["target"] == "native-target"


def test_dynamic_inventory_contract_and_art_kit_resources(project):
    ids = []
    for i in range(20):
        name = "item_" + str(i)
        core.atomic_json(game_art.root(project) / "game-items" / (name + ".json"), {})
        # A real item record must be nonempty.
        core.atomic_json(
            game_art.root(project) / "game-items" / (name + ".json"), {"item_id": name}
        )
        ids.append(name)
    spec = payload(project, creations.create_ui(project, "large_bag", item_ids=ids))
    assert spec["item_ids"] == ids
    for action in ("create_art_kit", "configure_gameplay", "project_adapters", "recommend_assets"):
        assert production.dispatch(project, "describe", action)["parameters"]
    source = registry.resources() / "examples/forest_apothecary.py"
    compile(source.read_text(), str(source), "exec")
    assert len(art_kits.PARTS) == 7


def test_recommendation_decisions_bind_real_images_and_detect_changed_source(project, monkeypatch):
    native = project / "Assets/Existing.prefab"
    native.write_text("original reference")
    image = project / "native-preview.png"
    Image.new("RGB", (8, 8), "green").save(image)
    request_id, evidence_id = "a" * 32, "b" * 32
    monkeypatch.setattr(
        semantics, "evidence", lambda *args: ({"image_sha256": "real-image-hash"}, image)
    )
    row = {
        "request_id": request_id,
        "query": "cozy cabinet",
        "requirements": {},
        "candidates": [
            {
                "path": "Assets/Existing.prefab",
                "evidence_id": evidence_id,
                "source_stamp": asset_recommendations.stamp(project, "Assets/Existing.prefab"),
            }
        ],
        "assessments": [],
    }
    core.atomic_json(game_art.root(project) / "asset-recommendations" / (request_id + ".json"), row)
    proof = asset_recommendations.evidence(project, request_id)
    with pytest.raises(ValueError, match="inspected"):
        asset_recommendations.reuse(project, request_id, proof["token"], "Assets/Existing.prefab")
    result = asset_recommendations.assess(
        project,
        request_id,
        proof["token"],
        [
            {
                "path": "Assets/Existing.prefab",
                "decision": "reuse",
                "reason": "Broad rounded silhouette and muted wood match the room",
            },
        ],
    )
    assert result["assessments"][0]["decision"] == "reuse"
    with pytest.raises(ValueError, match="changed"):
        asset_recommendations.assess(project, request_id, "stale", [])
    native.write_text("geometry and materials changed")
    with pytest.raises(ValueError, match="changed"):
        asset_recommendations.reuse(project, request_id, proof["token"], "Assets/Existing.prefab")


def test_invalid_reuse_requirements_never_launch_work(project, monkeypatch):
    monkeypatch.setattr(
        background, "submit", lambda *args: pytest.fail("Invalid input launched a task")
    )
    for requirements in ({"style": [False]}, {"max_triangles": -1}, {"hidden": True}):
        with pytest.raises(ValueError):
            asset_recommendations.start(project, "chair", requirements)


def test_candidates_do_not_repeat_exports_of_the_same_model():
    entries = [
        {"path": "chair.prefab", "asset_id": "chair"},
        {"path": "chair.fbx", "asset_id": "chair"},
        {"path": "other.fbx"},
    ]
    assert [r["path"] for r in asset_recommendations.distinct(entries, 2)] == [
        "chair.prefab",
        "other.fbx",
    ]


def test_workbench_has_unique_ids_and_loads_gameplay_script():
    from collections import Counter
    from html.parser import HTMLParser

    from prompt_to_scene import workbench

    ids = []

    class Parser(HTMLParser):
        def handle_starttag(self, tag, attributes):
            ids.extend(v for k, v in attributes if k == "id")

    source = workbench.page()
    Parser().feed(source)
    assert not [key for key, count in Counter(ids).items() if count > 1]
    assert 'id="tab-flows"' in source and "configure_gameplay" in source
