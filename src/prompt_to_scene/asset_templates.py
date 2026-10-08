"""Project-local, versioned designs that retain editable geometry and provenance."""

import hashlib
import shutil
import uuid
from copy import deepcopy
from pathlib import Path

from . import authoring, core, game_art, preparation, recipes, workflow


def folder(project):
    return game_art.root(project) / "design-library"


def save(project, name, asset_id, description="", tags=None):
    core.asset_id(name)
    info = workflow.inspect_asset(project, asset_id)
    if info["current"].get("status") != "imported":
        raise ValueError("Save a successfully imported design")
    description = game_art.text(description, "description", 1000)
    if not isinstance(tags or [], list) or len(tags or []) > 20:
        raise ValueError("Use up to 20 tags")
    tags = [game_art.text(t, "tag", 60) for t in tags or []]
    source = Path(info["source_blend"])
    if not source.is_file():
        raise ValueError("This asset's editable source is unavailable")
    version = uuid.uuid4().hex
    destination = folder(project) / name / version
    destination.mkdir(parents=True)
    try:
        shutil.copy2(source, destination / "source.blend")
        if info.get("script"):
            (destination / "model.py").write_text(info["script"], encoding="utf-8")
        metadata = info["metadata"]
        recipe = deepcopy(metadata.get("recipe"))
        design = (metadata.get("provenance") or {}).get("art_design") or (recipe or {}).get(
            "art_design"
        )
        row = {
            "name": name,
            "version": version,
            "asset_id": asset_id,
            "source_revision": info["current"]["request_id"],
            "description": description,
            "tags": tags,
            "recipe": recipe,
            "design": design,
            "parts": (metadata.get("report") or {}).get("parts", {}),
            "provenance": metadata.get("provenance"),
            "source_sha256": hashlib.sha256(
                (destination / "source.blend").read_bytes()
            ).hexdigest(),
            "preparation": (metadata.get("preparation") or {}).get("settings"),
            "created_utc": workflow.now(),
        }
        core.atomic_json(destination / "template.json", row)
        core.atomic_json(folder(project) / name / "latest.json", {"version": version})
    except Exception:
        shutil.rmtree(destination)
        raise
    return row


def read(project, name, version=None):
    base = folder(project) / core.asset_id(name)
    if version is None:
        version = (core.read_optional_json(base / "latest.json") or {}).get("version")
    if not version:
        raise ValueError("Unknown saved design")
    path = base / workflow.identifier(version)
    row = core.read_optional_json(path / "template.json")
    if (
        not row
        or hashlib.sha256((path / "source.blend").read_bytes()).hexdigest() != row["source_sha256"]
    ):
        raise ValueError("Saved source changed; save a new design version")
    return row, path


def search(project, query=""):
    from .project_library import rank

    rows = []
    for path in sorted(folder(project).glob("*/latest.json")):
        row, _ = read(project, path.parent.name)
        rows.append(
            {
                "path": row["name"],
                "name": row["name"],
                "notes": row["description"],
                "tags": row["tags"],
                "version": row["version"],
                "kind": (row.get("recipe") or {}).get("kind", "custom"),
                "parts": list(row["parts"]),
                "source_asset": row["asset_id"],
            }
        )
    return {"templates": rank(rows, query, limit=30)}


def instantiate(
    project,
    name,
    asset_id,
    version=None,
    parameters=None,
    part_changes=None,
    position=None,
    family_style=False,
    retry_request_id=None,
):
    row, path = read(project, name, version)
    core.asset_id(asset_id)
    current = workflow.inspect_asset(project, asset_id)["current"]
    retry = (
        retry_request_id
        and current.get("request_id") == retry_request_id
        and current["status"] in {"error", "cancelled"}
    )
    if current["status"] != "unknown" and not retry:
        raise ValueError("Choose a new asset ID; edit existing instances with the part tools")
    if row.get("recipe"):
        script, recipe = recipes.revise(row["recipe"], parameters or {})
        for part, changes in (part_changes or {}).items():
            script, recipe = recipes.edit_part(recipe, part, changes)
        task = authoring.submit_recipe(project, asset_id, script, recipe, position)
    else:
        if parameters:
            raise ValueError("Custom designs expose named part changes, not recipe parameters")
        from .parts import validate_changes

        payloads = []
        for part, changes in (part_changes or {}).items():
            if part not in row["parts"]:
                raise ValueError("Unknown template part")
            validate_changes(changes)
            locks = row["parts"][part].get("locks", {})
            if locks.get("geometry") and set(changes) & {"scale", "offset", "rotation"}:
                raise ValueError("Template geometry is locked")
            if locks.get("material") and set(changes) & {"color", "roughness", "metallic"}:
                raise ValueError("Template material is locked")
            payloads.append(dict(part=part, changes=changes))
        script = "import runpy\nfrom pathlib import Path\n"
        for payload in payloads:
            script += (
                'runpy.run_path(str(Path(__file__).with_name("blender_edit.py")))'
                '["apply"](' + repr(payload) + ")\n"
            )
        config = preparation.options(
            {
                **(row["preparation"] or {}),
                "ground": False,
                "target_size": None,
                "unit_scale": 1,
                "up_axis": "auto",
            }
        )
        task = workflow.submit(
            project,
            asset_id,
            script,
            position,
            blend_file=str(path / "source.blend"),
            preparation=config,
            provenance={
                **(row["provenance"] or {}),
                "template": name,
                "template_version": row["version"],
            },
        )
    if family_style and (row.get("design") or row.get("recipe")):
        # A family is explicit project intent; instantiation alone never changes defaults.
        core.atomic_json(
            game_art.root(project) / "design-family.json",
            {
                "name": name,
                "version": row["version"],
                "design": row.get("design"),
                "style": (row.get("design") or row.get("recipe"))["style"],
                "parts": list(row["parts"]),
            },
        )
    return {**task, "template": name, "template_version": row["version"]}
