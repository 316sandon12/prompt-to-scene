"""Unreal editor-only queue consumer. No sockets or third-party Python packages."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import unreal

from .importer import import_asset, is_commandlet, is_playing
from .protocol import state_root, validate, write_json

_handle = None
_busy = False
_next_tick = 0
_last_error = None


def project_root():
    return Path(unreal.Paths.project_dir()).resolve()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def import_pending():
    """Import pending assets on the editor thread; also usable by commandlet tests."""
    global _busy
    if _busy or is_playing():
        return
    root = state_root(project_root())
    _busy = True
    try:
        for path in sorted((root / "inbox").glob("*.json")):
            receipt = {"status": "error", "engine": "unreal", "asset_id": path.stem}
            try:
                if path.is_symlink() or path.stat().st_size > 1024 * 1024:
                    raise ValueError("Request is too large or a symlink")
                request = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(request, dict):
                    receipt["request_id"] = request.get("request_id")
                source = validate(request, path.stem, root)
                receipt = import_asset(request, source)
                unreal.log("[Prompt-to-Scene] Imported " + path.stem)
            except Exception as error:
                receipt["error"] = str(error)
                unreal.log_warning("[Prompt-to-Scene] " + path.stem + ": " + str(error))
            receipt["completed_utc"] = utc_now()
            write_json(root / "receipts" / path.name, receipt)
            path.unlink()
    finally:
        _busy = False


def tick(_delta):
    global _next_tick, _last_error
    if _busy or time.monotonic() < _next_tick:
        return
    _next_tick = time.monotonic() + 2
    try:
        root = state_root(project_root())
        if not root.is_dir():
            return
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        level = levels.get_current_level()
        playing = is_playing()
        write_json(
            root / "editor.json",
            {
                "engine": "unreal",
                "unreal_version": unreal.SystemLibrary.get_engine_version(),
                "scene": level.get_outer().get_path_name() if level else None,
                "playing": playing,
                "updated_utc": utc_now(),
            },
        )
        if level and not playing:
            import_pending()
        _last_error = None
    except Exception as error:
        if str(error) != _last_error:
            unreal.log_warning("[Prompt-to-Scene] Polling failed: " + str(error))
            _last_error = str(error)


def start():
    global _handle
    # Commandlets have no Slate loop; tests invoke import_pending explicitly.
    if (
        is_commandlet()
        or "-prompttoscenenowatch" in unreal.SystemLibrary.get_command_line().lower()
    ):
        return
    if _handle is None:
        _handle = unreal.register_slate_post_tick_callback(tick)
        unreal.log("[Prompt-to-Scene] Watching the local project inbox")


def stop():
    global _handle
    if _handle is not None:
        unreal.unregister_slate_post_tick_callback(_handle)
        _handle = None
