"""Local file transport. Each editor owns its engine assets and scene mutations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .targets import resolve_target

ASSET_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def asset_id(value: str) -> str:
    if not ASSET_ID.fullmatch(value):
        raise ValueError(
            "asset_id must be 1–64 lowercase letters/digits/_/-, starting with a letter"
        )
    return value


def project_path(value: str | Path, engine: str = "auto") -> Path:
    return resolve_target(value, engine).root


def position_values(value: list[float] | None) -> list[float]:
    result = [0.0, 0.0, 0.0] if value is None else value
    if len(result) != 3 or any(not math.isfinite(float(v)) for v in result):
        raise ValueError("position must contain three finite numbers, in engine XYZ meters")
    return [float(v) for v in result]


def blender_path() -> str:
    override = os.environ.get("PTS_BLENDER")
    if override and not Path(override).expanduser().is_file():
        raise ValueError("PTS_BLENDER does not point to a Blender executable")
    from .registry import find_blender

    found = find_blender()
    if found:
        return found
    raise ValueError("Blender is missing. Open Prompt-to-Scene setup and select Blender.")


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def read_optional_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def state_root(project: Path) -> Path:
    root = project / ".prompt-to-scene"
    # Do not follow a project-local symlink out of the chosen project.
    if root.is_symlink() or not root.resolve().is_relative_to(project):
        raise ValueError(".prompt-to-scene must be a directory inside the project")
    return root


def status(project: str | Path, name: str, *, engine: str = "auto") -> dict:
    target = resolve_target(project, engine)
    project = target.root
    name = asset_id(name)
    root = state_root(project)
    request_file = root / "inbox" / f"{name}.json"
    receipt_file = root / "receipts" / f"{name}.json"
    # Editors write the receipt before removing the request. Read in that order's reverse
    # so a request consumed during this call cannot expose a stale success or raise ENOENT.
    request = read_optional_json(request_file)
    receipt = read_optional_json(receipt_file)
    if request:
        if receipt and receipt.get("request_id") == request["request_id"]:
            return receipt
        return {
            "status": "queued",
            "asset_id": name,
            "request_id": request["request_id"],
            "engine": target.engine,
            "message": "Waiting for the editor. Open this project with Prompt-to-Scene installed.",
        }
    return receipt or {"status": "unknown", "asset_id": name}


def wait_for_status(
    project: str | Path,
    name: str,
    request_id: str | None = None,
    wait_seconds: float = 0,
    *,
    engine: str = "auto",
) -> dict:
    if not math.isfinite(wait_seconds) or not 0 <= wait_seconds <= 30:
        raise ValueError("wait_seconds must be between 0 and 30")
    if request_id is not None and not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise ValueError("request_id must be the 32-character ID returned by build_asset")
    if wait_seconds and not request_id:
        raise ValueError("Pass request_id when waiting, so an old receipt cannot confirm success")
    deadline = time.monotonic() + wait_seconds
    while True:
        result = status(project, name, engine=engine)
        latest = result.get("request_id")
        if request_id and latest and latest != request_id:
            return {
                "status": "superseded",
                "asset_id": name,
                "request_id": request_id,
                "latest_request_id": latest,
                "message": "A different revision is current; this is not confirmation of yours.",
            }
        if result["status"] in {"imported", "error"} or not wait_seconds:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {**result, "wait_timed_out": True}
        time.sleep(min(0.25, remaining))


@contextmanager
def blender_slot(root, revision):
    """Share at most two Blender processes per project across clients and candidate batches."""
    from .workflow import process_alive

    slots = root / "blender-slots"
    slots.mkdir(exist_ok=True)
    claimed = None
    deadline = time.monotonic() + 1800
    while claimed is None:
        if (root / "cancel" / revision).exists():
            raise RuntimeError("Cancelled while waiting for Blender")
        for index in range(2):
            slot = slots / str(index)
            cleanup = slots / (str(index) + "-cleanup")
            if cleanup.exists():
                try:
                    # Cleanup only touches two tiny files. Recover an empty lock left by a crash.
                    if time.time() - cleanup.stat().st_mtime > 30:
                        cleanup.rmdir()
                except (FileNotFoundError, OSError):
                    pass
                if cleanup.exists():
                    continue
            try:
                slot.mkdir()
            except FileExistsError:
                try:
                    cleanup.mkdir()
                except FileExistsError:
                    continue
                try:
                    owner = read_optional_json(slot / "owner.json")
                    abandoned = owner and not process_alive(owner["pid"])
                    if not owner and slot.exists():
                        abandoned = time.time() - slot.stat().st_mtime > 30
                    if abandoned:
                        (slot / "owner.json").unlink(missing_ok=True)
                        slot.rmdir()
                except FileNotFoundError:
                    pass
                finally:
                    cleanup.rmdir()
                continue
            atomic_json(slot / "owner.json", {"pid": os.getpid(), "request_id": revision})
            claimed = slot
            break
        if claimed is None:
            if time.monotonic() > deadline:
                raise RuntimeError("Blender queue did not become available; inspect running tasks")
            time.sleep(0.2)
    try:
        yield
    finally:
        (claimed / "owner.json").unlink(missing_ok=True)
        claimed.rmdir()


def build(
    project: str | Path,
    name: str,
    script: str,
    position: list[float] | None = None,
    collider: bool = True,
    *,
    blend_file: str | Path | None = None,
    timeout: int = 180,
    engine: str = "auto",
    request_id: str | None = None,
    recipe: dict | None = None,
    preview_only: bool = False,
) -> dict:
    """Run a trusted AI/user-authored script in a separate Blender process, then queue import."""
    target = resolve_target(project, engine)
    project = target.root
    name = asset_id(name)
    automatic_placement = position is None
    position = position_values(position)
    if not script.strip() and blend_file is None:
        raise ValueError("Provide Blender Python or an existing .blend file")
    blender = blender_path()
    source = None
    if blend_file is not None:
        source = Path(blend_file).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() != ".blend":
            raise ValueError("blend_file must point to an existing .blend file")
    root = state_root(project)
    lock = root / "locks" / name
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError(f"A build of {name} is already running") from exc
    try:
        if (root / "inbox" / f"{name}.json").exists():
            raise ValueError(
                "Previous import is still queued; inspect the editor before rebuilding"
            )
        revision = request_id or uuid.uuid4().hex
        if not re.fullmatch(r"[a-f0-9]{32}", revision):
            raise ValueError("Invalid request ID")
        work = root / "work" / name / revision
        work.mkdir(parents=True)
        (work / "model.py").write_text(script, encoding="utf-8")
        # Retain the exact drivers with the source. A detached packaged worker uses a
        # fresh extraction directory, and the submitting MCP process may already be gone.
        for helper in (
            "blender_export.py",
            "blender_recipe.py",
            "blender_surfaces.py",
            "blender_preview.py",
        ):
            shutil.copy2(Path(__file__).with_name(helper), work / helper)
        driver = work / "blender_export.py"
        command = [
            blender,
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--threads",
            "4",
        ]
        if source:
            command.append(str(source))
        command += ["--python-exit-code", "1", "--python", str(driver), "--", str(work)]
        log_path = work / "blender.log"
        with blender_slot(root, revision):
            with log_path.open("w") as log:
                try:
                    child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                    deadline = time.monotonic() + timeout
                    while child.poll() is None:
                        if (root / "cancel" / revision).exists():
                            child.terminate()
                            try:
                                child.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                child.kill()
                                child.wait()
                            raise RuntimeError("Cancelled before import")
                        if time.monotonic() > deadline:
                            child.kill()
                            child.wait()
                            raise subprocess.TimeoutExpired(command, timeout)
                        time.sleep(0.1)
                    result = child
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(
                        f"Blender timed out after {timeout}s; log: {log_path}"
                    ) from exc
        export_file = work / "export.json"
        if result.returncode != 0 or not export_file.exists():
            tail = log_path.read_text(errors="replace")[-6000:]
            raise RuntimeError(f"Blender export failed. No import was queued.\n{tail}")
        exported = json.loads(export_file.read_text())
        files = []
        for path in sorted(work.glob("*")):
            if path.name == "model.fbx" or path.name.startswith("tex_"):
                files.append(
                    {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                )
        request = {
            "schema_version": 2,
            "target_engine": target.engine,
            "position_unit": "meters",
            "asset_id": name,
            "request_id": revision,
            "work_dir": work.relative_to(root).as_posix(),
            "position": position,
            "auto_place": automatic_placement,
            "collider": collider,
            "materials": exported["materials"],
            "files": files,
        }
        atomic_json(work / "request.json", request)
        atomic_json(
            work / "asset.json",
            {
                "asset_id": name,
                "request_id": revision,
                "recipe": recipe,
                "source_file": str(source) if source else None,
                "collider": collider,
                "report": exported.get("report"),
                "previews": exported.get("previews", []),
            },
        )
        if source and not script.strip():
            original_script = source.with_name("model.py")
            if original_script.is_file():
                shutil.copyfile(original_script, work / "model.py")
        if (root / "cancel" / revision).exists():
            raise RuntimeError("Cancelled before import")
        if not preview_only:
            atomic_json(root / "inbox" / f"{name}.json", request)
        return {
            "status": "completed" if preview_only else "queued",
            "engine": target.engine,
            "asset_id": name,
            "request_id": revision,
            "source_blend": str(work / "source.blend"),
            "triangles": exported["triangles"],
            "report": exported.get("report"),
            "previews": exported.get("previews", []),
            "preview_only": preview_only,
            "message": "Blender finished. Call get_asset_status with request_id to verify import.",
        }
    finally:
        lock.rmdir()


def inspect_project(project: str | Path, *, engine: str = "auto") -> dict:
    from . import __version__
    from .registry import find_blender

    target = resolve_target(project, engine)
    project = target.root
    root = state_root(project)
    root.mkdir(parents=True, exist_ok=True)
    heartbeat = root / "editor.json"
    editor = read_optional_json(heartbeat)
    age = None
    if editor and editor.get("updated_utc"):
        try:
            updated = datetime.fromisoformat(editor["updated_utc"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - updated).total_seconds()
        except (ValueError, TypeError):
            pass
    responding = age is not None and -5 <= age <= 15
    blender = find_blender()
    bridge = project / (
        "Packages/com.prompttoscene.bridge/package.json"
        if target.engine == "unity"
        else "Plugins/PromptToScene/PromptToScene.uplugin"
    )
    diagnostics = []
    if not blender:
        diagnostics.append({"code": "blender_missing", "message": "Select Blender in setup."})
    if not bridge.exists() and not responding:
        diagnostics.append(
            {
                "code": "bridge_unconfirmed",
                "message": "Connect this project in setup to install/update the bridge.",
            }
        )
    if not responding:
        diagnostics.append(
            {
                "code": "editor_offline",
                "message": "Open this project and wait for editor startup/compilation.",
            }
        )
    elif editor.get("playing"):
        diagnostics.append(
            {"code": "editor_playing", "message": "Leave Play mode to process queued work."}
        )
    elif editor.get("bridge_version") != __version__:
        diagnostics.append(
            {
                "code": "bridge_version",
                "message": "Reconnect this project in setup to update the bridge; restart UE.",
            }
        )
    return {
        "project": str(project),
        "project_file": str(target.project_file) if target.project_file else None,
        "engine": target.engine,
        "coordinates": "XYZ meters; Y-up" if target.engine == "unity" else "XYZ meters; Z-up",
        "blender": blender,
        "editor": editor,
        "editor_responding": responding,
        "diagnostics": diagnostics,
        "assets": [
            status(target.project_file or project, name, engine=target.engine)
            for name in sorted(
                {p.stem for folder in ("inbox", "receipts") for p in (root / folder).glob("*.json")}
            )
        ],
        "note": "Check the heartbeat's UTC timestamp; an old one does not mean Unity is open.",
    }
