"""Resolve one explicitly configured local engine project without guessing between projects."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Target:
    root: Path
    engine: str
    project_file: Path | None = None


def resolve_target(value: str | Path, engine: str = "auto") -> Target:
    if engine not in {"auto", "unity", "unreal"}:
        raise ValueError("engine must be auto, unity or unreal")
    path = Path(value).expanduser().resolve()
    explicit_file = path.is_file() and path.suffix.lower() == ".uproject"
    root = path.parent if explicit_file else path
    unity = (root / "Assets").is_dir() and (root / "ProjectSettings").is_dir()
    projects = [path] if explicit_file else sorted(root.glob("*.uproject"))
    if engine == "auto":
        if explicit_file:
            engine = "unreal"
        elif unity and projects:
            raise ValueError("Ambiguous project: choose --engine / PTS_ENGINE explicitly")
        elif unity:
            engine = "unity"
        elif projects:
            engine = "unreal"
        else:
            raise ValueError("Not a Unity project or Unreal .uproject: " + str(path))
    if engine == "unity":
        if explicit_file or not unity:
            raise ValueError("Unity requires a directory with Assets and ProjectSettings")
        return Target(root, "unity")
    if len(projects) != 1:
        raise ValueError("Specify one existing .uproject file (directory has zero or multiple)")
    try:
        descriptor = json.loads(projects[0].read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError("Cannot read the .uproject JSON") from exc
    if not isinstance(descriptor, dict) or descriptor.get("FileVersion") != 3:
        raise ValueError("Expected an Unreal .uproject with FileVersion 3")
    return Target(root, "unreal", projects[0])


def configured_target() -> Target:
    value = os.environ.get("PTS_PROJECT") or os.environ.get("PTS_UNITY_PROJECT")
    if not value:
        raise ValueError("Set PTS_PROJECT to a Unity directory or an Unreal .uproject file")
    return resolve_target(value, os.environ.get("PTS_ENGINE", "auto").lower())
