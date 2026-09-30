"""Shared, local project connections used by every supported AI client."""

from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path

from . import __version__
from .core import atomic_json, read_optional_json, state_root
from .targets import resolve_target


def home() -> Path:
    return Path(os.environ.get("PTS_HOME", Path.home() / ".prompt-to-scene")).expanduser().resolve()


def resources() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources"
    bundled = Path(__file__).with_name("resources")
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parents[2]


def read() -> dict:
    return read_optional_json(home() / "connections.json") or {"projects": [], "active": None}


def find_blender() -> str | None:
    candidates = [os.environ.get("PTS_BLENDER"), read().get("blender"), shutil.which("blender")]
    candidates += ["/Applications/Blender.app/Contents/MacOS/Blender"]
    if sys.platform == "win32":
        for root in [os.environ.get("ProgramFiles", "C:/Program Files")]:
            candidates += map(
                str,
                sorted(Path(root).glob("Blender Foundation/Blender */blender.exe"), reverse=True),
            )
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()), None)


def resolve(value: str | None = None):
    if value:
        return resolve_target(value)
    explicit = os.environ.get("PTS_PROJECT") or os.environ.get("PTS_UNITY_PROJECT")
    if explicit:
        return resolve_target(explicit, os.environ.get("PTS_ENGINE", "auto"))
    state = read()
    if state.get("active"):
        return resolve_target(state["active"])
    raise ValueError("No project connected. Open setup or call connect_project with your project.")


def connect(project: str, blender: str | None = None, install_bridge: bool = True) -> dict:
    target = resolve_target(project)
    root = state_root(target.root)
    if blender and not Path(blender).expanduser().is_file():
        raise ValueError("Choose Blender's executable, not its containing folder")
    state = read()
    value = str(target.project_file or target.root)
    state["active"] = value
    state["projects"] = [p for p in state["projects"] if p["path"] != value]
    state["projects"].append({"path": value, "engine": target.engine, "name": target.root.name})
    if blender:
        state["blender"] = str(Path(blender).expanduser().resolve())
    elif find_blender():
        state["blender"] = find_blender()
    bridge = install(target) if install_bridge else {"installed": False}
    atomic_json(home() / "connections.json", state)
    ignore = target.root / ".gitignore"
    contents = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    if not any(
        line.strip().rstrip("/") in {".prompt-to-scene", "/.prompt-to-scene"}
        for line in contents.splitlines()
    ):
        ignore.write_text(
            contents
            + ("\n" if contents and not contents.endswith("\n") else "")
            + "\n# Prompt-to-Scene local jobs and source history\n.prompt-to-scene/\n",
            encoding="utf-8",
        )
    # Create the inbox before editor startup, so its heartbeat starts immediately.
    (root / "inbox").mkdir(parents=True, exist_ok=True)
    return {"project": value, "engine": target.engine, "blender": state.get("blender"), **bridge}


def install(target) -> dict:
    state_root(target.root)
    if target.engine == "unity":
        source = resources() / "unity/Packages/com.prompttoscene.bridge"
        destination = target.root / "Packages/com.prompttoscene.bridge"
    else:
        source = resources() / "unreal/PromptToScene"
        destination = target.root / "Plugins/PromptToScene"
    if not source.is_dir():
        raise ValueError(
            "Bridge files are missing from this installation; reinstall Prompt-to-Scene"
        )
    if destination.is_symlink() or not destination.resolve().is_relative_to(target.root):
        raise ValueError("The bridge destination is a symlink; choose a regular project directory")
    backup = None
    if destination.exists():
        backup = target.root / ".prompt-to-scene/bridge-backups" / uuid.uuid4().hex
        shutil.copytree(destination, backup)
    temporary = destination.with_name(destination.name + ".pts-staging")
    if temporary.exists():
        shutil.rmtree(temporary)
    shutil.copytree(source, temporary, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if destination.exists():
        shutil.rmtree(destination)
    temporary.rename(destination)
    if target.engine == "unreal":
        descriptor = json.loads(target.project_file.read_text(encoding="utf-8-sig"))
        plugins = descriptor.setdefault("Plugins", [])
        for name in ("PromptToScene", "PythonScriptPlugin", "EditorScriptingUtilities"):
            row = next((p for p in plugins if p.get("Name") == name), None)
            if row is None:
                plugins.append({"Name": name, "Enabled": True})
            else:
                row["Enabled"] = True
        backup_file = (
            target.root / ".prompt-to-scene/bridge-backups" / (uuid.uuid4().hex + ".uproject")
        )
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target.project_file, backup_file)
        atomic_json(target.project_file, descriptor)
    return {
        "installed": True,
        "bridge_version": __version__,
        "restart_editor": target.engine == "unreal",
        "message": "Restart Unreal once."
        if target.engine == "unreal"
        else "Wait for Unity to finish compiling.",
        "backup": str(backup) if backup else None,
    }


def discover() -> list[dict]:
    """Only inspect known connections and immediate project folders, never crawl a drive."""
    result = {p["path"]: p for p in read()["projects"] if Path(p["path"]).exists()}
    roots = [Path.cwd(), Path.home() / "Documents/Unreal Projects", Path.home() / "Unity Projects"]
    for root in roots:
        candidates = [root]
        if root.is_dir():
            candidates += [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")][
                :100
            ]
        for path in candidates:
            try:
                target = resolve_target(path)
                value = str(target.project_file or target.root)
                result[value] = {"path": value, "name": target.root.name, "engine": target.engine}
            except (ValueError, OSError):
                pass
    return list(result.values())
