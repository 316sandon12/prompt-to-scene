"""Scene grounding must survive generation, coordinates, edits and project switches."""

import copy
from pathlib import Path

import pytest
from PIL import Image

from prompt_to_scene import (
    core,
    creative_tasks,
    game_art,
    image_assets,
    image_edits,
    production,
    registry,
    scene_context,
    style_matching,
    workflow,
)


@pytest.fixture(params=["unity", "unreal"])
def project(tmp_path, monkeypatch, request):
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PTS_PROJECT", raising=False)
    monkeypatch.delenv("PTS_UNITY_PROJECT", raising=False)
    root = tmp_path / "Game"
    root.mkdir()
    if request.param == "unity":
        (root / "Assets").mkdir()
        (root / "ProjectSettings").mkdir()
    else:
        core.atomic_json(root / "Game.uproject", {"FileVersion": 3})
    registry.connect(str(root), install_bridge=False)
    return root


def native(project, key="a", changed=None):
    engine = registry.resolve(project).engine
    target = dict(
        id="placeholder",
        name="Chest blockout",
        asset_id="placeholder",
        position=[0, 0, 0],
        rotation=[0, 0, 0],
        scale=[1, 1, 1],
        bounds_min=[-1, 0, -0.5],
        bounds_max=[1, 1, 0.5],
    )
    # Both adapters report metres, even UE's native source uses centimetres.
    if engine == "unreal":
        target["bounds_min"], target["bounds_max"] = [-1, -0.5, 0], [1, 0.5, 1]
    camera = dict(
        id="camera",
        name="Game camera",
        primary=True,
        aspect=1,
        position=[0, 0, -10] if engine == "unity" else [-10, 0, 0],
        forward=[0, 0, 1] if engine == "unity" else [1, 0, 0],
        right=[1, 0, 0] if engine == "unity" else [0, 1, 0],
        up=[0, 1, 0] if engine == "unity" else [0, 0, 1],
        vertical_fov=90,
        orthographic=False,
        ortho_height_m=10,
        projection_supported=True,
        near_m=0.1,
    )
    row = dict(
        request_id=key * 32,
        status="completed",
        engine=engine,
        scene="Main",
        context=[target],
        assets=[target],
        selected_context=[target],
        cameras=[camera],
    )
    if changed:
        changed(row)
    core.atomic_json(core.state_root(project) / "action-receipts" / (key * 32 + ".json"), row)
    return row


def retain_model(project, design):
    root = core.state_root(project)
    core.atomic_json(root / "receipts/chest.json", dict(status="imported", request_id="f" * 32))
    core.atomic_json(
        root / "work/chest" / ("f" * 32) / "asset.json", {"provenance": {"art_design": design}}
    )


def test_scene_shared_between_models_images_and_tasks_without_engine_calls(project, monkeypatch):
    row = native(project)
    scene_context.save(project, row["request_id"], {"fit": "fit", "usage": "store herbs"})
    monkeypatch.setattr(workflow, "action", lambda *a, **k: pytest.fail("must reuse capture"))
    model = game_art.plan(project, "chest", "Medicine chest")
    image = image_assets.plan(project, "chest_icon", "The same medicine chest")
    assert image["scene_context"] == model["scene_context"]
    assert model["scene_context"]["max_size_m"] == [2, 1, 1]
    assert "store herbs" in image["effective_prompt"]
    assert "WORLD XYZ" in model["modeling_guidance"][-1]
    assert (
        creative_tasks.context(project)["scene_context"]["revision"]
        == (model["scene_context"]["revision"])
    )
    scene_context.save(project, settings={"size_m": [0.3, 0.4, 0.5]})
    assert game_art.saved_plan(project, "chest")["scene_context"]["max_size_m"] == [2, 1, 1]
    scene_context.save(project, settings={"enabled": False})
    assert game_art.plan(project, "new", "New object")["scene_context"] is None


def test_reference_copy_and_region_base_order_are_preserved(project):
    source = project / "scene.png"
    Image.new("RGB", (80, 40), "green").save(source)
    scene_context.save(project, reference_path=str(source))
    source.unlink()
    observation = style_matching.inspect(project, use_scene=True)
    assert observation["sources"][0]["kind"] == "scene_reference"
    assert observation["status"] == "ready_for_vision"
    applied = style_matching.apply(
        project,
        observation["source_token"],
        {
            "observations": "Green material in the saved scene reference",
            "shape_language": "Broad, simple forms",
            "confidence": 0.8,
            "palette": {"paint": "#008000"},
        },
    )
    assert applied["status"] == "applied"
    plan = image_assets.plan(project, "icon", "An herb")
    assert len(plan["references"]) == 1 and "Reference 1 is the scene" in plan["effective_prompt"]
    source = project / "icon.png"
    pixels = Image.new("RGBA", (256, 256))
    pixels.paste((80, 130, 50, 255), (60, 60, 190, 190))
    pixels.save(source)
    imported = image_assets.import_image(
        project, "icon", str(source), plan["plan_id"], preview_only=True
    )
    edit = image_edits.plan(
        project, "icon", imported["revision"], [0.2, 0.2, 0.5, 0.5], "gold leaf"
    )
    assert edit["references"][0]["source"].endswith("/image.png")
    assert "scene-references" in edit["references"][1]["source"]
    assert "Reference 2 is the scene" in edit["effective_prompt"]
    Path(scene_context.read(project)["reference"]["path"]).write_bytes(b"changed")
    # An already retained generation stays reproducible even after source evidence changes.
    assert Path(image_assets.read_plan(project, plan["plan_id"])["references"][0]["path"]).is_file()
    with pytest.raises(ValueError, match="reference changed"):
        image_assets.plan(project, "next", "Next image")


@pytest.mark.parametrize(
    "settings",
    [
        {"size_m": [1, True, 1]},
        {"size_m": [1, float("nan"), 1]},
        {"display_size_px": [0, 64]},
        {"display_size_px": [64.5, 64]},
        {"fit": []},
        {"image_margin": 0.5},
        {"enabled": "yes"},
        {"fit": "fit"},
        {"target_id": "not-in-scene"},
        {"unknown": 1},
    ],
)
def test_bad_constraints_never_partially_replace_saved_settings(project, settings):
    scene_context.save(project, settings={"usage": "keep this"})
    before = scene_context.read(project)
    with pytest.raises(ValueError):
        scene_context.save(project, settings=settings)
    assert scene_context.read(project) == before


def test_no_guesses_with_multiple_selections_or_cameras_and_no_cross_project_read(
    project, tmp_path
):
    def many(row):
        row["selected_context"].append({**row["context"][0], "id": "second"})
        row["cameras"][0]["primary"] = False
        row["cameras"].append({**row["cameras"][0], "id": "second-camera"})

    row = native(project, changed=many)
    result = scene_context.save(project, row["request_id"])
    assert not result["settings"]["target_id"] and not result["settings"]["camera_id"]
    assert scene_context.brief(project)["max_size_m"] is None
    other = tmp_path / "Other"
    (other / "Assets").mkdir(parents=True)
    (other / "ProjectSettings").mkdir()
    assert scene_context.brief(other) is None
    with pytest.raises(ValueError, match="completed inspect_scene"):
        scene_context.save(other, row["request_id"])


def test_flat_target_needs_explicit_height_before_any_settings_are_saved(project):
    def flat(row):
        up = 1 if row["engine"] == "unity" else 2
        row["context"][0]["bounds_max"][up] = row["context"][0]["bounds_min"][up]

    row = native(project, changed=flat)
    with pytest.raises(ValueError, match="Target volume"):
        scene_context.save(project, row["request_id"], {"fit": "fit"})
    assert scene_context.read(project) == {}
    scene_context.save(project, row["request_id"], {"fit": "fit", "size_m": [1, 1, 1]})
    assert scene_context.brief(project)["max_size_m"] == [1, 1, 1]


def test_dimensions_framing_and_staleness_use_imported_brief_not_latest_plan(project):
    row = native(project)
    scene_context.save(project, row["request_id"], {"fit": "fit"})
    design = game_art.plan(project, "chest", "Chest")
    retain_model(project, design)
    scene_context.save(project, settings={"size_m": [20, 20, 20]})
    game_art.plan(project, "chest", "Different future design")

    def generated(row):
        prop = copy.deepcopy(row["context"][0])
        prop.update(id="instance", asset_id="chest")
        prop["bounds_max"][0] += 2
        row["assets"].append(prop)

    latest = native(project, "b", generated)
    report = production.dispatch(
        project,
        "execute",
        "check_scene_fit",
        {"asset_id": "chest", "inspection_id": latest["request_id"]},
    )
    assert report["max_size_m"] == [2, 1, 1] and not report["stale"]
    assert report["instances"][0]["oversized_axes"] == ["X"]
    assert report["instances"][0]["uniform_scale_to_fit"] == 0.5
    assert report["instances"][0]["outside_target_axes"] == ["X"]
    assert report["instances"][0]["framing"]["status"] == "estimated"
    latest["cameras"][0]["aspect"] = 2
    latest["context"][0]["position"] = [10, 0, 0]
    core.atomic_json(core.state_root(project) / "action-receipts" / ("b" * 32 + ".json"), latest)
    report = scene_context.check_model(project, "chest", "b" * 32)
    assert len(report["stale"]) == 2 and report["instances"][0]["framing"] is None
    with pytest.raises(ValueError, match="again after importing"):
        scene_context.check_model(project, "chest", "a" * 32)


def test_image_report_measures_alpha_margin_but_never_claims_beauty(project):
    scene_context.save(project, settings={"display_size_px": [64, 32], "image_margin": 0.1})
    design = image_assets.plan(project, "icon", "Icon")
    pixels = Image.new("RGBA", (256, 256))
    pixels.paste((255, 0, 0, 255), (0, 0, 100, 100))
    source = project / "icon.png"
    pixels.save(source)
    result = image_assets.import_image(
        project, "icon", str(source), design["plan_id"], preview_only=True
    )
    report = result["report"]["scene_fit"]
    assert len(report["warnings"]) == 2
    assert report["alpha_bounds_px"] == (0, 0, 100, 100)
    assert not report["appearance_accepted"]
    assert result["report"]["warnings"] == report["warnings"]


def test_numeric_provider_limits_are_kept_whole_or_reported_omitted(project):
    scene_context.save(project, settings={"size_m": [0.123, 0.456, 0.789]})
    design = game_art.plan(project, "chest", "Chest")
    prompt, shortened = game_art.provider_prompt("a chest", design)
    assert "[0.123, 0.456, 0.789]" in prompt and len(prompt) <= 800
    prompt, shortened = game_art.provider_prompt("a" * 790, design)
    assert prompt == "a" * 790 and "Max world XYZ metres" in shortened


def test_projection_math_for_orthographic_perspective_and_behind_camera():
    camera = dict(
        projection_supported=True,
        position=[0, 0, 0],
        right=[1, 0, 0],
        up=[0, 1, 0],
        forward=[0, 0, 1],
        aspect=2,
        vertical_fov=90,
        orthographic=False,
        ortho_height_m=4,
        near_m=0.1,
    )
    box = {"bounds_min": [-2, -1, 2], "bounds_max": [2, 1, 4]}
    projection = scene_context.projected_bounds(box, camera)
    assert projection["rectangle"] == pytest.approx([0.25, 0.25, 0.5, 0.5])
    camera["orthographic"] = True
    assert scene_context.projected_bounds(box, camera)["rectangle"] == pytest.approx(
        [0.25, 0.25, 0.5, 0.5]
    )
    box["bounds_max"][0] = 10
    assert scene_context.projected_bounds(box, camera)["outside_frame"]
    box["bounds_min"][2] = -1
    assert scene_context.projected_bounds(box, camera)["status"] == "near_plane"
    camera["projection_supported"] = False
    assert scene_context.projected_bounds(box, camera) is None
