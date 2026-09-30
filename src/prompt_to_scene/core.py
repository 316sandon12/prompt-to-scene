"""Local file-based transport. Unity owns all writes to its AssetDatabase."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ASSET_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def asset_id(value: str) -> str:
    if not ASSET_ID.fullmatch(value):
        raise ValueError(
            "asset_id must be 1–64 lowercase letters/digits/_/-, starting with a letter"
        )
    return value


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not (path / "Assets").is_dir() or not (path / "ProjectSettings").is_dir():
        raise ValueError(f"Not a Unity project (Assets and ProjectSettings required): {path}")
    return path


def position_values(value: list[float] | None) -> list[float]:
    result = [0.0, 0.0, 0.0] if value is None else value
    if len(result) != 3 or any(not math.isfinite(float(v)) for v in result):
        raise ValueError("position must contain three finite numbers, in Unity meters")
    return [float(v) for v in result]


def blender_path() -> str:
    override = os.environ.get("PTS_BLENDER")
    candidates = [override] if override else [shutil.which("blender")]
    if not override and sys.platform == "darwin":
        candidates.append("/Applications/Blender.app/Contents/MacOS/Blender")
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise ValueError("Blender executable not found. Set PTS_BLENDER to its full path.")


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


def status(project: str | Path, name: str) -> dict:
    project = project_path(project)
    name = asset_id(name)
    root = state_root(project)
    request_file = root / "inbox" / f"{name}.json"
    receipt_file = root / "receipts" / f"{name}.json"
    # Unity writes the receipt before removing the request. Read in that order's reverse
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
            "message": "Waiting for Unity. Open the project with Prompt-to-Scene installed.",
        }
    return receipt or {"status": "unknown", "asset_id": name}


def build(
    project: str | Path,
    name: str,
    script: str,
    position: list[float] | None = None,
    collider: bool = True,
    *,
    blend_file: str | Path | None = None,
    timeout: int = 180,
) -> dict:
    """Run a trusted AI/user-authored script in a separate Blender process, then queue import."""
    project = project_path(project)
    name = asset_id(name)
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
            raise ValueError("Previous import is still queued; inspect Unity before rebuilding")
        revision = uuid.uuid4().hex
        work = root / "work" / name / revision
        work.mkdir(parents=True)
        (work / "model.py").write_text(script, encoding="utf-8")
        driver = Path(__file__).with_name("blender_export.py")
        command = [blender, "--background", "--factory-startup", "--disable-autoexec"]
        if source:
            command.append(str(source))
        command += ["--python-exit-code", "1", "--python", str(driver), "--", str(work)]
        log_path = work / "blender.log"
        with log_path.open("w") as log:
            try:
                result = subprocess.run(
                    command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"Blender timed out after {timeout}s; log: {log_path}") from exc
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
            "schema_version": 1,
            "asset_id": name,
            "request_id": revision,
            "work_dir": work.relative_to(root).as_posix(),
            "position": position,
            "collider": collider,
            "materials": exported["materials"],
            "files": files,
        }
        atomic_json(root / "inbox" / f"{name}.json", request)
        return {
            "status": "queued",
            "asset_id": name,
            "request_id": revision,
            "source_blend": str(work / "source.blend"),
            "triangles": exported["triangles"],
            "message": "Blender finished. Call get_asset_status to verify the Unity import.",
        }
    finally:
        lock.rmdir()


def inspect_project(project: str | Path) -> dict:
    project = project_path(project)
    root = state_root(project)
    root.mkdir(parents=True, exist_ok=True)
    heartbeat = root / "editor.json"
    return {
        "project": str(project),
        "blender": blender_path(),
        "editor": read_optional_json(heartbeat),
        "assets": [
            status(project, name)
            for name in sorted(
                {p.stem for folder in ("inbox", "receipts") for p in (root / folder).glob("*.json")}
            )
        ],
        "note": "Check the heartbeat's UTC timestamp; an old one does not mean Unity is open.",
    }
