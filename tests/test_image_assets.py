import base64
import importlib.util
import io
import json
import os
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

from prompt_to_scene import (
    background,
    core,
    game_art,
    image_provider,
    production,
    registry,
    workbench,
)
from prompt_to_scene import (
    image_assets as images,
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


def png(size=(64, 32), alpha=True):
    image = Image.new("RGBA", size, (60, 140, 90, 255))
    if alpha:
        image.putpixel((0, 0), (0, 0, 0, 0))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def source(project):
    path = project / "source.png"
    path.write_bytes(png())
    return path


def test_brief_retains_project_style_and_reference_even_after_source_cleanup(project, source):
    game_art.configure(project, {"world": "herbalist village", "gameplay": "gather and craft"})
    result = images.plan(project, "potion", "Healing potion", reference_paths=[str(source)])
    source.unlink()
    game_art.configure(project, {"world": "different world"})
    saved = images.read_plan(project, result["plan_id"])
    assert saved["context"]["world"] == "herbalist village"
    assert "gather and craft" in saved["effective_prompt"]
    assert saved["palette"]["wood"].startswith("#")
    assert Path(saved["references"][0]["path"]).is_file()


def test_transparency_is_not_invented_and_pixel_art_is_not_blurred():
    with pytest.raises(ValueError, match="no real transparency"):
        images.prepare(png(alpha=False), images.settings())
    with pytest.raises(ValueError, match="opaque source"):
        images.prepare(png(), images.settings("background"))
    with pytest.raises(ValueError, match="whole-number"):
        images.prepare(png(), images.settings(width=100, height=100, pixel_art=True))
    result, report = images.prepare(png(), images.settings(width=128, height=128, pixel_art=True))
    assert result.size == (128, 128) and report["has_alpha"]
    assert {color for count, color in result.getcolors()} <= {(0, 0, 0, 0), (60, 140, 90, 255)}


@pytest.mark.parametrize(
    "values",
    [
        {"width": True},
        {"height": 8192},
        {"border": [20, 0, 240, 0]},
        {"border": [0, 0, 0, 1]},
        {"transparent": "false"},
        {"fit": "stretch"},
    ],
)
def test_invalid_settings_are_rejected(values):
    with pytest.raises(ValueError):
        images.settings(**values)


def test_image_import_preserves_source_and_prepared_revisions_without_blender(
    project, source, monkeypatch
):
    monkeypatch.setattr(core, "blender_path", lambda: pytest.fail("Images must not start Blender"))
    result = images.import_image(
        project, "potion", str(source), width=128, height=128, preview_only=True
    )
    source.unlink()
    saved, folder = images.read_revision(project, "potion", result["revision"])
    assert (folder / "source").read_bytes() == png()
    assert saved["report"]["output_size"] == [128, 128]
    assert not (core.state_root(project) / "actions").exists()
    preview = workbench.image("game_image", result["revision"], "potion")
    assert base64.b64decode(preview["url"].split(",")[1]).startswith(b"\x89PNG")
    task = images.publish(project, "potion", result["revision"])
    assert images.publish(project, "potion", result["revision"])["request_id"] == task["request_id"]
    assert len(list((core.state_root(project) / "actions").glob("*.json"))) == 1
    (folder / "image.png").write_bytes(png((20, 20)))
    with pytest.raises(ValueError, match="changed"):
        images.publish(project, "potion", result["revision"])


def unreal_image_module(monkeypatch):
    directory = (
        Path(__file__).resolve().parents[1]
        / "unreal/PromptToScene/Content/Python/prompt_to_scene_unreal"
    )
    package = types.ModuleType("image_bridge_fixture")
    package.__path__ = [str(directory)]
    monkeypatch.setitem(sys.modules, "image_bridge_fixture", package)
    spec = importlib.util.spec_from_file_location(
        "image_bridge_fixture.image_assets", directory / "image_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_rejects_stale_or_tampered_images_before_native_writes(project, source, monkeypatch):
    bridge = unreal_image_module(monkeypatch)
    prepared = images.import_image(project, "potion", str(source), preview_only=True)
    task = images.publish(project, "potion", prepared["revision"])
    root = core.state_root(project)
    request = core.read_optional_json(root / "actions" / (task["request_id"] + ".json"))
    data, path, current = bridge.validate(request, root)
    assert path.is_file() and current is None
    core.atomic_json(root / "image-receipts/potion.json", {"revision": "f" * 32, "kind": "icon"})
    with pytest.raises(ValueError, match="changed after"):
        bridge.validate(request, root)
    data["expected_revision"] = "f" * 32
    data["file"] = "../../outside.png"
    with pytest.raises(ValueError, match="retained revision"):
        bridge.validate({**request, "image_json": json.dumps(data)}, root)


def test_plan_cannot_be_attached_to_another_image(project, source):
    plan = images.plan(project, "potion", "Potion")
    with pytest.raises(ValueError, match="different asset"):
        images.import_image(project, "shield", str(source), plan["plan_id"])


def test_remote_generation_needs_explicit_choice_and_never_resends_uncertain_request(
    project, monkeypatch
):
    monkeypatch.setenv("PTS_IMAGE_API_KEY", "fixture-secret")
    config = image_provider.configure(endpoint="https://images.example/v1", model="fixture")
    assert "fixture-secret" not in json.dumps(config)
    plan = images.plan(project, "potion", "Potion")
    with pytest.raises(ValueError, match="allow_remote"):
        images.generate(project, plan["plan_id"])
    job = SimpleNamespace(
        project=project,
        path=core.state_root(project) / "jobs/test/spec.json",
        state={"provider_started": True},
    )
    job.path.parent.mkdir(parents=True)
    monkeypatch.setattr(image_provider, "request", lambda *a: pytest.fail("Must not resubmit"))
    with pytest.raises(ValueError, match="unknown outcome"):
        images.run(job, plan["plan_id"], {}, False)


def test_local_api_generates_previews_and_resume_reuses_saved_pixels(project, source, monkeypatch):
    monkeypatch.setenv("PTS_IMAGE_API_KEY", "fixture-secret")
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            calls.append((self.path, body, self.headers["Authorization"]))
            result = json.dumps({"data": [{"b64_json": base64.b64encode(png()).decode()}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(result)))
            self.end_headers()
            self.wfile.write(result)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            image_provider.configure(
                endpoint=f"http://127.0.0.1:{server.server_port}/v1", model="fixture"
            )
            design = images.plan(project, "potion", "Potion", reference_paths=[str(source)])
            job = SimpleNamespace(
                project=project,
                path=core.state_root(project) / "jobs/test/spec.json",
                state={},
                check=lambda: None,
            )
            job.path.parent.mkdir(parents=True)
            job.update = lambda **values: job.state.update(values)
            first = images.run(job, design["plan_id"], image_provider.config(), True)
            second = images.run(job, design["plan_id"], image_provider.config(), True)
            assert len(calls) == 1 and calls[0][0] == "/v1/images/edits"
            assert b'name="image[]"' in calls[0][1] and b"herbalist" not in calls[0][1]
            assert first["image_revision"] == second["image_revision"]
            assert calls[0][2] == "Bearer fixture-secret"
        finally:
            server.shutdown()
            thread.join()


def test_mixed_production_plan_and_gateway_discovery(project, source, monkeypatch):
    monkeypatch.setattr(background, "submit", lambda project, kind, parameters, *a: parameters)
    spec = production.submit(
        project,
        [
            dict(asset_id="chair", kind="chair"),
            dict(asset_id="potion", method="image", source=str(source)),
        ],
    )
    assert spec["items"][1]["design"]["settings"]["kind"] == "icon"
    actions = production.dispatch(project, query="image")["actions"]
    assert {"plan_image", "generate_image", "import_image", "image_preview"} <= {
        a["action"] for a in actions
    }
    for name in ("plan_image", "import_image", "image_provider"):
        assert production.dispatch(project, "describe", name)["example"]
    with pytest.raises(ValueError, match="requires a model"):
        production.submit(
            project,
            [dict(asset_id="portrait", method="image", source=str(source))],
            review_view="game",
        )


def test_restoring_an_older_image_creates_a_new_native_import(project, source):
    prepared = images.import_image(project, "potion", str(source), preview_only=True)
    task = images.publish(project, "potion", prepared["revision"])
    root = core.state_root(project)
    core.atomic_json(
        root / "action-receipts" / (task["request_id"] + ".json"),
        {"status": "completed", "request_id": task["request_id"]},
    )
    core.atomic_json(root / "image-receipts/potion.json", {"revision": "a" * 32, "kind": "icon"})
    (root / "actions" / (task["request_id"] + ".json")).unlink()
    restored = images.publish(project, "potion", prepared["revision"])
    assert restored["request_id"] != task["request_id"]
    request = core.read_optional_json(root / "actions" / (restored["request_id"] + ".json"))
    assert json.loads(request["image_json"])["expected_revision"] == "a" * 32


def test_changing_provider_does_not_send_the_previous_servers_key(project, monkeypatch):
    monkeypatch.setenv("PTS_IMAGE_API_KEY", "fixture-secret")
    first = image_provider.configure(endpoint="https://first.example/v1", model="a")
    assert image_provider.key_for(first) == "fixture-secret"
    second = image_provider.configure(endpoint="https://second.example/v1", model="b")
    assert image_provider.key_for(second) is None and not second["has_key"]


def test_installed_compact_mcp_delivers_real_image_pixels_without_extra_tools(project):
    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from prompt_to_scene.server import main; main()"],
            env={**os.environ, "PTS_COMPACT_TOOLS": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert len((await session.list_tools()).tools) == 3
                result = await session.call_tool(
                    "game_workflow", {"operation": "execute", "action": "image_example"}
                )
                assert not result.isError, result
                task = json.loads(result.content[0].text)
                preview = await session.call_tool(
                    "game_workflow",
                    {
                        "operation": "execute",
                        "action": "image_preview",
                        "values": {"asset_id": task["asset_id"], "revision": task["revision"]},
                    },
                )
                assert not preview.isError, preview
                assert any(
                    row.type == "image" and row.mimeType == "image/png" for row in preview.content
                )

    anyio.run(exercise)
