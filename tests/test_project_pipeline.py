import hashlib
import json
import os
import time

import pytest

from prompt_to_scene import (
    art_adaptation,
    core,
    intake,
    native_locations,
    project_library,
    project_profiles,
    semantics,
    workflow,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "Game"
    (root / "Assets").mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    monkeypatch.setenv("PTS_PROJECT", str(root))
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    return root


def test_profile_persists_merges_and_cannot_put_inbox_in_assets(project):
    profile = project_profiles.configure(
        project,
        "save",
        {
            "preparation": {"texture_size": 1024},
            "organization": {"rules": {"model": {"prefix": "Mesh_"}}},
        },
    )
    assert project_profiles.read(project) == profile
    assert (project / project_profiles.FILE).is_file()
    assert (
        project_profiles.preparation_defaults(project, {"texture_size": 256})["texture_size"] == 256
    )
    with pytest.raises(ValueError, match="outside engine"):
        project_profiles.configure(project, "save", {"intake": {"folder": "Assets/Incoming"}})
    assert project_profiles.read(project) == profile


def test_new_names_follow_profile_old_assets_keep_paths(project):
    old = native_locations.layout(project, "old_chair")
    project_profiles.configure(
        project,
        "save",
        {"organization": {"destination": "Assets/World", "rules": {"model": {"prefix": "Mesh_"}}}},
    )
    assert native_locations.layout(project, "old_chair") == old
    new = native_locations.layout(project, "new_chair")
    assert new["folder"] == "Assets/World/PromptToScene/new_chair"
    assert new["model"] == "Models/Mesh_NewChair"
    assert new["materials"] == "Materials/"


def test_intake_idempotent_settled_and_dependency_changes(project, monkeypatch):
    folder = intake.inbox(project)
    folder.mkdir()
    model = folder / "chair.gltf"
    model.write_text(json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "chair.bin"}]}))
    data = folder / "chair.bin"
    data.write_bytes(b"geometry")
    tasks = []

    def submit(project, kind, parameters, asset_id):
        task = {"request_id": str(len(tasks)).zfill(32), "status": "building"}
        tasks.append((asset_id, parameters, task))
        return task

    monkeypatch.setattr(intake.background, "submit", submit)
    monkeypatch.setattr(workflow, "job_status", lambda *args: {"status": "completed"})
    assert not intake.manage(project, "scan")["tasks"]
    for path in (model, data):
        os.utime(path, (time.time() - 10,) * 2)
    assert len(intake.manage(project, "scan")["tasks"]) == 1
    assert not intake.manage(project, "scan")["tasks"]
    data.write_bytes(b"revised geometry")
    os.utime(data, (time.time() - 10,) * 2)
    assert len(intake.manage(project, "scan")["tasks"]) == 1
    assert tasks[0][0] == tasks[1][0]  # Stable asset identity across updates.
    assert tasks[0][1]["fingerprint"] != tasks[1][1]["fingerprint"]
    assert data.read_bytes() == b"revised geometry"


def test_intake_rejects_external_dependencies_and_waits_for_active_job(project, monkeypatch):
    folder = intake.inbox(project)
    folder.mkdir()
    model = folder / "bad.gltf"
    model.write_text(json.dumps({"buffers": [{"uri": "../secret.bin"}]}))
    assert intake.manage(project, "scan")["errors"]
    model.write_text("{}")
    os.utime(model, (time.time() - 10,) * 2)
    fingerprint, _ = intake.fingerprint(model, folder)
    core.atomic_json(
        core.state_root(project) / "intake.json",
        {"bad.gltf": {"request_id": "a" * 32, "fingerprint": fingerprint}},
    )
    monkeypatch.setattr(workflow, "job_status", lambda *args: {"status": "building"})
    assert intake.manage(project, "retry")["skipped"][0]["reason"] == "already running"


def proof(project):
    root = core.state_root(project)
    identifier = "a" * 32
    image = root / "previews" / (identifier + ".png")
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"native capture fixture")
    core.atomic_json(
        root / "semantic-evidence" / (identifier + ".json"),
        {
            "path": "Assets/Chair.prefab",
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        },
    )
    return identifier, image


def test_semantic_search_and_corrections_preserve_evidence(project):
    identifier, image = proof(project)
    desc = dict(
        name="旧木椅", object_type="chair", uses=["酒馆 tavern"], materials=["wood"], confidence=0.8
    )
    result = semantics.save(project, identifier, desc, corrected=True)
    entries = [{"name": "Cube", "path": "Assets/Chair.prefab", "tags": []}]
    assert project_library.rank(entries, "酒馆", {result["path"]: result})
    project_library.annotate(project, result["path"], tags=["prop"])
    saved = core.read_optional_json(core.state_root(project) / "project-library.json")
    assert saved[result["path"]]["semantic"]["corrected"]
    with pytest.raises(ValueError, match="corrected"):
        semantics.save(project, identifier, desc)
    image.write_bytes(b"different image")
    with pytest.raises(ValueError, match="changed"):
        semantics.save(project, identifier, desc, corrected=True)


def test_remote_vision_requires_explicit_send_and_credentials_stay_out_of_project(
    project, monkeypatch
):
    stored = []
    monkeypatch.setattr(semantics.credentials, "put", lambda *args: stored.append(args))
    semantics.configure("https://vision.example/v1", "vision-model", "secret")
    assert stored == [("vision", "secret")]
    with pytest.raises(ValueError, match="allow_remote"):
        semantics.start(project, ["Assets/Chair.prefab"], use_provider=True)
    assert "secret" not in (semantics.registry.home() / "vision.json").read_text()


def test_adaptation_selection_uses_saved_plan_rows(project, monkeypatch):
    identifier = "b" * 32
    core.atomic_json(
        core.state_root(project) / "adaptation" / (identifier + ".json"), {"entries": [{"id": "2"}]}
    )
    with pytest.raises(ValueError, match="row IDs"):
        art_adaptation.start(project, mode="apply", plan_id=identifier, selected=["unknown"])
    monkeypatch.setattr(art_adaptation.development, "request", lambda *args, **values: values)
    assert art_adaptation.start(project, mode="apply", plan_id=identifier, selected=["2"])[
        "slots"
    ] == ["2"]


def test_vision_adapter_sends_native_image_and_validates_structured_response(project, monkeypatch):
    import base64
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    _, image = proof(project)
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            observed.append(data)
            response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                dict(name="Fixture cube", object_type="cube", confidence=0.6)
                            )
                        }
                    }
                ]
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(semantics.credentials, "get", lambda *_: None)
    try:
        semantics.configure("http://127.0.0.1:" + str(server.server_port) + "/v1", "fixture")
        result = semantics.infer(image, {"size": [1, 1, 1]})
        assert result["confidence"] == 0.6
        assert observed[0]["model"] == "fixture"
        encoded = observed[0]["messages"][0]["content"][1]["image_url"]["url"].split(",", 1)[1]
        assert base64.b64decode(encoded) == image.read_bytes()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_user_correction_follows_organized_asset_evidence(project):
    identifier, _ = proof(project)
    root = core.state_root(project)
    core.atomic_json(
        root / "project-library.json", {"Assets/New/Chair.prefab": {"evidence_ids": [identifier]}}
    )
    result = semantics.save(
        project, identifier, dict(name="Chair", object_type="chair", confidence=1), corrected=True
    )
    assert result["path"] == "Assets/New/Chair.prefab"
    assert "Assets/Chair.prefab" not in core.read_optional_json(root / "project-library.json")
