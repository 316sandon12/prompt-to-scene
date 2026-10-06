"""Versioned project conventions shared by hosts, intake and native editor panels."""

import re
from collections import Counter
from pathlib import PurePosixPath

from . import core, organization, preparation, registry

FILE = "prompt-to-scene.json"


def defaults(project):
    engine = registry.resolve(project).engine
    return {
        "schema_version": 1,
        "name": "Project defaults",
        "organization": {
            "destination": "Assets/GameAssets" if engine == "unity" else "/Game/GameAssets",
            "rename": True,
            "group_by": "type",
            "exclude": [],
            "rules": {},
        },
        "preparation": preparation.options(),
        "intake": {"folder": "AssetInbox", "enabled": False, "settle_seconds": 5},
    }


def validate(project, values):
    if not isinstance(values, dict) or values.keys() - defaults(project).keys():
        raise ValueError("Unknown project convention field")
    result = defaults(project)
    result.update(values)
    if result["schema_version"] != 1:
        raise ValueError("Unsupported project convention version")
    if not isinstance(result["name"], str) or not 1 <= len(result["name"]) <= 80:
        raise ValueError("Use a short profile name")
    org = result["organization"]
    if not isinstance(org, dict) or org.keys() - defaults(project)["organization"].keys():
        raise ValueError("Unknown naming or folder convention")
    engine = registry.resolve(project).engine
    organization.make_plan(
        {"scan_id": "validation", "engine": engine, "entries": [], "scope": "", "occupied": []}, org
    )
    result["organization"] = {**defaults(project)["organization"], **org}
    result["preparation"] = preparation.options(result["preparation"])
    intake = result["intake"]
    if not isinstance(intake, dict) or intake.keys() - {"folder", "enabled", "settle_seconds"}:
        raise ValueError("Unknown intake setting")
    intake = {**defaults(project)["intake"], **intake}
    folder = intake["folder"]
    if (
        not isinstance(folder, str)
        or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_/ -]{0,100}", folder)
        or any(p in {"", ".", ".."} for p in folder.split("/"))
        or folder.split("/")[0].lower() in {"assets", "content", "plugins", "packages", "library"}
    ):
        raise ValueError("Choose a project-relative source inbox outside engine asset folders")
    if type(intake["enabled"]) is not bool or type(intake["settle_seconds"]) is not int:
        raise ValueError("enabled is boolean and settle_seconds is an integer")
    if not 2 <= intake["settle_seconds"] <= 120:
        raise ValueError("Wait 2–120 seconds for copied files to settle")
    result["intake"] = intake
    return result


def read(project):
    path = registry.resolve(project).root / FILE
    if path.is_file() and path.stat().st_size > 64 * 1024:
        raise ValueError("Project convention file is too large")
    return validate(project, core.read_optional_json(path) or {})


def configure(project, mode="read", settings=None, scan_id=None):
    if mode == "read":
        return read(project)
    if mode == "suggest":
        target = registry.resolve(project)
        scan = organization.read_record(core.state_root(target.root), "scans", scan_id)
        if scan["engine"] != target.engine or scan.get("truncated"):
            raise ValueError("Use a complete scan from this project")
        suggestions = {}
        for kind in organization.RULES:
            entries = [e for e in scan["entries"] if e["kind"] == kind and not e.get("reason")]
            prefixes = Counter()
            for entry in entries:
                match = re.match(r"([A-Za-z][A-Za-z0-9]{0,12}_)\w", entry["name"])
                if match:
                    prefixes[match[1]] += 1
            if prefixes:
                prefix, count = prefixes.most_common(1)[0]
                suggestions[kind] = {
                    "prefix": prefix,
                    "count": count,
                    "total": len(entries),
                    "confidence": round(count / len(entries), 3),
                }
        parents = Counter(str(PurePosixPath(e["path"]).parent) for e in scan["entries"])
        return {
            "suggestions": suggestions,
            "common_folders": parents.most_common(12),
            "message": "Suggestions only; save chosen rules to adopt them.",
        }
    if mode != "save" or not isinstance(settings, dict):
        raise ValueError("Choose read, save with settings, or suggest with scan_id")
    current = read(project)
    for key, value in settings.items():
        current[key] = (
            {**current[key], **value} if isinstance(value, dict) and key in current else value
        )
    current = validate(project, current)
    core.atomic_json(registry.resolve(project).root / FILE, current)
    return current


def preparation_defaults(project, explicit=None):
    """Explicit job options override saved conventions; old projects keep their defaults."""
    if not (registry.resolve(project).root / FILE).is_file():
        return explicit
    return {**read(project)["preparation"], **(explicit or {})}
