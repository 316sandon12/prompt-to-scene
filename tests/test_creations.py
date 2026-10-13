import json

import pytest
from PIL import Image

from prompt_to_scene import (
    art_samples,
    background,
    core,
    creations,
    game_art,
    image_assets,
    image_edits,
    production,
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


@pytest.fixture
def picture(project):
    path = project / "icon.png"
    im = Image.new("RGBA", (64, 64), (35, 150, 80, 255))
    im.putpixel((0, 0), (0, 0, 0, 0))
    im.save(path)
    return path


def test_sample_versions_survive_source_removal_and_enter_briefs(project, picture):
    first = art_samples.save(project, "Quiet material", "icon", str(picture), "Keep broad shapes")
    second = art_samples.save(
        project,
        "Noisy material",
        "icon",
        str(picture),
        "Avoid tiny lines",
        "avoid",
        first["sample_id"],
    )
    picture.unlink()
    brief = image_assets.plan(project, "item_icon", "a matching potion")
    assert "Avoid tiny lines" in brief["effective_prompt"] and not brief["references"]
    art_samples.restore(project, first["sample_id"], first["revision"])
    brief = image_assets.plan(project, "item_icon", "a matching potion")
    assert "Keep broad shapes" in brief["effective_prompt"] and brief["references"]
    assert first["sha256"] == art_samples.read(project, first["sample_id"])["sha256"]
    assert second["revision"] in art_samples.catalog(project)["samples"][0]["versions"]


def test_model_brief_receives_theme_and_sample_evidence(project, picture):
    art_samples.save(project, "Round silhouette", "model", str(picture), "Keep rounded edges")
    theme = art_samples.theme(project, {"accent": "#ABCDEF"})
    brief = game_art.plan(project, "vase", "A round vase")
    assert brief["art_samples"]["theme"]["version"] == theme["version"]
    assert brief["art_samples"]["samples"][0]["notes"] == "Keep rounded edges"
    with pytest.raises(ValueError):
        art_samples.theme(project, {"font_size": True})
    with pytest.raises(ValueError):
        art_samples.theme(project, {"accent": "javascript:bad"})


def test_region_edit_preserves_every_outside_pixel_and_rejects_stale_base(project, picture):
    original = image_assets.import_image(
        project, "icon", str(picture), width=64, height=64, preview_only=True
    )
    plan = image_edits.plan(
        project, "icon", original["revision"], [0.25, 0.25, 0.5, 0.5], "red cap"
    )
    mask = Image.open(plan["region_edit"]["mask_path"])
    assert mask.getpixel((0, 0))[3] == 255 and mask.getpixel((24, 24))[3] == 0
    patch = project / "patch.png"
    Image.new("RGBA", (32, 32), (230, 40, 20, 255)).save(patch)
    result = image_assets.import_image(
        project, "icon", str(patch), plan["plan_id"], preview_only=True
    )
    row, folder = image_assets.read_revision(project, "icon", result["revision"])
    actual, source = Image.open(folder / "image.png"), Image.open(picture)
    for y in range(64):
        for x in range(64):
            assert actual.getpixel((x, y)) == (
                (230, 40, 20, 255) if 16 <= x < 48 and 16 <= y < 48 else source.getpixel((x, y))
            )
    assert row["report"]["outside_selection_preserved"]
    with pytest.raises(ValueError, match="changed"):
        image_assets.import_image(project, "icon", str(patch), plan["plan_id"], preview_only=True)


@pytest.mark.parametrize(
    "rectangle",
    [[-1, 0, 1, 1], [0, 0, 0, 0.5], [0, 0, 2, 1], [False, 0, 1, 1], [0, 0, float("nan"), 1]],
)
def test_region_bounds_are_validated(project, picture, rectangle):
    original = image_assets.import_image(project, "icon", str(picture), preview_only=True)
    with pytest.raises(ValueError):
        image_edits.plan(project, "icon", original["revision"], rectangle, "edit")


def test_linked_item_records_expectation_and_preserves_field_intent(project, monkeypatch):
    monkeypatch.setattr(workflow, "inspect_asset", lambda *a: {"current": {"status": "imported"}})
    monkeypatch.setattr(background, "submit", lambda p, k, v, *a: v)
    root = game_art.root(project)
    core.atomic_json(root / "game-items/potion.json", {"revision": "a" * 32})
    spec = creations.create_item(project, "potion", model_asset_id="potion_model", name="New name")
    assert spec["expected_revision"] == "a" * 32 and spec["update_fields"] == []
    with pytest.raises(ValueError):
        creations.create_item(project, "potion", model_asset_id="potion_model", model={})
    with pytest.raises(ValueError):
        creations.create_item(project, "potion", model_asset_id="potion_model", render_icon=False)


def test_ui_contract_reuses_known_items_and_rejects_template_change(project):
    root = game_art.root(project)
    core.atomic_json(root / "game-items/potion.json", {"item_id": "potion"})
    task = creations.create_ui(project, "bag", item_ids=["potion"])
    command = core.read_optional_json(root / "actions" / (task["request_id"] + ".json"))
    spec = json.loads(json.loads(command["development_json"])["content_json"])
    assert spec["item_ids"] == ["potion"] and not spec["update_theme"]
    core.atomic_json(root / "game-screens/bag.json", {"kind": "inventory", "revision": "b" * 32})
    with pytest.raises(ValueError):
        creations.create_ui(project, "bag", "pause")
    with pytest.raises(ValueError):
        creations.create_ui(project, "another", item_ids=["unknown"])
    assert production.dispatch(project, "describe", "create_game_item")["parameters"]["item_id"][
        "required"
    ]


def test_masked_provider_frames_non_square_art_and_restores_exact_outside(project, picture):
    import io

    original = image_assets.import_image(
        project, "wide_icon", str(picture), width=192, height=64, preview_only=True
    )
    plan = image_edits.plan(
        project, "wide_icon", original["revision"], [0.3, 0.2, 0.3, 0.6], "gold seal"
    )
    frame = image_edits.provider_frame(plan, "auto")
    image, mask = Image.open(io.BytesIO(frame["image"])), Image.open(io.BytesIO(frame["mask"]))
    assert image.size == mask.size == (1536, 1024)
    assert mask.getpixel((0, 0))[3] == 255
    changed = io.BytesIO()
    Image.new("RGBA", image.size, (220, 160, 40, 255)).save(changed, format="PNG")
    data = image_edits.provider_result(changed.getvalue(), frame)
    result = image_edits.composite(project, plan, data)
    _, original_folder = image_assets.read_revision(project, "wide_icon", original["revision"])
    source = Image.open(original_folder / "image.png")
    left, top, right, bottom = plan["region_edit"]["box"]
    for y in range(64):
        for x in range(192):
            if not (left <= x < right and top <= y < bottom):
                assert result.getpixel((x, y)) == source.getpixel((x, y))
    assert result.getpixel((left + 1, top + 1)) == (220, 160, 40, 255)


def test_masked_provider_posts_matching_png_mask_and_does_not_retry(project, picture, monkeypatch):
    import base64
    import io

    from prompt_to_scene import image_provider

    original = image_assets.import_image(project, "icon", str(picture), preview_only=True)
    plan = image_edits.plan(project, "icon", original["revision"], [0.2, 0.2, 0.4, 0.4], "new seal")
    config = dict(
        endpoint="http://127.0.0.1:1234/v1",
        model="fixture",
        api_style="gpt_image",
        size="1024x1024",
        use_key=False,
    )
    monkeypatch.setattr(image_provider, "config", lambda: config)
    frame = image_edits.provider_frame(plan, config["size"])
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert request.full_url.endswith("/images/edits")
            assert b'name="mask"' in request.data and frame["mask"] in request.data
            assert frame["image"] in request.data
            return io.BytesIO(
                json.dumps(
                    {"data": [{"b64_json": base64.b64encode(frame["image"]).decode()}]}
                ).encode()
            )

    monkeypatch.setattr(image_provider.urllib.request, "build_opener", lambda *a: Opener())
    data = image_provider.request(config, plan)
    assert Image.open(io.BytesIO(data)).size == (256, 256)
    assert len(requests) == 1


def test_workbench_embeds_all_creation_scripts_and_retained_sample_image(project, picture):
    from prompt_to_scene import workbench

    sample = art_samples.save(project, "Jade", "material", str(picture), "Soft green glaze")
    page = workbench.page()
    assert 'id="creationGallery"' in page and "PTSModelViewer" in page
    assert '<script src="/' not in page
    assert workbench.image("art_sample", sample["revision"], sample["sample_id"])["url"].startswith(
        "data:image/png;base64,"
    )
