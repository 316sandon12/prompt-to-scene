import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from prompt_to_scene import clients, core, recipes, registry, setup, workflow


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PTS_PROJECT", raising=False)
    monkeypatch.delenv("PTS_UNITY_PROJECT", raising=False)
    root = tmp_path / "Unity with spaces"
    (root / "Assets").mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    return root


def test_connect_preserves_project_and_backs_up_bridge(project):
    manifest = project / "Packages/manifest.json"
    core.atomic_json(manifest, {"dependencies": {"custom": "1.0.0"}})
    registry.connect(str(project))
    assert registry.resolve().root == project
    assert registry.read()["projects"][0]["engine"] == "unity"
    plugin = project / "Packages/com.prompttoscene.bridge/custom.txt"
    plugin.write_text("artist changes")
    result = registry.connect(str(project))
    assert (Path(result["backup"]) / "custom.txt").read_text() == "artist changes"
    assert json.loads(manifest.read_text())["dependencies"] == {"custom": "1.0.0"}
    assert len(registry.read()["projects"]) == 1
    assert (project / ".gitignore").read_text().count(".prompt-to-scene/") == 1


def test_saved_blender_path_wins_over_system_default(project, monkeypatch):
    monkeypatch.delenv("PTS_BLENDER", raising=False)
    chosen = project / "My Blender"
    chosen.write_text("fixture executable")
    registry.connect(str(project), blender=str(chosen), install_bridge=False)
    assert core.blender_path() == str(chosen)


def test_unreal_connection_preserves_descriptor(tmp_path, monkeypatch):
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    descriptor = tmp_path / "Demo.uproject"
    core.atomic_json(
        descriptor,
        {
            "FileVersion": 3,
            "Custom": "keep",
            "Plugins": [
                {"Name": "Other", "Enabled": True},
                {"Name": "PythonScriptPlugin", "Enabled": False},
            ],
        },
    )
    assert registry.connect(str(descriptor))["restart_editor"]
    saved = json.loads(descriptor.read_text())
    assert saved["Custom"] == "keep"
    assert {p["Name"] for p in saved["Plugins"]} == {
        "Other",
        "PythonScriptPlugin",
        "EditorScriptingUtilities",
        "PromptToScene",
    }
    assert all(p["Enabled"] for p in saved["Plugins"])


@pytest.mark.parametrize("kind", recipes.DEFAULTS)
def test_recipes_validate_and_preserve_parameters(kind):
    script, recipe = recipes.prepare(kind, {"width": 2.3, "roughness": 0})
    compile(script, "recipe", "exec")
    _, changed = recipes.prepare(kind, {**recipe["parameters"], "color": [0, 1, 0]})
    assert changed["parameters"]["width"] == 2.3
    with pytest.raises(ValueError):
        recipes.prepare(kind, {"arbitrary_python": "bad"})
    with pytest.raises(ValueError):
        recipes.prepare(kind, {"height": float("nan")})


def test_queue_cancellation_and_exact_receipt(project):
    task = workflow.action(str(project), "transform", values={"move": [1, 0, 0]})
    revision = task["request_id"]
    assert workflow.job_status(str(project), revision)["status"] == "queued"
    assert workflow.cancel(str(project), revision)["status"] == "cancel_requested"
    root = core.state_root(project)
    assert (root / "cancel" / revision).exists()
    core.atomic_json(
        root / "action-receipts" / (revision + ".json"),
        {"status": "cancelled", "request_id": revision},
    )
    assert workflow.job_status(str(project), revision)["status"] == "cancelled"
    with pytest.raises(ValueError):
        workflow.action(str(project), "transform", scope="asset", values={"move": [1, 0, 0]})
    with pytest.raises(ValueError):
        workflow.job_status(str(project), "../escape")


def test_restore_only_successful_source_and_original_collider(project, monkeypatch):
    root = core.state_root(project)
    first, second = "a" * 32, "b" * 32
    for i, revision in enumerate((first, second)):
        core.atomic_json(
            root / "history/crate" / (revision + ".json"),
            {"status": "imported", "request_id": revision, "completed_utc": str(i)},
        )
    core.atomic_json(root / "receipts/crate.json", {"status": "imported", "request_id": second})
    old = root / "work/crate" / first
    core.atomic_json(old / "asset.json", {"recipe": {"kind": "crate"}})
    core.atomic_json(old / "request.json", {"collider": False})
    (old / "source.blend").write_bytes(b"fixture")
    monkeypatch.setattr(workflow, "submit", lambda *args, **kwargs: kwargs)
    restored = workflow.restore(str(project), "crate")
    assert restored["blend_file"] == str(old / "source.blend")
    assert restored["collider"] is False
    assert restored["recipe"]["kind"] == "crate"
    with pytest.raises(ValueError):
        workflow.restore(str(project), "crate", second)


def test_clients_share_one_runtime_and_connection(project):
    registry.connect(str(project), install_bridge=False)
    bundles = clients.create_bundles()
    codex = json.loads((bundles["codex"] / ".mcp.json").read_text())["mcpServers"][
        "prompt_to_scene"
    ]
    harness = json.loads((bundles["harness"] / "cordis.patch.yml").read_text())[0]["insert"][0][
        "config"
    ]
    for key in ("command", "args", "env"):
        assert codex[key] == harness[key]
    assert "permissions" not in codex
    assert (bundles["codex"] / "skills/prompt-to-scene/SKILL.md").exists()


def test_setup_rejects_foreign_origins_and_missing_token(project):
    registry.connect(str(project), install_bridge=False)
    with setup.Server() as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = server.origin + "/api/state"
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(url)
            assert error.value.code == 403
            headers = {"X-PTS-Token": server.token, "Origin": "https://example.com"}
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(urllib.request.Request(url, headers=headers))
            headers["Origin"] = server.origin
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as response:
                assert json.load(response)["active"] == str(project)
        finally:
            server.shutdown()
            thread.join()
