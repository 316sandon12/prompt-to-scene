import copy
import socket

import pytest

from prompt_to_scene import design, layout, recipes, registry, setup, styles


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PTS_PROJECT", raising=False)
    monkeypatch.delenv("PTS_UNITY_PROJECT", raising=False)
    p = tmp_path / "Project"
    (p / "Assets").mkdir(parents=True)
    (p / "ProjectSettings").mkdir()
    registry.connect(str(p), install_bridge=False)
    return p


def test_style_is_concrete_and_project_scoped(project, tmp_path):
    art = styles.save(
        str(project), "heritage", "mobile", {"palette": {"wood": [0.1, 0.2, 0.3]}, "wear": 0.8}
    )
    assert styles.read(str(project)) == art
    other = tmp_path / "Other"
    (other / "Assets").mkdir(parents=True)
    (other / "ProjectSettings").mkdir()
    assert styles.read(str(other))["preset"] == "cozy"
    _, recipe = recipes.prepare("chair", style=styles.read(str(project)))
    assert recipe["style"]["palette"]["wood"] == [0.1, 0.2, 0.3]
    assert recipe["style"]["quality"] == "mobile"
    with pytest.raises(ValueError):
        styles.save(
            str(project), overrides={"material_bindings": {"wood": "Assets/../private.mat"}}
        )


@pytest.mark.parametrize("kind", design.DEFAULTS)
def test_every_recipe_has_distinct_variants_and_semantic_parts(kind):
    hashes = []
    for variant in range(3):
        script, recipe = recipes.prepare(kind, {"variant": variant})
        compile(script, "recipe", "exec")
        items = design.plan(recipe)
        assert {v["part"] for v in items} == set(design.PARTS[kind])
        assert len({v["name"] for v in items}) == len(items)
        hashes.append(recipe["part_hashes"])
    assert len({str(h) for h in hashes}) == 3, kind


def test_local_edit_and_independent_geometry_material_locks():
    _, original = recipes.prepare("chair")
    _, edited = recipes.edit_part(original, "backrest", {"scale": [1, 1, 1.3]})
    for part in original["available_parts"]:
        assert (original["part_hashes"][part] == edited["part_hashes"][part]) == (
            part != "backrest"
        )
    _, locked = recipes.edit_part(edited, "backrest", lock_geometry=True)
    _, changed = recipes.revise(locked, {"height": 1.3})
    assert changed["part_hashes"]["backrest"] == edited["part_hashes"]["backrest"]
    _, both = recipes.edit_part(
        changed, "backrest", {"material": "paint", "color": [0.3, 0.1, 0.05]}, lock_material=True
    )
    _, restyled = recipes.revise(
        both, {"height": 1.5, "roughness": 0.1}, style=styles.preset("workshop")
    )
    assert restyled["part_hashes"]["backrest"] == edited["part_hashes"]["backrest"]
    surfaces = [i["surface"] for i in design.plan(restyled) if i["part"] == "backrest"]
    assert all(m["color"] == [0.3, 0.1, 0.05] and m["roughness"] != 0.1 for m in surfaces)
    with pytest.raises(ValueError, match="Unlock"):
        recipes.edit_part(restyled, "backrest", {"scale": [1, 1, 2]})
    _, unlocked = recipes.edit_part(restyled, "backrest", {"scale": [1, 1, 2]}, lock_geometry=False)
    assert unlocked["part_hashes"]["backrest"] != edited["part_hashes"]["backrest"]
    assert unlocked["locks"]["backrest"]["material"]


def test_material_edit_preserves_every_geometry_hash():
    _, recipe = recipes.prepare("cabinet")
    _, recolored = recipes.edit_part(recipe, "doors", {"color": [0, 0.2, 0.5], "wear": 0.8})
    assert recolored["part_hashes"] == recipe["part_hashes"]
    for bad in (
        {"scale": [1, 0, 1]},
        {"color": [0, 1, float("nan")]},
        {"material": "glass"},
        {"arbitrary": 1},
    ):
        with pytest.raises(ValueError):
            recipes.edit_part(recipe, "doors", bad)


@pytest.fixture(params=["unity", "unreal"])
def scene(request):
    engine = request.param
    up = 1 if engine == "unity" else 2

    def obj(name, center, size, asset=""):
        axes = [0, 2, 1] if up == 1 else [0, 1, 2]
        center = [center[i] for i in axes]
        size = [size[i] for i in axes]
        return {
            "id": name,
            "asset_id": asset,
            "name": name,
            "position": [center[i] - size[i] / 2 if i == up else center[i] for i in range(3)],
            "rotation": [0, 0, 0],
            "scale": [1, 1, 1],
            "bounds_min": [c - s / 2 for c, s in zip(center, size)],
            "bounds_max": [c + s / 2 for c, s in zip(center, size)],
        }

    anchor = obj("table", [0, 0, 0.5], [2, 1, 1], "table")
    source = obj("chair", [5, 0, 0.5], [0.4, 0.4, 1], "chair")
    return {
        "engine": engine,
        "scene": "test",
        "assets": [anchor, source],
        "selected_context": [anchor],
        "context": [anchor, source],
    }


def test_arrange_copies_are_collision_free_and_do_not_modify_snapshot(scene):
    saved = copy.deepcopy(scene)
    p = layout.plan(scene, [{"asset_id": "chair", "count": 4}])
    assert scene == saved
    assert sum(r["duplicate"] for r in p["placements"]) == 3
    assert len(p["placements"]) == 4
    assert not any(
        layout.overlaps(a, b)
        for i, a in enumerate(p["placements"])
        for b in p["placements"][i + 1 :]
    )
    blocker = {**p["placements"][0], "id": "obstacle", "name": "Other prop"}
    scene["context"].append(blocker)
    with pytest.raises(ValueError, match="overlap"):
        layout.plan(scene, [{"asset_id": "chair", "count": 4}])


def test_under_fit_respects_available_height_and_floor(scene):
    with pytest.raises(ValueError, match="fit"):
        layout.plan(scene, [{"asset_id": "chair"}], "under", clearance=0.6)
    p = layout.plan(scene, [{"asset_id": "chair"}], "under", fit=True, clearance=0.6)
    row = p["placements"][0]
    up = 1 if scene["engine"] == "unity" else 2
    assert row["bounds_max"][up] <= 0.6001
    assert abs(row["bounds_min"][up]) < 0.0001
    assert all(abs(v - 0.6) < 0.0001 for v in row["scale"])


def test_setup_start_does_not_depend_on_dns(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Loopback setup must not perform reverse DNS")

    monkeypatch.setattr(socket, "getfqdn", forbidden)
    with setup.Server() as server:
        assert server.server_port > 0


def test_process_probe_does_not_terminate_live_workers():
    import subprocess
    import sys

    from prompt_to_scene.workflow import process_alive

    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"], stdin=subprocess.PIPE
    )
    try:
        assert process_alive(child.pid)
        assert child.poll() is None
        child.stdin.close()
        child.wait(timeout=10)
        assert not process_alive(child.pid)
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
