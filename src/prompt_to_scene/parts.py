"""Named parts and independent locks for imported static assets."""

import math
from pathlib import Path

from . import core, preparation, sources, workflow


def edit(
    project,
    asset_id,
    part,
    changes=None,
    members=None,
    lock_geometry=None,
    lock_material=None,
    replacement_path=None,
):
    info = workflow.inspect_asset(project, asset_id)
    if info["current"].get("status") != "imported":
        raise ValueError("Wait for this asset's current import before editing")
    if not isinstance(part, str) or not part.strip() or len(part) > 100:
        raise ValueError("Choose a short part name")
    report = info["metadata"].get("report") or {}
    parts = report.get("parts", {})
    if members:
        if (
            not isinstance(members, list)
            or not 1 <= len(members) <= 128
            or any(m not in parts for m in members)
        ):
            raise ValueError("Choose existing part names from inspect_asset")
    elif part not in parts:
        raise ValueError("Unknown part; choose existing parts as members to create a named group")
    changes = changes or {}
    if set(changes) - {"scale", "offset", "rotation", "color", "roughness", "metallic"}:
        raise ValueError("Unsupported part change")
    for key, value in changes.items():
        values = value if key in {"scale", "offset", "rotation", "color"} else [value]
        if key in {"scale", "offset", "rotation", "color"}:
            core.position_values(values)
        for v in values:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError("Part values must be finite numbers")
            if key in {"color", "roughness", "metallic"} and not 0 <= v <= 1:
                raise ValueError("Material values must be between zero and one")
            if key == "scale" and not 0.01 <= v <= 100:
                raise ValueError("Scale must be between .01 and 100")
    for flag in (lock_geometry, lock_material):
        if flag is not None and type(flag) is not bool:
            raise ValueError("Locks must be booleans")
    if members and part in parts and part not in members:
        raise ValueError("Include the existing group in members before merging into its name")
    geometry_change = bool(set(changes) & {"scale", "offset", "rotation"} or replacement_path)
    material_change = bool(set(changes) & {"color", "roughness", "metallic"})
    for member in members or [part]:
        locks = parts[member].get("locks", {})
        if geometry_change and locks.get("geometry") and lock_geometry is not False:
            raise ValueError("Unlock this part's geometry before changing it")
        if material_change and locks.get("material") and lock_material is not False:
            raise ValueError("Unlock this part's material before changing it")
    replacement = sources.validate_source({"path": replacement_path}) if replacement_path else None
    payload = dict(
        part=part,
        changes=changes,
        members=members,
        lock_geometry=lock_geometry,
        lock_material=lock_material,
        replacement=replacement,
    )
    current = Path(info["source_blend"])
    original = current.with_name("original.blend")
    source = original if original.exists() else current
    config = preparation.options((info["metadata"].get("preparation") or {}).get("settings"))
    payload["normalize"] = config if original.exists() else None
    config = {**config, "ground": False, "target_size": None, "unit_scale": 1.0, "up_axis": "auto"}
    prior = info["metadata"].get("preparation") or {}
    before_count = prior.get("triangles_before", 0)
    old_budget = (prior.get("settings") or {}).get("triangle_budget", before_count)
    fallback_ratio = min(
        1.0, old_budget / max(1, before_count) * (0.96 if before_count > old_budget else 1)
    )
    fixed = [
        name
        for label, row in parts.items()
        if label not in (members or [part]) or not geometry_change
        for name in row["objects"]
    ]
    payload["preserve_ratios"] = {
        name: prior.get("objects", {}).get(name, {}).get("ratio", fallback_ratio)
        if prior.get("objects", {}).get(name, {}).get("accepted", True)
        else 1.0
        for name in fixed
    }
    script = (
        "import runpy, json\nfrom pathlib import Path\n"
        'runpy.run_path(str(Path(__file__).with_name("blender_edit.py")))["apply"]('
        + repr(payload)
        + ")\n"
    )
    return workflow.submit(
        project,
        asset_id,
        script,
        blend_file=str(source),
        collider=config["collision"] != "none",
        preparation=config,
        provenance=info["metadata"].get("provenance"),
    )
