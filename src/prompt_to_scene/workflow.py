"""Persistent jobs and editor actions. No long Blender process occupies an MCP call."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import core, registry

TERMINAL = {"imported", "completed", "error", "cancelled", "superseded"}


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid request ID")
    return value


def launch_command(*arguments):
    if getattr(sys, "frozen", False):
        return [sys.executable, *arguments]
    return [sys.executable, "-m", "prompt_to_scene.app", *arguments]


def launch_worker(spec: Path):
    with spec.with_name("worker.log").open("w") as log:
        return subprocess.Popen(
            launch_command("--worker", str(spec)),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
            start_new_session=sys.platform != "win32",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )


def submit(
    project,
    name,
    script,
    position=None,
    collider=True,
    blend_file=None,
    recipe=None,
    preview_only=False,
    source=None,
    preparation=None,
    provenance=None,
):
    target = registry.resolve(project)
    name = core.asset_id(name)
    core.position_values(position)
    core.blender_path()  # fail immediately with an actionable setup error
    if not script.strip() and not blend_file and not source:
        raise ValueError("Provide a model script or a saved .blend file")
    root = core.state_root(target.root)
    gate = root / "submission-locks" / name
    gate.parent.mkdir(parents=True, exist_ok=True)
    try:
        gate.mkdir()
    except FileExistsError as exc:
        raise ValueError("Another client is submitting this asset; retry shortly") from exc
    try:
        last = core.read_optional_json(root / "latest" / (name + ".json"))
        if (
            last
            and job_status(str(target.project_file or target.root), last["request_id"])["status"]
            not in TERMINAL
        ):
            raise ValueError("This asset already has a running task. Wait or cancel it first.")
        if (root / "inbox" / (name + ".json")).exists():
            raise ValueError("An import is pending in the editor. Wait or cancel it first.")
        revision = uuid.uuid4().hex
        folder = root / "jobs" / revision
        spec = {
            "project": str(target.project_file or target.root),
            "asset_id": name,
            "request_id": revision,
            "script": script,
            "position": position,
            "collider": collider,
            "blend_file": blend_file,
            "recipe": recipe,
            "preview_only": preview_only,
            "source": source,
            "preparation": preparation,
            "provenance": provenance,
        }
        state = {
            "request_id": revision,
            "asset_id": name,
            "engine": target.engine,
            "status": "building",
            "stage": "Starting Blender",
            "created_utc": now(),
        }
        core.atomic_json(folder / "spec.json", spec)
        core.atomic_json(folder / "state.json", state)
        core.atomic_json(root / "latest" / (name + ".json"), state)
        try:
            child = launch_worker(folder / "spec.json")
            core.atomic_json(folder / "process.json", {"pid": child.pid})
        except OSError as error:
            state.update(status="error", error=str(error), completed_utc=now())
            core.atomic_json(folder / "state.json", state)
            raise
        return {
            **state,
            "message": "Task started. Wait with get_asset_status using this request_id.",
        }
    finally:
        gate.rmdir()


def worker(spec_path):
    path = Path(spec_path).resolve()
    spec = json.loads(path.read_text())
    target = registry.resolve(spec["project"])
    revision = identifier(spec["request_id"])
    root = core.state_root(target.root)
    if path != root / "jobs" / revision / "spec.json":
        raise ValueError("Worker spec must be inside this project's job directory")
    if spec.get("kind"):
        from . import background

        return background.run(path)
    state = core.read_optional_json(path.with_name("state.json"))
    try:
        if (root / "cancel" / revision).exists():
            raise RuntimeError("Cancelled before Blender started")
        provenance = spec.get("provenance")
        if spec.get("source"):
            from . import sources

            state["stage"] = "Preparing source asset"
            core.atomic_json(path.with_name("state.json"), state)
            model, source_provenance = sources.resolve(
                spec["source"], path.parent / "inputs", root / "cancel" / revision
            )
            provenance = provenance or source_provenance
            spec["script"] = sources.script(model)
        previous = core.read_optional_json(root / "receipts" / (spec["asset_id"] + ".json"))
        if previous and previous.get("status") == "imported":
            core.atomic_json(
                root
                / "history"
                / spec["asset_id"]
                / (identifier(previous["request_id"]) + ".json"),
                previous,
            )
        result = core.build(
            spec["project"],
            spec["asset_id"],
            spec["script"],
            spec["position"],
            spec["collider"],
            blend_file=spec["blend_file"],
            request_id=revision,
            recipe=spec["recipe"],
            preview_only=spec.get("preview_only", False),
            timeout=600,
            preparation=spec.get("preparation"),
            provenance=provenance,
        )
        state.update(
            result,
            stage="Draft ready" if spec.get("preview_only") else "Waiting for the editor to import",
        )
    except Exception as error:
        cancelled = (root / "cancel" / revision).exists()
        state.update(
            status="cancelled" if cancelled else "error",
            error=str(error),
            stage="Cancelled" if cancelled else "Build needs attention",
            recovery=(
                "Check the script error; at most two automatic repairs. "
                "An offline editor only needs to be opened."
            ),
            completed_utc=now(),
            report=core.read_optional_json(
                root / "work" / spec["asset_id"] / revision / "preparation.json"
            ),
        )
    core.atomic_json(path.with_name("state.json"), state)


def job_status(project, revision, wait_seconds=0):
    identifier(revision)
    if not math.isfinite(wait_seconds) or not 0 <= wait_seconds <= 30:
        raise ValueError("wait_seconds must be between 0 and 30")
    target = registry.resolve(project)
    root = core.state_root(target.root)
    deadline = time.monotonic() + wait_seconds
    while True:
        state = core.read_optional_json(root / "jobs" / revision / "state.json")
        if state and state.get("kind"):
            if state["status"] == "building":
                process = core.read_optional_json(root / "jobs" / revision / "process.json")
                if process and not process_alive(process["pid"]):
                    state.update(status="error", error="Worker stopped; resume the saved workflow")
        elif state:
            receipt = core.read_optional_json(
                root / "history" / state["asset_id"] / (revision + ".json")
            )
            current = core.read_optional_json(root / "receipts" / (state["asset_id"] + ".json"))
            if current and current.get("request_id") == revision:
                receipt = current
            if receipt:
                state = {**state, **receipt}
            elif state["status"] == "building":
                process = core.read_optional_json(root / "jobs" / revision / "process.json")
                if process and not process_alive(process["pid"]):
                    state.update(
                        status="error",
                        error="The worker stopped before publishing its result. Retry this asset.",
                    )
        else:
            state = core.read_optional_json(root / "action-receipts" / (revision + ".json"))
            if not state:
                pending = core.read_optional_json(root / "actions" / (revision + ".json"))
                state = {"request_id": revision, "status": "queued" if pending else "unknown"}
        if state["status"] in TERMINAL or not wait_seconds:
            return state
        if time.monotonic() >= deadline:
            return {
                **state,
                "wait_timed_out": True,
                "message": (
                    "Still running. Open the target editor and leave Play mode "
                    "if waiting for import."
                ),
            }
        time.sleep(0.15)


def process_alive(pid):
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied is not proof of exit.
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def cancel(project, revision):
    target = registry.resolve(project)
    identifier(revision)
    state = job_status(project, revision)
    if state["status"] in TERMINAL or state["status"] == "unknown":
        return state
    root = core.state_root(target.root)
    marker = root / "cancel" / revision
    marker.parent.mkdir(exist_ok=True)
    marker.touch()
    return {
        "status": "cancel_requested",
        "request_id": revision,
        "message": (
            "Blender can be stopped; a native import already in progress may finish. "
            "Check this request's result."
        ),
    }


def action(project, operation, *, asset_id=None, scope="selected", values=None, undo_id=None):
    if operation not in {
        "inspect",
        "transform",
        "tint",
        "focus",
        "preview",
        "undo",
        "arrange",
        "analyze",
        "ground",
        "select",
    }:
        raise ValueError("Unknown editor action")
    if scope not in {"selected", "asset"}:
        raise ValueError("scope must be selected or asset")
    if asset_id:
        core.asset_id(asset_id)
    if scope == "asset" and not asset_id:
        raise ValueError("An asset ID is required to edit every loaded instance")
    values = values or {}
    if values.keys() - {
        "move",
        "rotate",
        "scale",
        "color",
        "material",
        "scene",
        "anchor",
        "placements",
        "view",
        "frame_id",
        "review_stage",
        "object_id",
        "snap_to_surface",
    }:
        raise ValueError("Unknown edit field")
    if "view" in values and values["view"] not in {"studio", "front", "back"}:
        raise ValueError("Unknown preview view")
    if values.get("frame_id"):
        identifier(values["frame_id"])
        if values.get("review_stage") not in {"before", "after"}:
            raise ValueError("Unknown comparison stage")
    for key in ("move", "rotate", "scale", "color"):
        if key in values:
            vector = core.position_values(values[key])
            if key == "scale" and any(v <= 0 or v > 100 for v in vector):
                raise ValueError("Scale factors must be positive and at most 100")
            if key == "color" and any(not 0 <= v <= 1 for v in vector):
                raise ValueError("Color must be three linear RGB values between 0 and 1")
    if operation == "tint" and "color" not in values:
        raise ValueError("Tint needs a color")
    if operation == "transform" and not ({"move", "rotate", "scale"} & values.keys()):
        raise ValueError("Provide a move, rotate or scale change")
    if operation == "undo":
        identifier(undo_id)
    target = registry.resolve(project)
    root = core.state_root(target.root)
    revision = uuid.uuid4().hex
    (root / "inbox").mkdir(parents=True, exist_ok=True)
    request = {
        "schema_version": 1,
        "request_id": revision,
        "operation": operation,
        "target_engine": target.engine,
        "scope": scope,
        "asset_id": asset_id or "",
        "undo_id": undo_id or "",
        **values,
    }
    core.atomic_json(root / "actions" / (revision + ".json"), request)
    return {"status": "queued", "request_id": revision, "operation": operation}


def inspect_asset(project, name):
    target = registry.resolve(project)
    root = core.state_root(target.root)
    core.asset_id(name)
    current = core.status(target.project_file or target.root, name)
    revision = current.get("request_id")
    history = []
    for path in sorted((root / "history" / name).glob("*.json")):
        row = core.read_optional_json(path)
        if row and row.get("status") == "imported":
            history.append(row)
    if current.get("status") == "imported" and not any(
        h["request_id"] == revision for h in history
    ):
        history.append(current)
    history.sort(key=lambda r: r.get("completed_utc", ""))
    work = root / "work" / name / identifier(revision) if revision else None
    metadata = core.read_optional_json(work / "asset.json") if work else None
    script = (work / "model.py").read_text() if work and (work / "model.py").exists() else None
    return {
        "asset_id": name,
        "current": current,
        "metadata": metadata,
        "report": core.read_optional_json(work / "report.json") if work else None,
        "script": script,
        "history": history,
        "source_blend": str(work / "source.blend") if work else None,
    }


def restore(project, name, revision=None):
    target = registry.resolve(project)
    info = inspect_asset(project, name)
    current = info["current"]
    if current.get("status") != "imported":
        raise ValueError("Finish or repair the current import before restoring a revision")
    candidates = [h for h in info["history"] if h["request_id"] != current["request_id"]]
    if revision:
        identifier(revision)
        candidates = [h for h in candidates if h["request_id"] == revision]
    if not candidates:
        raise ValueError("No earlier successful revision exists for this asset")
    root = core.state_root(target.root)
    old = root / "work" / name / candidates[-1]["request_id"]
    metadata = core.read_optional_json(old / "asset.json") or {}
    request = core.read_optional_json(old / "request.json") or {}
    if not (old / "source.blend").is_file():
        raise ValueError("The source of this revision is missing")
    # Reimport the immutable saved source with its original recipe metadata.
    return submit(
        str(target.project_file or target.root),
        name,
        "",
        blend_file=str(old / "source.blend"),
        collider=request.get("collider", True),
        recipe=metadata.get("recipe"),
        provenance=metadata.get("provenance"),
    )
