"""Local, token-protected setup/dashboard. Packaged users double-click an app."""

import json
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import urlsplit

from . import (
    __version__,
    authoring,
    clients,
    compositions,
    core,
    game_art,
    generation,
    kits,
    performance,
    quality,
    registry,
    reviews,
    sources,
    studies,
    workbench,
    workflow,
)


def pick(kind="project"):
    if sys.platform == "darwin":
        script = (
            'POSIX path of (choose folder with prompt "Choose your Unity or Unreal project")'
            if kind == "project"
            else (
                'POSIX path of (choose file with prompt "Choose a GLB, glTF, FBX or Blender model")'
                if kind == "asset"
                else 'POSIX path of (choose file with prompt "Choose Blender or its executable")'
            )
        )
        if kind == "reference":
            script = (
                'POSIX path of (choose file with prompt "Choose a PNG or JPEG reference image")'
            )
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        value = result.stdout.strip()
        if kind == "blender" and value.endswith(".app/"):
            value += "Contents/MacOS/Blender"
        if kind == "blender" and value.endswith(".app"):
            value += "/Contents/MacOS/Blender"
        return value
    if sys.platform == "win32":
        dialog = "FolderBrowserDialog" if kind == "project" else "OpenFileDialog"
        prop = "SelectedPath" if kind == "project" else "FileName"
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$ptsDialog = New-Object System.Windows.Forms."
            + dialog
            + "; if($ptsDialog.ShowDialog() -eq 'OK') { $ptsDialog."
            + prop
            + " }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.stdout.strip()
    raise ValueError(
        "Native picker is available on macOS/Windows. Paste the project path on this platform."
    )


def state():
    result = {
        "version": __version__,
        "projects": registry.discover(),
        "active": registry.read().get("active"),
        "blender": registry.find_blender(),
        "clients": clients.inventory(),
        "recipes": authoring.recipes.DEFAULTS,
        "providers": generation.inventory(),
        "usage_presets": performance.PRESETS,
    }
    try:
        target = registry.resolve()
        result["active"] = str(target.project_file or target.root)
        result["target"] = core.inspect_project(target.project_file or target.root)
        result["library"] = authoring.catalog(str(target.project_file or target.root))
        result["art_brief"] = quality.brief(None)
        result["game_art"] = game_art.configure(None)
        result["style_match"] = core.read_optional_json(game_art.root(None) / "style-match.json")
        result["layouts"] = compositions.templates(None)
        root = core.state_root(target.root)
        jobs = sorted(
            (root / "jobs").glob("*/state.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:20]
        result["studies"] = [
            studies.read(None, p.stem)
            for p in sorted(
                (root / "studies").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            )[:5]
        ]
        result["assets"] = []
        moving_parts = {
            (core.read_optional_json(p) or {}).get("moving_asset_id")
            for p in (root / "interactions").glob("*.json")
        }
        for path in (root / "receipts").glob("*.json"):
            if path.stem in moving_parts:
                continue
            receipt = core.read_optional_json(path) or {}
            if receipt.get("status") != "imported":
                history = [
                    core.read_optional_json(p)
                    for p in (root / "history" / path.stem).glob("*.json")
                ]
                imported = [r for r in history if r and r.get("status") == "imported"]
                receipt = max(imported, key=lambda r: r.get("completed_utc", ""), default={})
            if receipt:
                result["assets"].append(receipt)
        task_paths = [(p.stat().st_mtime, p.parent.name) for p in jobs]
        for folder in ("actions", "action-receipts"):
            for path in sorted(
                (root / folder).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            )[:30]:
                item = core.read_optional_json(path) or {}
                if item.get("operation") == "develop" or item.get("development"):
                    task_paths.append((path.stat().st_mtime, path.stem))
        revisions = list(
            dict.fromkeys(revision for _, revision in sorted(task_paths, reverse=True))
        )[:20]
        result["tasks"] = [
            workflow.job_status(str(target.project_file or target.root), revision)
            for revision in revisions
        ]
        result["reviews"] = [
            reviews.read(None, p.stem)
            for p in sorted(
                (root / "reviews").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            )[:3]
        ]
    except (ValueError, OSError) as error:
        result["connection_message"] = str(error)
    return result


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # This loopback-only app does not need a potentially blocking reverse DNS lookup.
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.token = secrets.token_urlsafe(32)
        self.origin = "http://127.0.0.1:" + str(self.server_port)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, value, status=200, content_type="application/json"):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https://cdn.polyhaven.com; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        origin = self.headers.get("Origin")
        return (
            self.headers.get("Host") == "127.0.0.1:" + str(self.server.server_port)
            and origin in {None, self.server.origin}
            and secrets.compare_digest(self.headers.get("X-PTS-Token", ""), self.server.token)
        )

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in {"/workshop.js", "/workbench.js"} and self.headers.get(
            "Host"
        ) == "127.0.0.1:" + str(self.server.server_port):
            self.reply(
                Path(__file__).with_name(path[1:]).read_bytes(),
                content_type="text/javascript; charset=utf-8",
            )
            return
        if path in {"/", "/workbench"} and self.headers.get("Host") == "127.0.0.1:" + str(
            self.server.server_port
        ):
            page = (
                Path(__file__)
                .with_name("workbench.html" if path == "/workbench" else "setup.html")
                .read_bytes()
            )
            self.reply(page, content_type="text/html; charset=utf-8")
            return
        if not self.authorized():
            self.reply({"error": "Invalid local setup token/origin"}, 403)
            return
        try:
            if path == "/api/state":
                self.reply(state())
            elif path.startswith("/api/studio/"):
                fields = path.split("/")
                if len(fields) != 7:
                    raise ValueError("Invalid studio preview path")
                image = studies.preview_path(None, fields[4], fields[5], fields[6])
                self.reply(image.read_bytes(), content_type="image/png")
            elif path.startswith("/api/asset/"):
                self.reply(workflow.inspect_asset(None, path.rsplit("/", 1)[1]))
            elif path.startswith("/api/preview/"):
                revision = workflow.identifier(path.rsplit("/", 1)[1])
                root = core.state_root(registry.resolve().root)
                image = (root / "previews" / (revision + ".png")).resolve()
                if not image.is_relative_to(root) or image.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError("Invalid preview")
                self.reply(image.read_bytes(), content_type="image/png")
            else:
                self.reply({"error": "Not found"}, 404)
        except (OSError, ValueError) as error:
            self.reply({"error": str(error)}, 400)

    def do_POST(self):
        if not self.authorized():
            self.reply({"error": "Invalid local setup token/origin"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 100000:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            operation = urlsplit(self.path).path
            if operation == "/api/workbench":
                result = workbench.dispatch(**data)
            elif operation == "/api/provider":
                result = generation.configure(**data)
            elif operation == "/api/pick":
                result = {"path": pick(data.get("kind", "project"))}
            elif operation == "/api/connect":
                result = registry.connect(data["project"], data.get("blender") or None)
            elif operation == "/api/client":
                result = clients.install(
                    data["client"], data.get("profile", "web"), data.get("command") or None
                )
            elif operation == "/api/demo":
                result = authoring.create(
                    None, data.get("kind", "crate"), data.get("asset_id", "demo_crate")
                )
            elif operation == "/api/style":
                result = authoring.set_style(None, **data)
            elif operation == "/api/create":
                result = authoring.create(None, **data)
            elif operation == "/api/search":
                result = sources.search(**data)
            elif operation == "/api/import":
                result = sources.submit(None, **data)
            elif operation == "/api/prepare":
                result = authoring.optimize(None, **data)
            elif operation == "/api/kit":
                result = kits.create(None, **data)
            elif operation == "/api/review":
                result = reviews.capture(None, **data)
            elif operation == "/api/publish-prepared":
                result = sources.publish(None, **data)
            elif operation == "/api/part":
                result = authoring.edit_part(None, **data)
            elif operation == "/api/revise":
                result = authoring.revise(None, **data)
            elif operation == "/api/variants":
                result = studies.create(None, **data)
            elif operation == "/api/choose":
                result = studies.choose(None, **data)
            elif operation == "/api/arrange":
                import asyncio

                from .server import arrange_props

                result = asyncio.run(arrange_props(**data))
            elif operation == "/api/action":
                result = workflow.action(
                    None,
                    data["operation"],
                    asset_id=data.get("asset_id"),
                    scope=data.get("scope", "selected"),
                    values=data.get("values"),
                    undo_id=data.get("undo_id"),
                )
            elif operation == "/api/task":
                result = workflow.job_status(None, data["request_id"])
            elif operation == "/api/cancel":
                result = workflow.cancel(None, data["request_id"])
            elif operation == "/api/restore":
                result = workflow.restore(None, data["asset_id"])
            elif operation == "/api/close":
                result = {"closed": True}
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.reply({"error": "Not found"}, 404)
                return
            self.reply(result)
        except Exception as error:
            self.reply({"error": str(error)}, 400)


def main():
    from .intake import start_watcher

    start_watcher()
    with Server() as server:
        url = server.origin + "/#" + server.token
        if os.environ.get("PTS_SETUP_URL_FILE"):
            Path(os.environ["PTS_SETUP_URL_FILE"]).write_text(url)
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        server.serve_forever()
