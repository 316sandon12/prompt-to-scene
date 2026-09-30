import hashlib
import json
import time

import pytest

from prompt_to_scene import core, kits, preparation, registry, reviews, sources, workflow


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


@pytest.mark.parametrize(
    "values",
    [
        [],
        {"triangle_budget": True},
        {"triangle_budget": 30.5},
        {"texture_size": 256.0},
        {"unit_scale": float("nan")},
        {"lod_ratios": [0.25, 0.5]},
        {"lod_ratios": [1]},
        {"target_size": 0},
        {"ground": "false"},
        {"collision": "mesh"},
        {"up_axis": "W"},
        {"unknown": 1},
    ],
)
def test_invalid_preparation_is_rejected_before_starting_workers(values):
    with pytest.raises(ValueError):
        preparation.options(values)


def test_source_edit_after_submission_is_detected(tmp_path):
    path = tmp_path / "model.glb"
    path.write_bytes(b"original")
    source = sources.validate_source({"path": str(path)})
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed after submission"):
        sources.resolve(source, tmp_path, tmp_path / "cancel")
    assert path.read_bytes() == b"changed"


@pytest.mark.parametrize(
    "url",
    [
        "http://dl.polyhaven.org/file.glb",
        "https://polyhaven.com.evil.org/model.glb",
        "https://dl.polyhaven.org@127.0.0.1/model.glb",
        "https://dl.polyhaven.org:8080/model.glb",
        "file:///tmp/model.glb",
    ],
)
def test_provider_redirects_cannot_leave_allowed_https_hosts(url):
    with pytest.raises(ValueError):
        sources.Redirect().redirect_request(None, None, 302, "", {}, url)


def test_provider_dependencies_and_attribution_are_retained(tmp_path, monkeypatch):
    gltf, texture = b'{"asset":{"version":"2.0"}}', b"texture fixture"
    url = "https://dl.polyhaven.org/model.gltf"
    dependency = "https://dl.polyhaven.org/texture.jpg"
    entry = {
        "url": url,
        "md5": hashlib.md5(gltf).hexdigest(),
        "include": {
            "textures/color.jpg": {"url": dependency, "md5": hashlib.md5(texture).hexdigest()},
        },
    }
    manifest = json.dumps({"gltf": {"1k": {"gltf": entry}}}).encode()
    responses = {sources.API + "/files/vase": manifest, url: gltf, dependency: texture}
    monkeypatch.setattr(sources, "fetch", lambda url, *a, **kw: responses[url])
    path, provenance = sources.resolve(
        {"provider": "polyhaven", "id": "vase"}, tmp_path, tmp_path / "cancel"
    )
    assert path.read_bytes() == gltf
    assert (tmp_path / "textures/color.jpg").read_bytes() == texture
    assert provenance["files"]["textures/color.jpg"] == hashlib.sha256(texture).hexdigest()
    assert provenance["license"] == "CC0-1.0" and provenance["credit"] == sources.CREDIT
    responses[dependency] = b"modified transfer"
    with pytest.raises(ValueError, match="checksum"):
        sources.resolve({"provider": "polyhaven", "id": "vase"}, tmp_path, tmp_path / "cancel")


@pytest.mark.parametrize(
    "name", ["../outside", "/tmp/outside", "C:/outside", "x\\..\\outside", ".secret"]
)
def test_provider_dependencies_cannot_escape_the_job_folder(name):
    with pytest.raises(ValueError):
        sources.safe_relative(name)


def test_catalog_offline_fallback_preserves_pagination_and_credit(project, monkeypatch):
    core.atomic_json(
        registry.home() / "catalog/polyhaven-models.json",
        {
            "time": time.time() - 4000,
            "assets": {
                "a": {"name": "Wood chair", "tags": ["furniture"]},
                "b": {"name": "Wood table", "tags": ["furniture"]},
                "c": {"name": "Ceramic vase", "tags": []},
            },
        },
    )

    def offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(sources, "fetch", offline)
    first = sources.search("wood", limit=1)
    second = sources.search("wood", limit=1, offset=first["next_offset"])
    assert first["catalog_cached"] and first["total"] == 2 and first["credit"] == sources.CREDIT
    assert first["assets"][0]["id"] != second["assets"][0]["id"]
    assert second["next_offset"] is None


def test_review_requires_finished_before_and_keeps_asset_camera_identity(project):
    first = reviews.capture(str(project), "vase", view="front")
    root = core.state_root(project)
    review = first["review_id"]
    with pytest.raises(ValueError, match="Wait"):
        reviews.capture(str(project), "vase", review, "after", "front")
    with pytest.raises(ValueError, match="same asset"):
        reviews.capture(str(project), "vase", review, "before", "back")
    core.atomic_json(
        root / "action-receipts" / (first["request_id"] + ".json"),
        {
            "status": "completed",
            "request_id": first["request_id"],
        },
    )
    assert (
        reviews.capture(str(project), "vase", review, "before", "front")["request_id"]
        == first["request_id"]
    )
    second = reviews.capture(str(project), "vase", review, "after", "front")
    action = core.read_optional_json(root / "actions" / (second["request_id"] + ".json"))
    assert action["frame_id"] == review and action["review_stage"] == "after"
    assert reviews.read(str(project), review)["captures"]["before"]["status"] == "completed"


def test_kit_partial_failure_reports_already_started_assets(project, monkeypatch):
    from prompt_to_scene import authoring

    calls = []

    def submit(*args, **kwargs):
        calls.append(args[1])
        if len(calls) == 2:
            raise ValueError("busy")
        return {"asset_id": args[1], "request_id": "a" * 32}

    monkeypatch.setattr(authoring, "submit_recipe", submit)
    result = kits.create(str(project), "reading_corner", "corner")
    assert result["status"] == "partial" and len(result["tasks"]) == 1
    assert calls == ["corner_chair", "corner_table"]


def test_publish_preview_carries_provenance_and_recipe(project, monkeypatch):
    root = core.state_root(project)
    revision = "a" * 32
    core.atomic_json(
        root / "jobs" / revision / "state.json",
        {
            "asset_id": "vase",
            "status": "completed",
            "preview_only": True,
        },
    )
    metadata = {"provenance": {"provider": "polyhaven", "id": "vase"}, "collider": False}
    core.atomic_json(root / "work/vase" / revision / "asset.json", metadata)
    core.atomic_json(
        root / "work/vase" / revision / "request.json",
        {
            "auto_place": False,
            "position": [2, 0, 3],
        },
    )
    monkeypatch.setattr(workflow, "submit", lambda *a, **kw: kw)
    result = sources.publish(str(project), "vase", revision)
    assert result["provenance"] == metadata["provenance"] and not result["collider"]
    assert result["position"] == [2, 0, 3]
    with pytest.raises(ValueError):
        sources.publish(str(project), "other", revision)
