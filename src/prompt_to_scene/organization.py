"""Previewable, reference-preserving native asset organization with a persistent journal."""

import hashlib
import json
import os
import re
import unicodedata
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import PurePosixPath

from . import core, development, registry, workflow

RULES = {
    "model": ("Models", "SM_"),
    "skeletal_mesh": ("Characters", "SK_"),
    "prefab": ("Prefabs", "PF_"),
    "blueprint": ("Blueprints", "BP_"),
    "material": ("Materials", "M_"),
    "material_instance": ("Materials", "MI_"),
    "texture": ("Textures", "T_"),
    "sprite": ("Sprites", "SPR_"),
    "audio": ("Audio", "S_"),
    "animation": ("Animations", "A_"),
    "controller": ("Animations", "AC_"),
    "vfx": ("VFX", "VFX_"),
    "font": ("Fonts", "F_"),
}
PROTECTED = {
    "resources",
    "streamingassets",
    "editor",
    "editor default resources",
    "gizmos",
    "plugins",
    "standard assets",
    "prompttoscene",
    "__externalactors__",
    "__externalobjects__",
    "developers",
    "collections",
    "addressableassetsdata",
}
TEXTURE_ROLES = {
    "BaseColor": "basecolor|base_color|albedo|diffuse|diff|color|colour|bc|d",
    "Normal": "normal|normalgl|normaldx|normal_map|nrm|nor|n",
    "Roughness": "roughness|rough|r",
    "Metallic": "metallic|metalness|metal|m",
    "AO": "ambient_occlusion|occlusion|ao",
    "Emission": "emissive|emission|emit|e",
    "Height": "displacement|height|disp|h",
    "ORM": "orm|arm|rma|mask|masks",
}


def root_for(project):
    return core.state_root(registry.resolve(project).root)


def path_check(path, engine, folder=False):
    base = "Assets" if engine == "unity" else "/Game"
    if not isinstance(path, str) or len(path) > 240 or "\\" in path or "//" in path:
        raise ValueError("Use a project path inside " + base)
    if path != base and not path.startswith(base + "/"):
        raise ValueError("Use a project path inside " + base)
    parts = path.split("/")[1:] if engine == "unreal" else path.split("/")
    if any(p in {"", ".", ".."} or p.endswith((" ", ".")) for p in parts):
        raise ValueError("Invalid project path")
    if any(ord(c) < 32 or c in ':*?"<>|' for c in path):
        raise ValueError("Invalid project path")
    if not folder and path == base:
        raise ValueError("Choose an asset path")
    return path


def protected(path):
    return any(p.casefold() in PROTECTED or p.startswith(".") for p in path.split("/") if p)


def read_record(root, folder, identifier):
    path = root / "organization" / folder / (workflow.identifier(identifier) + ".json")
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError("Organization record is missing; scan and preview first")
    if path.stat().st_size > 32 * 1024**2:
        raise ValueError("Organization record is too large; choose a smaller folder")
    return json.loads(path.read_text(encoding="utf-8"))


def pinned_paths(root):
    """Generated revisions need their explicit material-reuse paths to remain valid."""
    result = set()

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "material_bindings" and isinstance(child, dict):
                    for native_path in child.values():
                        if isinstance(native_path, str):
                            result.add(
                                native_path.split(".", 1)[0]
                                if native_path.startswith("/Game/")
                                else native_path
                            )
                elif key == "reuse_path" and isinstance(child, str):
                    result.add(child.split(".", 1)[0] if child.startswith("/Game/") else child)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for path in [root / "art-direction.json", *(root / "work").glob("*/*/asset.json")]:
        visit(core.read_optional_json(path) or {})
    return result


def clean_name(text):
    text = unicodedata.normalize("NFKC", text)
    words = re.findall(r"[^\W_]+", text, re.UNICODE)
    value = (
        "".join(
            ("_" if i and w.isdigit() else "") + w[:1].upper() + w[1:] for i, w in enumerate(words)
        )
        or "Asset"
    )
    if len(value) > 64:
        value = value[:55] + "_" + hashlib.sha256(value.encode()).hexdigest()[:8]
    return value


def proposed_name(entry, rules, override=None):
    stem = PurePosixPath(entry["path"]).stem if entry.get("extension") else entry["name"]
    if override is not None:
        stem = override
    stem = re.sub("^" + re.escape(rules[entry["kind"]][1]), "", stem, count=1, flags=re.I)
    stem = re.sub(r"^(?:SM|SK|PF|BP|MI|M|T|SPR|S|A|AC|VFX|F)_", "", stem, flags=re.I)
    variant = re.search(r"(_[0-9]{2,})$", stem)
    variant_suffix = variant.group(1) if variant else ""
    if variant:
        stem = stem[: variant.start()]
    suffix = ""
    if entry["kind"] == "texture":
        role = entry.get("texture_role")
        for label, expression in TEXTURE_ROLES.items():
            match = re.search(r"(?:[_ .-])(" + expression + r")$", stem, re.I)
            if match:
                stem = stem[: match.start()]
                role = role or label
                break
        if role in TEXTURE_ROLES:
            suffix = "_" + role
    return rules[entry["kind"]][1] + clean_name(stem) + suffix + variant_suffix


def rules_for(settings):
    rules = dict(RULES)
    overrides = settings.get("rules", {})
    if not isinstance(overrides, dict) or overrides.keys() - RULES.keys():
        raise ValueError("Custom rules must use a supported asset kind")
    for kind, row in overrides.items():
        if not isinstance(row, dict) or row.keys() - {"folder", "prefix"}:
            raise ValueError("A naming rule supports folder and prefix")
        folder, prefix = row.get("folder", rules[kind][0]), row.get("prefix", rules[kind][1])
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_/]{0,79}", folder) or protected(folder):
            raise ValueError("Use a simple relative category folder")
        if "//" in folder or folder.endswith("/"):
            raise ValueError("Invalid category folder")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,15}", prefix):
            raise ValueError("Use a short letter/digit/underscore prefix")
        rules[kind] = (folder, prefix)
    return rules


def make_plan(scan, settings, pinned=(), annotation_paths=()):
    engine = scan["engine"]
    if scan.get("truncated"):
        raise ValueError("Scan limit reached; scan a smaller folder before organizing")
    if settings.keys() - {"destination", "rename", "group_by", "exclude", "overrides", "rules"}:
        raise ValueError("Unknown organization setting")
    destination = path_check(
        settings.get("destination")
        or ("Assets/GameAssets" if engine == "unity" else "/Game/GameAssets"),
        engine,
        True,
    )
    if protected(destination):
        raise ValueError("Choose a destination outside protected engine/plugin folders")
    rename = settings.get("rename", True)
    group = settings.get("group_by", "type")
    if type(rename) is not bool or group not in {"type", "source"}:
        raise ValueError("rename must be boolean; group_by must be type or source")
    excluded = settings.get("exclude", [])
    if not isinstance(excluded, list) or len(excluded) > 200:
        raise ValueError("Use at most 200 excluded asset/folder paths")
    for path in excluded:
        path_check(path, engine, True)
    overrides = settings.get("overrides", {})
    if not isinstance(overrides, dict) or len(overrides) > 2000:
        raise ValueError("Use at most 2,000 explicit name overrides")
    entries = scan["entries"]
    if overrides.keys() - {e["path"] for e in entries}:
        raise ValueError("Name overrides must refer to scanned assets")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 160 for v in overrides.values()):
        raise ValueError("Name overrides must be short nonempty text")
    rules = rules_for(settings)
    occupied = {p.casefold() for p in [*scan.get("occupied", []), *annotation_paths]}
    occupied.update(e["path"].casefold() for e in entries)
    rows = []
    for entry in sorted(entries, key=lambda e: e["path"]):
        old = path_check(entry["path"], engine)
        reason = entry.get("reason", "")
        if protected(old):
            reason = "Protected engine/plugin folder"
        elif old in pinned:
            reason = "Material path retained by a generated source revision"
        elif any(old == p or old.startswith(p + "/") for p in excluded):
            reason = "Excluded by project rule"
        elif entry["kind"] not in rules:
            reason = reason or "Classified for review; this type stays in its original location"
        new, collision = old, False
        if not reason:
            folder = rules[entry["kind"]][0]
            if group == "source" and old.startswith(destination + "/"):
                folder = str(PurePosixPath(old).parent).removeprefix(destination + "/")
            elif group == "source":
                relative = str(PurePosixPath(old).parent).removeprefix(scan["scope"] + "/")
                if relative != scan["scope"]:
                    folder = "/".join(clean_name(p) for p in relative.split("/")) + "/" + folder
            name = proposed_name(entry, rules, overrides.get(old)) if rename else entry["name"]
            extension = entry.get("extension", "")
            base = destination + "/" + folder + "/" + name
            new = base + extension
            if new.casefold() != old.casefold():
                index = 2
                while new.casefold() in occupied:
                    collision = True
                    new = base + f"_{index:02}" + extension
                    index += 1
            else:
                new = (
                    old  # Case-only renames vary by filesystem; never stage a hidden intermediate.
                )
            if len(new) > 220:
                reason, new = "Destination path too long; shorten the folder or name", old
            occupied.add(new.casefold())
        rows.append(
            {
                **entry,
                "source": old,
                "destination": new,
                "action": "skip" if reason else "keep" if new == old else "move",
                "reason": reason,
                "collision_resolved": collision,
            }
        )
    return {
        "schema_version": 1,
        "engine": engine,
        "scan_id": scan["scan_id"],
        "scope": scan["scope"],
        "destination": destination,
        "settings": settings,
        "entries": rows,
        "summary": {
            "scanned": len(rows),
            "move": sum(r["action"] == "move" for r in rows),
            "skip": sum(r["action"] == "skip" for r in rows),
            "keep": sum(r["action"] == "keep" for r in rows),
            "collisions_resolved": sum(r["collision_resolved"] for r in rows),
            "categories": dict(Counter(r["kind"] for r in rows)),
        },
        "warnings": [
            "Native serialized references are preserved. Code/config string paths are not "
            "rewritten; exclude assets loaded by custom paths.",
            "Names use filenames, native types and texture roles. Use overrides for semantic "
            "names; no visual AI classification is claimed.",
        ],
    }


@contextmanager
def annotation_lock(root):
    folder = root / "organization"
    if folder.resolve() != folder:
        raise ValueError("Organization state cannot traverse a symlink")
    folder.mkdir(exist_ok=True)
    path = folder / "annotations.lock"
    if path.is_symlink():
        raise ValueError("Annotation lock cannot be a symlink")
    with path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def sync_annotations(root):
    with annotation_lock(root):
        _sync_annotations(root)


def save_annotation(root, path, data):
    with annotation_lock(root):
        _sync_annotations(root)
        annotations = core.read_optional_json(root / "project-library.json") or {}
        annotations[path] = data
        core.atomic_json(root / "project-library.json", annotations)


def _sync_annotations(root):
    """Replay only new native move events; repeats and undo cannot remap unrelated new assets."""
    marker = root / "organization" / "annotation-events.json"
    seen = core.read_optional_json(marker) or {}
    annotations = core.read_optional_json(root / "project-library.json") or {}
    changed = updated = False
    for path in sorted(
        (root / "organization/journals").glob("*.json"), key=lambda p: p.stat().st_mtime
    ):
        stamp = path.stat().st_mtime_ns
        previous = seen.get(path.stem, {})
        if isinstance(previous, dict) and previous.get("stamp") == stamp:
            continue
        journal = core.read_optional_json(path) or {}
        events = journal.get("events", [])
        start = previous.get("count", 0) if isinstance(previous, dict) else previous
        for event in events[start:]:
            old, new = event["source"], event["destination"]
            # UE library entries use object paths; plans and native rename use package paths.
            pairs = [(old, new)]
            if journal.get("engine") == "unreal":
                pairs.append(
                    (old + "." + old.rsplit("/", 1)[-1], new + "." + new.rsplit("/", 1)[-1])
                )
            for before, after in pairs:
                if before in annotations:
                    if after in annotations:
                        raise ValueError("Annotation destination is occupied: " + after)
                    annotations[after] = annotations.pop(before)
            changed = True
        seen[path.stem] = {"count": len(events), "stamp": stamp}
        updated = True
    if changed:
        core.atomic_json(root / "project-library.json", annotations)
    if updated:
        core.atomic_json(marker, seen)


def organize(
    project, mode="scan", scan_id=None, plan_id=None, scope=None, settings=None, offset=0, limit=200
):
    target = registry.resolve(project)
    root = root_for(project)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Use offset >= 0 and limit between 1 and 500")
    if mode == "scan":
        scope = path_check(
            scope or ("Assets" if target.engine == "unity" else "/Game"), target.engine, True
        )
        return development.request(project, "organize", mode="scan", scope_path=scope)
    if mode == "plan":
        scan = read_record(root, "scans", scan_id)
        if scan["engine"] != target.engine:
            raise ValueError("Scan belongs to another engine")
        sync_annotations(root)
        annotation_paths = (core.read_optional_json(root / "project-library.json") or {}).keys()
        plan = make_plan(scan, settings or {}, pinned_paths(root), annotation_paths)
        plan_id = uuid.uuid4().hex
        plan.update(plan_id=plan_id, created_utc=workflow.now())
        core.atomic_json(root / "organization/plans" / (plan_id + ".json"), plan)
        return organize(project, "inspect", plan_id=plan_id, offset=offset, limit=limit)
    if mode == "history":
        paths = sorted(
            (root / "organization/plans").glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:20]
        return {"plans": [organize(project, "inspect", plan_id=p.stem, limit=1) for p in paths]}
    if mode not in {"inspect", "apply", "undo"}:
        raise ValueError("Choose scan, plan, inspect, apply, undo or history")
    plan = read_record(root, "plans", plan_id)
    journal = core.read_optional_json(root / "organization/journals" / (plan_id + ".json")) or {}
    if mode == "inspect":
        metadata_error = None
        try:
            sync_annotations(root)
        except ValueError as error:
            metadata_error = str(error)
        return {
            **plan,
            "status": journal.get("status", "planned"),
            "metadata_error": metadata_error,
            "journal": {k: v for k, v in journal.items() if k not in {"entries", "events"}},
            "moved": sum(e.get("current") == e["destination"] for e in journal.get("entries", [])),
            "entries": plan["entries"][offset : offset + limit],
            "offset": offset,
            "total": len(plan["entries"]),
            "has_more": offset + limit < len(plan["entries"]),
        }
    path = root / "organization/plans" / (plan_id + ".json")
    if mode == "apply" and not journal:
        annotations = core.read_optional_json(root / "project-library.json") or {}
        for row in plan["entries"]:
            destination = row["destination"]
            if row["action"] == "move" and (
                destination in annotations
                or destination + "." + destination.rsplit("/", 1)[-1] in annotations
            ):
                raise ValueError("Annotations changed since preview; generate a fresh plan")
    return development.request(
        project,
        "organize",
        mode=mode,
        plan_id=plan_id,
        plan_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
