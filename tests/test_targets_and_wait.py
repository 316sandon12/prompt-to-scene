import json
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest

from prompt_to_scene.core import atomic_json, inspect_project, state_root, wait_for_status
from prompt_to_scene.targets import configured_target, resolve_target


@pytest.fixture
def unreal_project(tmp_path):
    descriptor = tmp_path / "Test.uproject"
    descriptor.write_text(json.dumps({"FileVersion": 3}))
    return descriptor


def test_unreal_file_resolves_even_with_multiple_projects(unreal_project):
    second = unreal_project.with_name("Other.uproject")
    second.write_text(unreal_project.read_text())
    assert resolve_target(unreal_project).project_file == unreal_project
    with pytest.raises(ValueError, match="multiple"):
        resolve_target(unreal_project.parent)


def test_ambiguous_engine_requires_explicit_choice(unreal_project):
    (unreal_project.parent / "Assets").mkdir()
    (unreal_project.parent / "ProjectSettings").mkdir()
    with pytest.raises(ValueError, match="Ambiguous"):
        resolve_target(unreal_project.parent)
    assert resolve_target(unreal_project.parent, "unity").engine == "unity"
    assert resolve_target(unreal_project).engine == "unreal"


def test_legacy_unity_config_and_new_unreal_config(tmp_path, unreal_project, monkeypatch):
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    monkeypatch.delenv("PTS_PROJECT", raising=False)
    monkeypatch.setenv("PTS_ENGINE", "unity")
    monkeypatch.setenv("PTS_UNITY_PROJECT", str(tmp_path))
    assert configured_target().engine == "unity"
    monkeypatch.setenv("PTS_PROJECT", str(unreal_project))
    monkeypatch.setenv("PTS_ENGINE", "auto")
    assert configured_target().engine == "unreal"


def test_old_receipt_cannot_satisfy_expected_revision(unreal_project):
    root = state_root(unreal_project.parent)
    atomic_json(root / "receipts/crate.json", {"status": "imported", "request_id": "a" * 32})
    result = wait_for_status(unreal_project, "crate", "b" * 32, 1)
    assert result["status"] == "superseded"
    assert result["latest_request_id"] == "a" * 32


def test_wait_receives_editor_completion(unreal_project):
    root = state_root(unreal_project.parent)
    revision = "a" * 32
    atomic_json(root / "inbox/crate.json", {"request_id": revision})

    def editor_finishes():
        atomic_json(root / "receipts/crate.json", {"status": "imported", "request_id": revision})
        (root / "inbox/crate.json").unlink()

    thread = threading.Timer(0.05, editor_finishes)
    thread.start()
    try:
        result = wait_for_status(unreal_project, "crate", revision, 2)
        assert result["status"] == "imported" and result["request_id"] == revision
    finally:
        thread.join()


def test_wait_timeout_is_not_success(unreal_project):
    atomic_json(state_root(unreal_project.parent) / "inbox/crate.json", {"request_id": "a" * 32})
    result = wait_for_status(unreal_project, "crate", "a" * 32, 0.01)
    assert result["status"] == "queued" and result["wait_timed_out"]


@pytest.mark.parametrize("wait", [-1, 31, float("nan")])
def test_wait_is_bounded(unreal_project, wait):
    with pytest.raises(ValueError, match="between 0 and 30"):
        wait_for_status(unreal_project, "crate", "a" * 32, wait)


def test_wait_requires_revision(unreal_project):
    with pytest.raises(ValueError, match="Pass request_id"):
        wait_for_status(unreal_project, "crate", wait_seconds=1)


def test_inspection_reports_stale_heartbeat_and_pending_assets(unreal_project, monkeypatch):
    monkeypatch.setenv("PTS_BLENDER", sys.executable)
    root = state_root(unreal_project.parent)
    atomic_json(
        root / "editor.json",
        {
            "updated_utc": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
    )
    atomic_json(root / "inbox/crate.json", {"request_id": "a" * 32})
    result = inspect_project(unreal_project)
    assert result["engine"] == "unreal" and not result["editor_responding"]
    assert result["assets"][0]["status"] == "queued"
