import json
from types import SimpleNamespace

import pytest

from prompt_to_scene import (
    background,
    compositions,
    core,
    generation,
    layout,
    parts,
    performance,
    preparation,
    quality,
    registry,
    reviews,
    workbench,
    workflow,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PTS_PROJECT", raising=False)
    monkeypatch.delenv("PTS_UNITY_PROJECT", raising=False)
    root = tmp_path / "Project"
    (root / "Assets").mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    registry.connect(str(root), install_bridge=False)
    return root


def box(engine="unity", name="table", angle=0, position=None):
    up = 1 if engine == "unity" else 2
    size = [2, 0.8, 1] if engine == "unity" else [2, 1, 0.8]
    low, high = [-v / 2 for v in size], [v / 2 for v in size]
    low[up], high[up] = 0, size[up]
    obj = {
        "id": name,
        "name": name,
        "asset_id": name,
        "position": [0, 0, 0],
        "rotation": [0, 0, 0],
        "scale": [1, 1, 1],
        "bounds_min": low,
        "bounds_max": high,
        "oriented_min": low,
        "oriented_max": high,
    }
    rotation = [0, 0, 0]
    rotation[up] = angle
    return layout.pose(obj, position or [0, 0, 0], rotation, [1, 1, 1], engine)


@pytest.mark.parametrize("engine", ["unity", "unreal"])
def test_arbitrary_yaw_layout_uses_oriented_bounds_and_faces_anchor(engine):
    anchor, chair = box(engine, angle=37), box(engine, "chair", position=[10, 10, 10])
    scene = {
        "engine": engine,
        "scene": "room",
        "context": [anchor, chair],
        "selected_context": [anchor],
        "assets": [anchor, chair],
    }
    plan = layout.plan(scene, [{"asset_id": "chair", "count": 2}], gap=0.4, face_anchor=True)
    assert len(plan["placements"]) == 2
    assert plan["anchor"]["rotation"] == anchor["rotation"]
    assert all(len(p["footprint"]) == 8 for p in plan["placements"])
    assert not layout.overlaps(*plan["placements"])
    anchor["rotation"][0] = 20
    with pytest.raises(ValueError, match="upright"):
        layout.plan(scene, [{"asset_id": "chair"}])


def test_oriented_collision_rejects_false_aabb_overlap():
    a = box(angle=45)
    b = box(name="chair", angle=45, position=[1.2, 0, 1.2])
    assert not layout.overlaps(a, b)
    assert all(
        min(a["bounds_max"][i], b["bounds_max"][i]) > max(a["bounds_min"][i], b["bounds_min"][i])
        for i in range(3)
    )


@pytest.mark.parametrize("engine", ["unity", "unreal"])
def test_scene_kit_rotates_whole_composition_without_overlaps(engine):
    objects = [
        box(engine, name="corner_" + n, position=[i * 4, 0, 0])
        for i, n in enumerate(("table", "chair", "shelf"))
    ]
    scene = {"scene": "room", "engine": engine, "context": objects, "assets": objects}
    planned = compositions.planned(scene, objects, [12, 0, 12], 37, objects[0], "reading_corner")
    assert len(planned["placements"]) == 3 and planned["snap_to_surface"]
    assert not any(
        layout.overlaps(a, b)
        for i, a in enumerate(planned["placements"])
        for b in planned["placements"][:i]
    )


def test_performance_uses_actual_metrics_and_marks_estimates():
    native = {
        "metrics": [
            {
                "id": "a",
                "mesh_key": "m",
                "triangles": 9000,
                "texture_bytes_estimate": 12 * 1024**2,
                "material_slots": 3,
            },
            {"id": "b", "mesh_key": "m", "triangles": 9000, "material_slots": 3},
        ]
    }
    result = performance.summarize(native, "mobile_prop")
    assert len(result["recommendations"]) == 5
    assert result["shared_mesh_instances"] == [["a", "b"]]
    assert "not compressed" in result["measurement_note"] and "FPS" in result["measurement_note"]
    assert preparation.options(quality="draft")["texture_size"] == 256


def test_quality_only_flags_measured_support_and_marks_possible_overlap():
    findings = quality.findings(
        {
            "metrics": [
                {"id": "a", "support_known": False, "support_gap": 2},
                {
                    "id": "b",
                    "support_known": True,
                    "support_gap": 0.2,
                    "overlap_candidates": ["a"],
                    "missing_materials": 1,
                },
            ]
        }
    )
    assert all(f["object_id"] == "b" for f in findings)
    assert {f["kind"] for f in findings} == {"missing_material", "floating", "possible_overlap"}
    assert next(f for f in findings if f["kind"] == "possible_overlap")["requires_visual_review"]


def test_refresh_after_preserves_original_camera_and_history(project):
    before = reviews.capture(str(project), "chair")
    root = core.state_root(project)
    for capture in [before]:
        core.atomic_json(
            root / "action-receipts" / (capture["request_id"] + ".json"),
            {"request_id": capture["request_id"], "status": "completed"},
        )
    after = reviews.capture(str(project), "chair", before["review_id"], "after")
    core.atomic_json(
        root / "action-receipts" / (after["request_id"] + ".json"),
        {"request_id": after["request_id"], "status": "completed"},
    )
    refreshed = reviews.capture(str(project), "chair", before["review_id"], "after", refresh=True)
    assert refreshed["request_id"] != after["request_id"]
    record = reviews.read(str(project), before["review_id"])
    assert record["before"] == before["request_id"] and record["previous_after"] == [
        after["request_id"]
    ]
    command = core.read_optional_json(root / "actions" / (refreshed["request_id"] + ".json"))
    assert command["frame_id"] == before["review_id"]


def test_quality_repair_limit_and_external_revision_conflict(project, monkeypatch):
    root = core.state_root(project)
    revision = "a" * 32
    path = root / "jobs" / revision / "state.json"
    state = {
        "kind": "quality",
        "status": "completed",
        "asset_id": "chair",
        "asset_revision": "b" * 32,
        "repair_count": 2,
    }
    core.atomic_json(path, state)
    with pytest.raises(ValueError, match="Two-repair"):
        quality.repair(str(project), revision, "seat", {"roughness": 0.2})
    state["repair_count"] = 0
    core.atomic_json(path, state)
    monkeypatch.setattr(workflow, "inspect_asset", lambda *a: {"current": {"request_id": "c" * 32}})
    with pytest.raises(ValueError, match="outside"):
        quality.repair(str(project), revision, "seat", {"roughness": 0.2})


def test_imported_parts_keep_normalized_source_and_enforce_independent_locks(
    project, tmp_path, monkeypatch
):
    source = tmp_path / "source.blend"
    source.write_bytes(b"source")
    original = tmp_path / "original.blend"
    original.write_bytes(b"original")
    info = {
        "current": {"status": "imported"},
        "source_blend": str(source),
        "metadata": {
            "preparation": {"settings": {"target_size": 2, "unit_scale": 0.01, "ground": True}},
            "provenance": {"provider": "local"},
            "report": {
                "parts": {
                    "body": {"objects": ["body"], "locks": {"geometry": True}},
                    "rim": {"objects": ["rim"], "locks": {}},
                }
            },
        },
    }
    monkeypatch.setattr(workflow, "inspect_asset", lambda *a: info)
    monkeypatch.setattr(workflow, "submit", lambda *a, **kw: kw)
    with pytest.raises(ValueError, match="Unlock"):
        parts.edit(str(project), "vase", "body", {"scale": [2, 2, 2]})
    result = parts.edit(str(project), "vase", "body", {"roughness": 0.4})
    assert result["blend_file"] == str(original)
    assert result["preparation"]["ground"] is False and result["preparation"]["unit_scale"] == 1
    assert result["preparation"]["target_size"] is None
    assert result["provenance"] == {"provider": "local"}
    with pytest.raises(ValueError, match="existing group"):
        parts.edit(str(project), "vase", "body", members=["rim"])


def test_resume_dead_worker_uses_saved_spec_once(project, monkeypatch):
    root = core.state_root(project)
    revision = "a" * 32
    path = root / "jobs" / revision / "spec.json"
    core.atomic_json(
        path,
        {"kind": "composition", "project": str(project), "request_id": revision, "parameters": {}},
    )
    core.atomic_json(
        path.with_name("state.json"),
        {"kind": "composition", "status": "building", "request_id": revision},
    )
    core.atomic_json(path.with_name("process.json"), {"pid": 42})
    monkeypatch.setattr(workflow, "process_alive", lambda pid: pid == 43)
    calls = []
    monkeypatch.setattr(
        workflow, "launch_worker", lambda p: calls.append(p) or SimpleNamespace(pid=43)
    )
    assert background.resume(str(project), revision)["status"] == "building"
    assert background.resume(str(project), revision)["status"] == "building"
    assert calls == [path]


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://remote.example/api",
        "https://user:pass@example.com",
        "https://example.com/?key=x",
        "file:///tmp/server",
    ],
)
def test_provider_configuration_rejects_unsafe_endpoint(project, endpoint):
    with pytest.raises(ValueError):
        generation.configure("local", endpoint)
    assert not (registry.home() / "providers.json").exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://assets.meshy.ai/a.glb",
        "https://evil.example/a.glb",
        "https://assets.meshy.ai@evil.example/a.glb",
        "https://assets.meshy.ai:8080/a.glb",
    ],
)
def test_meshy_downloads_cannot_leave_documented_hosts(monkeypatch, url):
    monkeypatch.setattr(generation.credentials, "get", lambda *_: "test-secret")
    with pytest.raises(ValueError):
        generation.Adapter("meshy").url(url)


def test_provider_keys_are_never_serialized_or_returned(project, monkeypatch):
    saved = []
    monkeypatch.setattr(generation.credentials, "put", lambda name, key: saved.append((name, key)))
    monkeypatch.setattr(generation.credentials, "get", lambda *_: "test-secret")
    response = generation.configure("local", "http://127.0.0.1:1234", "test-secret")
    assert saved == [("local", "test-secret")]
    assert (
        "test-secret" not in json.dumps(response) + (registry.home() / "providers.json").read_text()
    )


@pytest.mark.parametrize("uri", ["texture.png", "../private.png", "https://example.com/tex.png"])
def test_generated_glb_rejects_unembedded_dependencies(tmp_path, uri):
    import struct

    path = tmp_path / "model.glb"

    def write(value):
        data = json.dumps({"asset": {"version": "2.0"}, "images": [{"uri": value}]}).encode()
        data += b" " * (-len(data) % 4)
        content = struct.pack("<4sII", b"glTF", 2, 20 + len(data))
        content += struct.pack("<I4s", len(data), b"JSON") + data
        path.write_bytes(content)
        return len(content)

    size = write(uri)
    with pytest.raises(ValueError, match="embed"):
        generation.validate_glb(path, size)
    generation.validate_glb(path, write("data:image/png;base64,fixture"))


def test_paid_generation_requires_explicit_boolean_before_worker(project, monkeypatch):
    monkeypatch.setattr(generation.credentials, "get", lambda *_: "test-secret")
    for flag in (False, "false", 1):
        with pytest.raises(ValueError):
            generation.submit(str(project), "chair", "a chair", provider="meshy", allow_paid=flag)
    assert not list((core.state_root(project) / "jobs").glob("*/spec.json"))


def test_saved_provider_id_is_resumed_without_a_second_paid_submission(
    project, tmp_path, monkeypatch
):
    calls = []

    class Job:
        state = {}
        project = str(project)
        path = tmp_path / "spec.json"

        def check(self):
            pass

        def update(self, **values):
            self.state.update(values)

        def wait(self, task):
            return {**task, "status": "completed"}

    job = Job()

    class Adapter:
        interrupted = True

        def __init__(self, *a):
            pass

        def request(self, path, payload=None):
            calls.append((path, payload))
            if payload:
                return {"id": "saved-task"}
            if Adapter.interrupted:
                raise RuntimeError("network interrupted")
            return {"status": "SUCCEEDED", "model_url": "fixture.glb"}

        def download(self, url, destination, job):
            destination.write_bytes(b"glTF fixture")

    monkeypatch.setattr(generation, "Adapter", Adapter)
    monkeypatch.setattr(
        workflow, "submit", lambda *a, **k: {"request_id": "b" * 32, "asset_id": a[1]}
    )
    args = (job, "chair", "wood chair", "local", [], 1, True, preparation.options(), None)
    with pytest.raises(RuntimeError, match="interrupted"):
        generation.run(*args)
    assert job.state["candidates"][0]["model_task"] == "saved-task"
    Adapter.interrupted = False
    result = generation.run(*args)
    assert sum(payload is not None for _, payload in calls) == 1
    assert result["candidates"][0]["result"]["status"] == "completed"


def test_unknown_submission_outcome_does_not_create_another_charge(project, tmp_path, monkeypatch):
    state = {"candidates": [{"model_task_submitting": True}]}
    job = SimpleNamespace(
        state=state,
        project=str(project),
        path=tmp_path / "spec.json",
        check=lambda: None,
        update=lambda **v: state.update(v),
    )
    monkeypatch.setattr(
        generation,
        "Adapter",
        lambda *_: SimpleNamespace(request=lambda *a: pytest.fail("must not resubmit")),
    )
    with pytest.raises(RuntimeError, match="unknown"):
        generation.run(
            job, "chair", "wood chair", "local", [], 1, True, preparation.options(), None
        )


def test_workbench_routes_real_asset_parameter_and_blocks_arbitrary_actions(project, monkeypatch):
    monkeypatch.setattr(workflow, "inspect_asset", lambda project, name: {"asset_id": name})
    assert workbench.dispatch("inspect_asset", {"asset_id": "chair"}) == {"asset_id": "chair"}
    with pytest.raises(ValueError, match="Unknown"):
        workbench.dispatch("configure", {"api_key": "secret"})
    with pytest.raises(ValueError):
        workbench.dispatch("image", {"kind": "file"})


@pytest.mark.parametrize(
    "images,route",
    [
        (0, "/openapi/v2/text-to-3d"),
        (1, "/openapi/v1/image-to-3d"),
        (2, "/openapi/v1/multi-image-to-3d"),
    ],
)
def test_meshy_contract_text_refine_and_image_routes(project, tmp_path, monkeypatch, images, route):
    import hashlib

    calls = []

    class Job:
        state = {}
        project = str(project)
        path = tmp_path / "spec.json"

        def check(self):
            pass

        def update(self, **values):
            self.state.update(values)

        def wait(self, task):
            return {**task, "status": "completed"}

    class Adapter:
        def __init__(self, name):
            assert name == "meshy"

        def request(self, path, payload=None):
            calls.append((path, payload))
            if payload:
                return {
                    "result": "model-task" if payload.get("mode") != "preview" else "preview-task"
                }
            return {
                "status": "SUCCEEDED",
                "model_urls": {"glb": "https://assets.meshy.ai/fixture.glb"},
            }

        def download(self, url, destination, job):
            destination.write_bytes(b"glTF fixture")

    monkeypatch.setattr(generation, "Adapter", Adapter)
    monkeypatch.setattr(
        workflow, "submit", lambda *a, **kw: {"request_id": "b" * 32, "asset_id": a[1]}
    )
    image = tmp_path / "image.png"
    image.write_bytes(b"fixture image")
    refs = [{"path": str(image), "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}] * images
    generation.run(Job(), "chair", "a chair", "meshy", refs, 1, True, preparation.options(), None)
    submissions = [(path, payload) for path, payload in calls if payload is not None]
    assert all(path == route for path, _ in submissions)
    if not images:
        assert [payload["mode"] for _, payload in submissions] == ["preview", "refine"]
        assert submissions[1][1]["preview_task_id"] == "preview-task"
    else:
        key = "image_url" if images == 1 else "image_urls"
        assert len(submissions) == 1 and key in submissions[0][1]
    assert submissions[-1][1]["enable_pbr"] is True
