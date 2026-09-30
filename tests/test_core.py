import json
import sys
from pathlib import Path

import pytest

from prompt_to_scene.core import asset_id, atomic_json, build, position_values, state_root, status


@pytest.fixture
def project(tmp_path):
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    return tmp_path


@pytest.mark.parametrize("name", ["../outside", "Uppercase", "", "a/b", "a" * 65])
def test_rejects_invalid_asset_identifiers(name):
    with pytest.raises(ValueError):
        asset_id(name)


@pytest.mark.parametrize("position", [[1, 2], [0, float("nan"), 0], [float("inf"), 0, 0]])
def test_rejects_nonfinite_or_incomplete_positions(position):
    with pytest.raises(ValueError):
        position_values(position)


def test_old_success_cannot_confirm_new_request(project):
    root = state_root(project)
    atomic_json(root / "receipts/crate.json", {"status": "imported", "request_id": "old"})
    atomic_json(root / "inbox/crate.json", {"request_id": "new"})
    assert status(project, "crate")["status"] == "queued"
    assert status(project, "crate")["request_id"] == "new"
    atomic_json(root / "receipts/crate.json", {"status": "error", "request_id": "new"})
    assert status(project, "crate")["status"] == "error"


def test_pending_import_cannot_be_overwritten(project, monkeypatch):
    monkeypatch.setenv("PTS_BLENDER", sys.executable)
    path = state_root(project) / "inbox/crate.json"
    atomic_json(path, {"request_id": "pending"})
    with pytest.raises(ValueError, match="still queued"):
        build(project, "crate", "pass")
    assert json.loads(path.read_text())["request_id"] == "pending"
    assert not (state_root(project) / "locks/crate").exists()


def test_request_consumed_during_status_returns_latest_receipt(project, monkeypatch):
    root = state_root(project)
    request = root / "inbox/crate.json"
    atomic_json(request, {"request_id": "new"})
    atomic_json(root / "receipts/crate.json", {"status": "imported", "request_id": "old"})
    original_read = Path.read_text

    def consume_before_read(path, *args, **kwargs):
        if path == request:
            atomic_json(root / "receipts/crate.json", {"status": "imported", "request_id": "new"})
            request.unlink()
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", consume_before_read)
    assert status(project, "crate")["request_id"] == "new"


def test_failed_blender_process_never_queues_success(project, monkeypatch):
    # Python rejects Blender's flags, exercising a genuine failed child process.
    monkeypatch.setenv("PTS_BLENDER", sys.executable)
    with pytest.raises(RuntimeError, match="No import was queued"):
        build(project, "crate", "pass")
    assert status(project, "crate")["status"] == "unknown"
    assert not (state_root(project) / "locks/crate").exists()


def test_project_state_cannot_escape_via_symlink(project, tmp_path_factory):
    (project / ".prompt-to-scene").symlink_to(tmp_path_factory.mktemp("outside"))
    with pytest.raises(ValueError, match="inside the project"):
        state_root(project)
