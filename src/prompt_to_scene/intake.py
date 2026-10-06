"""Settled source inbox -> retained Blender preparation -> native import, once per revision."""

import hashlib
import json
import re
import threading
import time
from pathlib import Path

from . import background, core, organization, project_profiles, registry, sources, workflow


def inbox(project):
    target = registry.resolve(project)
    path = target.root / project_profiles.read(project)["intake"]["folder"]
    if path.is_symlink() or not path.resolve().is_relative_to(target.root):
        raise ValueError("Source inbox must stay inside this project")
    return path


def fingerprint(path, base):
    """Track dependencies too: FBX/Blend relative textures and glTF external buffers."""
    files = [path]
    if path.suffix.lower() == ".gltf":
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("images", []) + data.get("buffers", []):
            uri = row.get("uri", "")
            if uri.startswith("data:") or not uri:
                continue
            from urllib.parse import unquote

            relative = sources.safe_relative(unquote(uri))
            files.append(path.parent / relative)
    elif path.suffix.lower() in {".fbx", ".blend"}:
        files += [
            p
            for p in path.parent.rglob("*")
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tga", ".exr"}
        ]
    if len(files) > 200:
        raise ValueError("Too many dependencies; put each model in its own source folder")
    digest = hashlib.sha256()
    total, modified = 0, 0
    for file in sorted(set(files)):
        if (
            file.is_symlink()
            or not file.resolve().is_relative_to(base.resolve())
            or not file.is_file()
        ):
            raise ValueError("Missing or external dependency: " + file.name)
        info = file.stat()
        total += info.st_size
        if info.st_size > sources.MAX_FILE or total > 512 * 1024**2:
            raise ValueError("Source package is too large")
        modified = max(modified, info.st_mtime)
        digest.update(file.relative_to(base).as_posix().encode())
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if file.stat().st_mtime_ns != info.st_mtime_ns or file.stat().st_size != info.st_size:
            raise ValueError("Source is still being copied")
    return digest.hexdigest(), modified


def manage(project, mode="status", paths=None):
    target = registry.resolve(project)
    root = core.state_root(target.root)
    record = root / "intake.json"
    if mode == "status":
        rows = core.read_optional_json(record) or {}
        for row in rows.values():
            if row.get("request_id"):
                row["task"] = workflow.job_status(project, row["request_id"])
        return {
            "folder": str(inbox(project)),
            "enabled": project_profiles.read(project)["intake"]["enabled"],
            "entries": rows,
        }
    if mode not in {"scan", "retry"}:
        raise ValueError("Choose status, scan or retry")
    base = inbox(project)
    base.mkdir(parents=True, exist_ok=True)
    if paths is not None and (not isinstance(paths, list) or len(paths) > 100):
        raise ValueError("Use at most 100 inbox-relative paths")
    candidates = (
        [base / sources.safe_relative(p) for p in paths] if paths else sorted(base.rglob("*"))
    )
    candidates = [p for p in candidates if p.suffix.lower() in sources.FORMATS]
    if len(candidates) > 200:
        raise ValueError("At most 200 models per inbox; move completed sources to an archive")
    settings = project_profiles.read(project)
    tasks, skipped, errors = [], [], []
    with organization.annotation_lock(root):
        rows = core.read_optional_json(record) or {}
        for path in candidates:
            key = path.relative_to(base).as_posix()
            try:
                digest, modified = fingerprint(path, base)
                previous = rows.get(key, {})
                task = (
                    workflow.job_status(project, previous["request_id"])
                    if previous.get("request_id")
                    else {}
                )
                if task.get("status") in {"building", "queued"}:
                    skipped.append({"path": key, "reason": "already running"})
                    continue
                if time.time() - modified < settings["intake"]["settle_seconds"]:
                    skipped.append({"path": key, "reason": "waiting for file copy"})
                    continue
                if digest == previous.get("fingerprint") and not (
                    mode == "retry" and task.get("status") in {"error", "cancelled"}
                ):
                    skipped.append(
                        {
                            "path": key,
                            "reason": "revision already registered; retry failed jobs explicitly",
                        }
                    )
                    continue
                stem = re.sub("[^a-z0-9]+", "_", path.stem.lower()).strip("_")[:40] or "asset"
                if not stem[0].isalpha():
                    stem = "asset_" + stem
                asset_id = (
                    previous.get("asset_id")
                    or stem + "_" + hashlib.sha256(key.encode()).hexdigest()[:8]
                )
                task = background.submit(
                    project,
                    "intake",
                    {
                        "path": str(path),
                        "fingerprint": digest,
                        "asset_id": asset_id,
                        "settings": settings,
                    },
                    asset_id,
                )
                rows[key] = {
                    "path": key,
                    "fingerprint": digest,
                    "asset_id": asset_id,
                    "request_id": task["request_id"],
                }
                core.atomic_json(record, rows)
                tasks.append(task)
            except (ValueError, OSError, json.JSONDecodeError) as error:
                errors.append({"path": key, "error": str(error)})
    return {"tasks": tasks, "skipped": skipped, "errors": errors}


def run(job, path, fingerprint, asset_id, settings):
    path = Path(path)
    actual, _ = globals()["fingerprint"](path, inbox(job.project))
    if actual != fingerprint:
        raise ValueError("Source changed before intake started; rescan it")
    # Child request is retained before waiting, so resuming never submits a duplicate revision.
    child = job.state.get("import_task")
    if not child:
        job.update(stage="Preparing geometry, PBR materials, LODs and collision")
        child = sources.submit(
            job.project,
            asset_id,
            {"provider": "local", "path": str(path)},
            settings=settings["preparation"],
        )
        job.update(import_task=child)
    if workflow.job_status(job.project, child["request_id"])["status"] in {"error", "cancelled"}:
        raise ValueError("Import failed; use intake retry to prepare a fresh revision")
    result = job.wait(child)
    job.update(stage="Native asset ready; source and import receipt retained")
    return {
        "asset_id": asset_id,
        "import_result": result,
        "profile": settings["name"],
        "source": str(path),
        "fingerprint": fingerprint,
    }


def start_watcher(project=None):
    stop = threading.Event()

    def loop():
        while not stop.wait(5):
            try:
                if project_profiles.read(project)["intake"]["enabled"]:
                    manage(project, "scan")
            except (ValueError, OSError):
                pass  # Status/scan exposes errors; changing/disconnecting projects is harmless.

    threading.Thread(target=loop, name="pts-intake", daemon=True).start()
    return stop
