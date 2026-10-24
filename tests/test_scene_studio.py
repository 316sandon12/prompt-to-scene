"""Scene previews must remain reversible and preserve gameplay, images and regional decisions."""

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from test_scene_context import native, retain_model

from prompt_to_scene import (
    art_samples,
    asset_requirements,
    background,
    core,
    game_art,
    image_assets,
    parts,
    production,
    registry,
    scene_context,
    scene_profiles,
    scene_studio,
    workflow,
)


@pytest.fixture(params=["unity", "unreal"])
def project(tmp_path, monkeypatch, request):
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "client"))
    monkeypatch.delenv("PTS_PROJECT", raising=False)
    monkeypatch.delenv("PTS_UNITY_PROJECT", raising=False)
    folder = tmp_path / "Game"
    folder.mkdir()
    if request.param == "unity":
        (folder / "Assets").mkdir()
        (folder / "ProjectSettings").mkdir()
    else:
        core.atomic_json(folder / "Game.uproject", {"FileVersion": 3})
    registry.connect(str(folder), install_bridge=False)
    return folder


def capture(project):
    row = native(project)
    path = core.state_root(project) / "previews" / ("a" * 32 + ".png")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), "#325044").save(path)
    row.update(
        preview="previews/" + path.name,
        reference_camera_id="camera",
        materials=[{"object_id": "placeholder", "path": "wood"}],
    )
    core.atomic_json(core.state_root(project) / "action-receipts" / ("a" * 32 + ".json"), row)
    scene_context.save(project, "a" * 32)
    return row


def model(project, monkeypatch):
    state = capture(project)
    source = deepcopy(state["context"][0])
    source.update(id="source", asset_id="chest", name="Medicine chest", position=[4, 0, 0])
    source["bounds_min"] = [v + (4 if i == 0 else 0) for i, v in enumerate(source["bounds_min"])]
    source["bounds_max"] = [v + (4 if i == 0 else 0) for i, v in enumerate(source["bounds_max"])]
    state["assets"] = [source]
    state["context"].append(source)
    state["request_id"] = "b" * 32
    core.atomic_json(core.state_root(project) / "action-receipts" / ("b" * 32 + ".json"), state)
    retain_model(project, game_art.plan(project, "chest", "Herb chest"))
    monkeypatch.setattr(
        background, "submit", lambda *a, **kw: {"status": "building", "request_id": "c" * 32}
    )
    return state


def completed_preview(project, row):
    for stage, key in (("before", "d"), ("trial", "e")):
        path = core.state_root(project) / "previews" / (key * 32 + ".png")
        Image.new("RGB", (64, 64), "green").save(path)
        core.atomic_json(
            core.state_root(project) / "action-receipts" / (key * 32 + ".json"),
            {"status": "completed", "preview": "previews/" + path.name},
        )
        row[stage] = key * 32
    return scene_studio.write(project, row)


def icon(project, opaque=False):
    capture(project)
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    image.paste((60, 130, 65, 255), (0, 0, 128, 128) if opaque else (0, 6, 120, 124))
    path = Path(project) / "herb.png"
    image.save(path)
    plan = image_assets.plan(
        project, "herb", "Herb icon", width=128, height=128, transparent=not opaque
    )
    return image_assets.import_image(project, "herb", str(path), plan["plan_id"], preview_only=True)


def test_reference_copies_native_pixels_camera_and_materials(project):
    capture(project)
    saved = scene_context.read(project)
    assert saved["reference"]["kind"] == "native_scene_reference"
    assert scene_context.brief(project)["materials"][0]["path"] == "wood"
    assert saved["reference"]["camera_id"] == "camera"
    Path(saved["reference"]["source"]).unlink()
    assert Path(saved["reference"]["path"]).is_file()


def test_model_preview_positions_from_bounds_and_does_not_move(project, monkeypatch):
    state = model(project, monkeypatch)
    before = deepcopy(state)
    result = scene_studio.preview_model(project, "chest", "b" * 32)
    row = scene_studio.read(project, result["plan_id"])
    up = 1 if state["engine"] == "unity" else 2
    assert row["placement"]["bounds_min"][up] == state["selected_context"][0]["bounds_max"][up]
    assert state == before
    assert not list((core.state_root(project) / "actions").glob("*.json"))
    with pytest.raises(ValueError, match="both game-camera"):
        scene_studio.act(project, row["plan_id"])
    completed_preview(project, row)
    adopted = scene_studio.act(project, row["plan_id"])
    assert scene_studio.act(project, row["plan_id"])["request_id"] == adopted["request_id"]
    payload = core.read_optional_json(
        core.state_root(project) / "actions" / (adopted["request_id"] + ".json")
    )
    assert payload["operation"] == "scene_stage"


@pytest.mark.parametrize("change", ["target", "camera", "ambiguous"])
def test_model_rejects_stale_and_ambiguous_scene(project, monkeypatch, change):
    state = model(project, monkeypatch)
    if change == "target":
        state["context"][0]["position"][0] = 1
    if change == "camera":
        state["cameras"][0]["position"][0] += 1
    if change == "ambiguous":
        state["assets"].append({**state["assets"][0], "id": "another"})
    core.atomic_json(core.state_root(project) / "action-receipts" / ("b" * 32 + ".json"), state)
    with pytest.raises(ValueError, match="changed|one model instance"):
        scene_studio.preview_model(project, "chest", "b" * 32)


def test_usage_minimum_scale_lock_and_clearance_block_bad_repairs(project, monkeypatch):
    state = model(project, monkeypatch)
    scene_context.save(project, settings={"size_m": [0.5, 0.5, 0.5]})
    asset_requirements.save(project, "chest", {"min_size_m": [1, 0, 0]})
    with pytest.raises(ValueError, match="minimum size"):
        scene_studio.preview_model(project, "chest", "b" * 32, resize=True)
    asset_requirements.save(project, "chest", {"min_size_m": [0, 0, 0], "lock_scale": True})
    with pytest.raises(ValueError, match="locked"):
        scene_studio.preview_model(project, "chest", "b" * 32, resize=True)
    asset_requirements.save(project, "chest", {"lock_scale": False, "clearance_m": [10, 10, 10]})
    obstacle = deepcopy(state["assets"][0])
    obstacle["id"] = "obstacle"
    state["context"].append(obstacle)
    core.atomic_json(core.state_root(project) / "action-receipts" / ("b" * 32 + ".json"), state)
    with pytest.raises(ValueError, match="Reserved interaction"):
        scene_studio.preview_model(project, "chest", "b" * 32, resize=True)


def test_adoption_refuses_new_requirements_and_discard(project, monkeypatch):
    model(project, monkeypatch)
    result = scene_studio.preview_model(project, "chest", "b" * 32)
    row = completed_preview(project, scene_studio.read(project, result["plan_id"]))
    asset_requirements.save(project, "chest", {"lock_scale": True})
    with pytest.raises(ValueError, match="requirements changed"):
        scene_studio.act(project, row["plan_id"])
    scene_studio.act(project, row["plan_id"], "discard")
    with pytest.raises(ValueError, match="discarded"):
        scene_studio.act(project, row["plan_id"])


def test_fast_preview_worker_keeps_completed_captures(project, monkeypatch):
    model(project, monkeypatch)

    def submit(project, kind, values, asset):
        completed_preview(project, scene_studio.read(project, values["plan_id"]))
        return {"status": "completed", "request_id": "c" * 32}

    monkeypatch.setattr(background, "submit", submit)
    result = scene_studio.preview_model(project, "chest", "b" * 32)
    assert len(scene_studio.evidence(project, result["plan_id"])["images"]) == 2


def test_discard_during_capture_does_not_restore_preview(project, monkeypatch):
    model(project, monkeypatch)
    result = scene_studio.preview_model(project, "chest", "b" * 32)
    plan_id = result["plan_id"]

    class Job:
        state = {}

        def check(self):
            pass

        def update(self, **values):
            self.state.update(values)

        def wait(self, task):
            scene_studio.act(project, plan_id, "discard")
            return {"request_id": "d" * 32}

    job = Job()
    job.project = project
    with pytest.raises(InterruptedError, match="discarded"):
        scene_studio.run(job, plan_id)
    saved = scene_studio.read(project, plan_id)
    assert saved["discarded"] and "trial" not in saved and "before" not in saved
    assert list(job.state) == ["before"]


def test_noncolliding_sky_does_not_hide_real_obstacles(project, monkeypatch):
    state = model(project, monkeypatch)
    sky = dict(
        id="sky",
        name="Sky",
        bounds_min=[-100, -100, -100],
        bounds_max=[100, 100, 100],
        has_collision=False,
    )
    state["context"].append(sky)
    receipt = core.state_root(project) / "action-receipts" / ("b" * 32 + ".json")
    core.atomic_json(receipt, state)
    scene_studio.preview_model(project, "chest", "b" * 32)
    sky["has_collision"] = True
    core.atomic_json(receipt, state)
    with pytest.raises(ValueError, match="overlap"):
        scene_studio.preview_model(project, "chest", "b" * 32)


def test_part_repair_is_scoped_and_restore_refuses_later_edits(project, monkeypatch):
    model(project, monkeypatch)
    result = scene_studio.preview_model(project, "chest", "b" * 32)
    row = completed_preview(project, scene_studio.read(project, result["plan_id"]))
    calls = []

    def edit(*args):
        calls.append(args)
        return {"request_id": "d" * 32, "status": "queued"}

    monkeypatch.setattr(parts, "edit", edit)
    with pytest.raises(ValueError, match="named part"):
        scene_studio.repair_part(project, row["plan_id"], "all", {"roughness": 0.6})
    scene_studio.repair_part(project, row["plan_id"], "lid", {"roughness": 0.6})
    assert calls == [(project, "chest", "lid", {"roughness": 0.6})]
    with pytest.raises(ValueError, match="outside this repair"):
        scene_studio.restore_part(project, row["plan_id"])
    core.atomic_json(
        core.state_root(project) / "receipts/chest.json",
        {"request_id": "d" * 32, "status": "imported"},
    )
    monkeypatch.setattr(workflow, "restore", lambda *args: args)
    assert scene_studio.restore_part(project, row["plan_id"])[2] == row["model_revision"]
    profile = scene_profiles.save(project, "Locked room", locks={"palette": "keep the green"})
    scene_profiles.activate(project, profile["profile_id"])
    with pytest.raises(ValueError, match="changed"):
        scene_studio.repair_part(project, row["plan_id"], "lid", {"color": [1, 0, 0]})
    assert len(calls) == 1


def test_image_adoption_and_undo_preserve_previous_revision(project, monkeypatch):
    first = icon(project)
    second = scene_studio.pad_image(project, "herb", first["revision"], 0.1)
    receipt = core.state_root(project) / "image-receipts/herb.json"
    core.atomic_json(receipt, {"revision": first["revision"]})

    def publish(project, asset, revision):
        task = {"request_id": uuid4().hex, "status": "completed"}
        core.atomic_json(receipt, {"revision": revision})
        core.atomic_json(
            core.state_root(project) / "action-receipts" / (task["request_id"] + ".json"), task
        )
        return task

    monkeypatch.setattr(image_assets, "publish", publish)
    row = scene_studio.preview_image(project, "herb", second["revision"])
    scene_studio.act(project, row["plan_id"])
    assert core.read_optional_json(receipt)["revision"] == second["revision"]
    scene_studio.act(project, row["plan_id"], "undo")
    assert core.read_optional_json(receipt)["revision"] == first["revision"]
    row = scene_studio.preview_image(project, "herb", second["revision"])
    scene_studio.act(project, row["plan_id"])
    core.atomic_json(receipt, {"revision": "e" * 32})
    with pytest.raises(ValueError, match="changed after adoption"):
        scene_studio.act(project, row["plan_id"], "undo")


def test_image_preview_padding_pixels_and_guarded_publish(project):
    image = icon(project)
    original = image_assets.read_revision(project, "herb", image["revision"])[1] / "image.png"
    original_bytes = original.read_bytes()
    padded = scene_studio.pad_image(project, "herb", image["revision"], 0.1)
    out = image_assets.read_revision(project, "herb", padded["revision"])[1] / "image.png"
    pixels = image_assets.decode(out.read_bytes())
    box = pixels.getchannel("A").getbbox()
    assert box[0] >= 12 and box[1] >= 12 and box[2] <= 116 and box[3] <= 116
    assert original.read_bytes() == original_bytes
    assert padded["report"]["scene_fit"]["warnings"] == []
    row = scene_studio.preview_image(project, "herb", padded["revision"], [64, 64], [0.1, 0.1])
    evidence = scene_studio.evidence(project, row["plan_id"])
    composite = image_assets.decode(Path(evidence["images"][0]["path"]).read_bytes())
    background_pixel = composite.getpixel((0, 0))
    assert composite.getpixel((10, 10)) == background_pixel
    assert composite.getpixel((112, 92)) != background_pixel
    core.atomic_json(core.state_root(project) / "image-receipts/herb.json", {"revision": "f" * 32})
    with pytest.raises(ValueError, match="Image changed"):
        scene_studio.act(project, row["plan_id"])


def test_nine_slice_preserves_corners_and_reports_missing_states(project):
    image = icon(project)
    asset_requirements.save(
        project, "herb", {"kind": "ui", "states": ["normal", "hover", "pressed"]}
    )
    row = scene_studio.preview_image(project, "herb", image["revision"])
    assert row["report"]["states"] == {"normal": True, "hover": False, "pressed": False}
    source = Image.new("RGBA", (32, 32), "green")
    source.paste("red", (0, 0, 4, 4))
    result = scene_studio.nine_slice(source, (80, 40), [4, 4, 4, 4], Image.Resampling.NEAREST)
    assert result.crop((0, 0, 4, 4)).tobytes() == source.crop((0, 0, 4, 4)).tobytes()
    with pytest.raises(ValueError, match="rectangle extends"):
        scene_studio.preview_image(project, "herb", image["revision"], [100, 100], [1, 1])


def test_profiles_isolate_examples_preserve_versions_and_clear_old_positions(project):
    capture(project)
    first = scene_profiles.save(project, "药草店", locks={"palette": "温暖的浅木色"})
    scene_profiles.activate(project, first["profile_id"])
    assert scene_context.brief(project)["target"] is None
    assert scene_context.brief(project)["reference"]
    scene_profiles.save(project, "药草店", first["profile_id"], notes="低对比")
    art_samples.save(
        project, "药瓶", "icon", scene_context.read(project)["reference"]["path"], "保留轮廓"
    )
    assert len(art_samples.context(project, "icon")["samples"]) == 1
    planned = image_assets.plan(project, "shop_icon", "药瓶")
    second = scene_profiles.save(project, "地牢")
    scene_profiles.activate(project, second["profile_id"])
    assert art_samples.context(project, "icon")["samples"] == []
    assert image_assets.read_plan(project, planned["plan_id"])["scene_profile"]["name"] == "药草店"
    scene_profiles.activate(project, first["profile_id"], first["revision"])
    assert scene_profiles.brief(project)["locks"] == {"palette": "温暖的浅木色"}
    assert len(art_samples.context(project, "icon")["samples"]) == 1


@pytest.mark.parametrize(
    "settings",
    [
        {"min_size_m": [True, 0, 0]},
        {"clearance_m": [-1, 0, 0]},
        {"safe_area": [0.8, 0.1, 0.5, 0.5]},
        {"axis": [0, 0, 0]},
        {"states": ["../bad"]},
        {"sockets": [{"name": "grip", "position": [0, float("nan"), 0], "rotation": [0, 0, 0]}]},
    ],
)
def test_invalid_usage_rejected_before_write(project, settings):
    with pytest.raises(ValueError):
        asset_requirements.save(project, "tool", settings)
    assert asset_requirements.save(project, "tool")["revision"] is None


def test_usage_carried_to_both_plans_and_configures_existing_native_tools(project, monkeypatch):
    model(project, monkeypatch)
    row = asset_requirements.save(
        project,
        "chest",
        {
            "kind": "weapon",
            "sockets": [{"name": "grip", "position": [0.1, 0, 0], "rotation": [0, 0, 0]}],
        },
    )
    assert game_art.plan(project, "chest", "tool")["usage_requirements"] == row
    assert image_assets.plan(project, "chest", "tool icon")["usage_requirements"] == row
    task = asset_requirements.apply(project, "chest")
    payload = core.read_optional_json(
        core.state_root(project) / "actions" / (task["request_id"] + ".json")
    )
    assert '"command": "protection"' in payload["development_json"]
    assert '"mode": "set"' in payload["development_json"]


def test_all_operations_available_through_shared_gateway():
    for name in (
        "reference_scene",
        "preview_scene_model",
        "preview_scene_image",
        "scene_preview_images",
        "scene_preview_action",
        "repair_image_padding",
        "repair_scene_part",
        "asset_requirements",
        "apply_asset_requirements",
        "save_scene_profile",
        "activate_scene_profile",
        "remember_scene_example",
    ):
        assert production.dispatch(None, "describe", name)["action"] == name
