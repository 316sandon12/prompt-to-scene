"""Native project organization. Renames keep UE references/redirectors and an undo journal."""

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

import unreal

from .protocol import write_json

_pending = None
_handle = None
TAG = "PromptToScene.OrganizerId"
RESERVED = {
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
CLASSES = {
    "StaticMesh": "model",
    "SkeletalMesh": "skeletal_mesh",
    "Blueprint": "blueprint",
    "WidgetBlueprint": "blueprint",
    "AnimBlueprint": "controller",
    "Material": "material",
    "MaterialInstanceConstant": "material_instance",
    "MaterialInstance": "material_instance",
    "Texture2D": "texture",
    "TextureCube": "texture",
    "Texture2DArray": "texture",
    "VolumeTexture": "texture",
    "PaperSprite": "sprite",
    "SoundWave": "audio",
    "SoundCue": "audio",
    "MetaSoundSource": "audio",
    "AnimSequence": "animation",
    "AnimMontage": "animation",
    "AnimComposite": "animation",
    "BlendSpace": "animation",
    "BlendSpace1D": "animation",
    "NiagaraSystem": "vfx",
    "NiagaraEmitter": "vfx",
    "ParticleSystem": "vfx",
    "Font": "font",
    "FontFace": "font",
    "World": "scene",
    "DataTable": "data",
    "DataAsset": "data",
    "PrimaryDataAsset": "data",
    "ObjectRedirector": "redirector",
}
MOVABLE = set(CLASSES.values()) - {"scene", "data", "redirector"}


def path_guard(path):
    if not isinstance(path, str) or len(path) > 240 or not re.fullmatch(r"/Game(?:/[\w-]+)*", path):
        raise ValueError(
            "Use a package/folder path inside /Game with letters, digits and underscores"
        )
    content = Path(unreal.Paths.project_content_dir()).resolve()
    physical = content / path.removeprefix("/Game").lstrip("/")
    if physical.resolve() != physical:
        raise ValueError("Asset path traverses a symlink")
    for extension in (".uasset", ".umap", ".uexp", ".ubulk"):
        if physical.with_suffix(extension).is_symlink():
            raise ValueError("Asset file is a symlink")
    return physical


def protected(path):
    return any(p.casefold() in RESERVED or p.startswith(".") for p in path.split("/") if p)


def record(root, folder, identifier):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier or ""):
        raise ValueError("Invalid organization ID")
    path = root / "organization" / folder / (identifier + ".json")
    if (
        path.resolve() != path
        or path.is_symlink()
        or (path.exists() and path.stat().st_size > 32 * 1024**2)
    ):
        raise ValueError("Invalid organization record")
    return path


def fingerprint(path):
    physical = path_guard(path)
    stamps = []
    for extension in (".uasset", ".umap", ".uexp", ".ubulk"):
        file = physical.with_suffix(extension)
        if file.exists():
            stat = file.stat()
            stamps.append(f"{extension}:{stat.st_size}:{stat.st_mtime_ns}")
    return ";".join(stamps)


def kind(data):
    return CLASSES.get(str(data.asset_class_path.asset_name), "other")


def reason(path, category):
    physical = path_guard(path)
    if protected(path):
        return "Protected engine/plugin folder"
    if category not in MOVABLE:
        return "Classified for review; this type stays in its original location"
    source = physical.with_suffix(".uasset")
    if not source.is_file():
        return "Save this asset before organizing"
    if not os.access(source, os.W_OK) or source.stat().st_mode & 0o222 == 0:
        return "Read-only asset"
    return ""


def main_asset(rows, path):
    # Renamed Blueprints can retain generated-class redirectors in the same package.
    # A package is one move unit; its first registry row is not necessarily its main asset.
    return max(
        (r for r in rows if str(r.package_name) == path),
        key=lambda r: (
            str(r.asset_name) == path.rsplit("/", 1)[-1],
            not r.is_redirector(),
            kind(r) in MOVABLE,
        ),
        default=None,
    )


def data_at(path):
    rows = unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_package_name(path)
    return main_asset(rows, path)


def occupied(path, obj=None, restoring=False):
    data = data_at(path)
    if data:
        if restoring and data.is_redirector() and unreal.load_asset(path) == obj:
            return False  # Rename manager handles a redirector back to this same object.
        return True
    physical = path_guard(path)
    return (
        any(physical.with_suffix(ext).exists() for ext in (".uasset", ".umap")) or physical.is_dir()
    )


def scan(root, request, scope):
    path_guard(scope)
    if not unreal.EditorAssetLibrary.does_directory_exist(scope):
        raise ValueError("Choose an existing project folder")
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.wait_for_completion()
    all_assets = registry.get_assets_by_path("/Game", recursive=True)
    packages = {}
    for data in all_assets:
        packages.setdefault(str(data.package_name), []).append(data)
    paths = sorted(packages)
    scoped = [main_asset(packages[path], path) for path in paths if path.startswith(scope + "/")]
    entries = []
    for data in scoped[:20000]:
        path = str(data.package_name)
        row = dict(
            path=path,
            name=str(data.asset_name),
            kind=kind(data),
            extension="",
            id=path,
            fingerprint="",
            reason="",
            texture_role="",
        )
        try:
            row["reason"] = reason(path, row["kind"])
            row["fingerprint"] = fingerprint(path)
            if str(data.get_tag_value("CompressionSettings") or "") == "TC_Normalmap":
                row["texture_role"] = "Normal"
        except Exception as error:
            row["reason"] = str(error)
        entries.append(row)
    write_json(
        record(root, "scans", request["request_id"]),
        dict(
            schema_version=1,
            engine="unreal",
            scan_id=request["request_id"],
            scope=scope,
            total=len(scoped),
            truncated=len(scoped) > 20000,
            occupied=paths,
            entries=entries,
        ),
    )
    return {
        "development": dict(
            command="organize",
            mode="scan",
            scan_id=request["request_id"],
            changed=len(entries),
            truncated=len(scoped) > 20000,
        )
    }


def execute(request, c, root):
    global _pending, _handle
    if _pending:
        raise ValueError("Another organization is running")
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        raise ValueError("Leave PIE before organizing assets")
    mode = c["mode"]
    if mode == "scan":
        return scan(root, request, c["scope_path"])
    if mode not in {"apply", "undo"}:
        raise ValueError("Unknown organization operation")
    plan_file = record(root, "plans", c["plan_id"])
    raw = plan_file.read_bytes()
    if hashlib.sha256(raw).hexdigest() != c["plan_sha256"]:
        raise ValueError("Naming plan changed; preview it again")
    plan = json.loads(raw)
    if (
        plan.get("schema_version") != 1
        or plan.get("engine") != "unreal"
        or plan.get("plan_id") != c["plan_id"]
        or len(plan.get("entries", [])) > 20000
    ):
        raise ValueError("Invalid organization plan")
    journal_path = record(root, "journals", c["plan_id"])
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else None
    if journal and (
        (mode == "apply" and journal["status"] == "applied")
        or (mode == "undo" and journal["status"] == "undone")
    ):
        return {
            "development": dict(
                command="organize",
                mode=mode,
                plan_id=c["plan_id"],
                changed=0,
                organization_status=journal["status"],
            )
        }
    if mode == "apply" and journal:
        raise ValueError("This plan already ran; undo it or create a fresh plan")
    if mode == "undo" and not journal:
        raise ValueError("Apply this plan before undoing it")
    entries = (
        [dict(e, current=e["source"]) for e in plan["entries"] if e["action"] == "move"]
        if mode == "apply"
        else journal["entries"]
    )
    destinations, objects = set(), []
    dirty = {
        p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    }
    for row in entries:
        old, new = row["source"], row["destination"]
        path_guard(old)
        path_guard(new)
        if old == new or protected(old) or protected(new) or new.casefold() in destinations:
            raise ValueError("Invalid or duplicate organization path")
        destinations.add(new.casefold())
        if mode == "apply":
            data = data_at(old)
            if (
                not data
                or data.is_redirector()
                or fingerprint(old) != row["fingerprint"]
                or kind(data) != row["kind"]
            ):
                raise ValueError("Asset changed since preview: " + old)
            issue = reason(old, kind(data))
            if issue:
                raise ValueError(issue + ": " + old)
            if old in dirty:
                raise ValueError("Save this asset before organizing: " + old)
            obj = data.get_asset()
        else:
            # A redirector may resolve an interrupted move; verify identity and actual package.
            obj = (
                unreal.load_asset(row["current"])
                or unreal.load_asset(old)
                or unreal.load_asset(new)
            )
            if (
                not obj
                or unreal.EditorAssetLibrary.get_metadata_tag(obj, TAG) != row["native_id"]
                or obj.get_outer().get_path_name() not in {old, new}
            ):
                raise ValueError("Asset identity moved outside this plan: " + old)
        if not obj:
            raise ValueError("Could not load asset: " + old)
        current = obj.get_outer().get_path_name()
        target = new if mode == "apply" else old
        if current != target and occupied(target, obj, restoring=mode == "undo"):
            raise ValueError("Destination is occupied: " + target)
        objects.append(obj)
    if journal is None:
        journal = dict(engine="unreal", plan_id=c["plan_id"], entries=entries, events=[])
    for row, obj in zip(entries, objects):
        current = obj.get_outer().get_path_name()
        if current != row["current"]:
            journal["events"].append(dict(source=row["current"], destination=current))
        row["current"] = current
        row["native_id"] = unreal.EditorAssetLibrary.get_metadata_tag(obj, TAG) or uuid.uuid4().hex
    journal.update(status="applying" if mode == "apply" else "undoing", error=None)
    write_json(journal_path, journal)
    _pending = dict(
        root=root,
        request=request,
        journal=journal,
        path=journal_path,
        objects=objects,
        mode=mode,
        index=0,
        changed=0,
    )
    _handle = unreal.register_slate_post_tick_callback(tick)
    return {
        "status": "queued",
        "development": dict(
            command="organize",
            mode=mode,
            plan_id=c["plan_id"],
            organization_status=journal["status"],
        ),
    }


def move_batch(state, restoring=False):
    changes, records = [], []
    for row, obj in zip(state["journal"]["entries"], state["objects"]):
        current = obj.get_outer().get_path_name()
        target = row["source"] if restoring else row["destination"]
        if current == target:
            continue
        if current not in {row["source"], row["destination"]}:
            raise ValueError("Asset moved outside this plan")
        path_guard(current)
        path_guard(target)
        if occupied(target, obj, restoring):
            raise ValueError("Destination became occupied: " + target)
        folder, name = target.rsplit("/", 1)
        changes.append(unreal.AssetRenameData(asset=obj, new_package_path=folder, new_name=name))
        records.append((row, obj, current, target))
    if not changes:
        return 0
    # Persist identity before native mutation so interrupted batches remain recoverable.
    for row, obj, current, _ in records:
        unreal.EditorAssetLibrary.set_metadata_tag(obj, TAG, row["native_id"])
        if not unreal.EditorAssetLibrary.save_loaded_asset(obj, only_if_is_dirty=False):
            raise ValueError("Could not save asset identity: " + current)
    # One native batch lets UE fix references among assets being moved together.
    ok = unreal.AssetToolsHelpers.get_asset_tools().rename_assets(changes)
    for row, obj, current, _ in records:
        actual = obj.get_outer().get_path_name()
        if actual != current:
            row["current"] = actual
            state["journal"]["events"].append(dict(source=current, destination=actual))
    write_json(state["path"], state["journal"])
    if not ok or any(obj.get_outer().get_path_name() != target for _, obj, _, target in records):
        raise ValueError("Native batch rename did not complete; restoring its completed moves")
    # Save the batch only after every in-batch reference has its final path.
    for _, obj, _, target in records:
        if not unreal.EditorAssetLibrary.save_loaded_asset(obj, only_if_is_dirty=False):
            raise ValueError("Could not save renamed asset: " + target)
    return len(records)


def finish(status, error=None):
    global _pending, _handle
    state = _pending
    state["journal"].update(status=status, error=error)
    write_json(state["path"], state["journal"])
    write_json(
        state["root"] / "action-receipts" / (state["request"]["request_id"] + ".json"),
        dict(
            request_id=state["request"]["request_id"],
            engine="unreal",
            status="completed"
            if error is None
            else "cancelled"
            if status == "cancelled"
            else "error",
            error=error,
            development=dict(
                command="organize",
                mode=state["mode"],
                plan_id=state["journal"]["plan_id"],
                changed=state["changed"],
                organization_status=status,
                message="Native renames retain UE references/redirectors. "
                "Custom code/config strings are not rewritten.",
            ),
        ),
    )
    unreal.unregister_slate_post_tick_callback(_handle)
    _pending = _handle = None


def tick(_delta):
    state = _pending
    if state is None or state.get("ticking"):
        return
    # Native rename/save can pump Slate during a slow task. Never re-enter this batch.
    state["ticking"] = True
    cancelled = (state["root"] / "cancel" / state["request"]["request_id"]).exists()
    try:
        if cancelled:
            raise ValueError("Organization cancelled")
        if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
            raise ValueError("Organization interrupted by PIE")
        state["changed"] = move_batch(state, restoring=state["mode"] == "undo")
        cancelled = (state["root"] / "cancel" / state["request"]["request_id"]).exists()
        if cancelled and state["mode"] == "apply":
            raise ValueError("Organization cancelled")
        finish("applied" if state["mode"] == "apply" else "undone")
    except Exception as error:
        status, detail = "recovery_required", str(error)
        if state["mode"] == "apply":
            try:
                move_batch(state, restoring=True)
                state["changed"] = 0
                status = "cancelled" if cancelled else "rolled_back"
            except Exception as rollback:
                detail += "; rollback needs attention: " + str(rollback)
        finish(status, detail)
    finally:
        state["ticking"] = False
