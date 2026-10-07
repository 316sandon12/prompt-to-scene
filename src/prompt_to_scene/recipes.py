"""Validated, persistent art-directed recipes and semantic edits."""

import json
import math
from copy import deepcopy

from . import design, styles

DEFAULTS = design.DEFAULTS
COMMON = {"color", "metal_color", "roughness", "seed", "variant", "detail", "taper"}
PART_FIELDS = {"scale", "offset", "rotation", "color", "material", "roughness", "wear"}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_part(changes):
    if not isinstance(changes, dict) or changes.keys() - PART_FIELDS:
        raise ValueError("Part edits support scale/offset/rotation/color/material/roughness/wear")
    for key in ("scale", "offset", "rotation", "color"):
        if key not in changes:
            continue
        v = changes[key]
        if not isinstance(v, list) or len(v) != 3 or not all(finite(n) for n in v):
            raise ValueError(key + " needs three finite values")
        if key == "scale" and any(n <= 0 or n > 10 for n in v):
            raise ValueError("Part scale must be positive and at most 10")
        if key == "color" and any(n < 0 or n > 1 for n in v):
            raise ValueError("Color uses linear RGB from 0 to 1")
        if key == "offset" and any(abs(n) > 100 for n in v):
            raise ValueError("Part offsets are limited to 100 meters")
    if "material" in changes and changes["material"] not in {"wood", "metal", "paint", "stone"}:
        raise ValueError("Choose wood, metal, paint or stone")
    for key in ("roughness", "wear"):
        if key in changes:
            styles.unit(changes[key], key)


def prepare(
    kind, parameters=None, *, style=None, quality=None, parts=None, locks=None, art_design=None
):
    if kind not in DEFAULTS:
        raise ValueError("Recipe must be one of " + ", ".join(DEFAULTS))
    parameters = deepcopy(parameters or {})
    if parameters.keys() - (DEFAULTS[kind].keys() | COMMON):
        raise ValueError(
            "Unknown recipe parameters: "
            + ", ".join(parameters.keys() - (DEFAULTS[kind].keys() | COMMON))
        )
    data = {**DEFAULTS[kind], "seed": 0, "variant": 0, "detail": 1, **parameters}
    for key, value in data.items():
        if key.endswith("color"):
            validate_part({"color": value})
        elif key in {"roughness", "taper"}:
            styles.unit(value, key)
            if key == "taper" and value < 0.3:
                raise ValueError("taper must be at least 0.3")
        elif key in {"seed", "variant", "detail", "planks", "shelves"}:
            limit = {
                "seed": (0, 1000000),
                "variant": (0, 2),
                "detail": (0, 1),
                "planks": (2, 16),
                "shelves": (2, 8),
            }[key]
            if not finite(value) or int(value) != value or not limit[0] <= value <= limit[1]:
                raise ValueError(f"{key} must be an integer from {limit[0]} to {limit[1]}")
        elif not finite(value) or not 0.01 <= value <= 100:
            raise ValueError(key + " must be between 0.01 and 100 meters")
    if kind == "table" and data["thickness"] >= data["height"] * 0.4:
        raise ValueError("thickness must be less than 40% of height")
    if kind == "chair" and data["seat_height"] >= data["height"] * 0.9:
        raise ValueError("seat_height must be less than 90% of height")
    if kind == "sign" and data["board_height"] >= data["height"] * 0.9:
        raise ValueError("board_height must be less than 90% of height")
    art = deepcopy(style or styles.preset())
    if quality:
        art["quality"] = quality
    styles.validate(art)
    parts, locks = deepcopy(parts or {}), deepcopy(locks or {})
    if (parts.keys() | locks.keys()) - set(design.PARTS[kind]):
        raise ValueError("Unknown part; choose " + ", ".join(design.PARTS[kind]))
    for edit in parts.values():
        validate_part(edit)
    recipe = {
        "version": 2,
        "kind": kind,
        "parameters": data,
        "style": art,
        "parts": parts,
        "locks": locks,
    }
    if art_design:
        recipe["art_design"] = deepcopy(art_design)
        recipe["art_design"]["style"] = deepcopy(art)
    items = design.plan(recipe)
    if any(any(not finite(v) or v <= 0 for v in item["size"]) for item in items):
        raise ValueError("These dimensions produce an invalid part; increase the available space")
    recipe["part_hashes"] = design.part_hashes(items)
    recipe["available_parts"] = design.PARTS[kind]
    script = (
        "import runpy, json\nfrom pathlib import Path\n"
        'runpy.run_path(str(Path(__file__).with_name("blender_recipe.py")))["build"](json.loads('
        + repr(json.dumps({"recipe": recipe, "objects": items}))
        + "))\n"
    )
    return script, recipe


def revise(recipe, parameters=None, *, style=None, quality=None, art_design=None):
    return prepare(
        recipe["kind"],
        {**recipe["parameters"], **(parameters or {})},
        style=style or recipe.get("style"),
        quality=quality,
        parts=recipe.get("parts"),
        locks=recipe.get("locks"),
        art_design=art_design or recipe.get("art_design"),
    )


def edit_part(recipe, part, changes=None, lock_geometry=None, lock_material=None):
    if part not in design.PARTS[recipe["kind"]]:
        raise ValueError("Unknown semantic part: " + part)
    changes = changes or {}
    validate_part(changes)
    updated = deepcopy(recipe)
    parts, locks = updated.setdefault("parts", {}), updated.setdefault("locks", {})
    old = locks.get(part, {})
    geometry_changes = changes.keys() & {"scale", "offset", "rotation"}
    material_changes = changes.keys() & {"color", "material", "roughness", "wear"}
    if old.get("geometry") and lock_geometry is not False and geometry_changes:
        raise ValueError("Unlock this part's geometry before changing it")
    if old.get("material") and lock_material is not False and material_changes:
        raise ValueError("Unlock this part's material before changing it")
    parts[part] = {**parts.get(part, {}), **changes}
    geometry = old.get("geometry", False) if lock_geometry is None else lock_geometry
    material = old.get("material", False) if lock_material is None else lock_material
    if not isinstance(geometry, bool) or not isinstance(material, bool):
        raise ValueError("Lock values must be booleans")
    if geometry or material:
        snapshot = deepcopy(old)
        snapshot.update(geometry=geometry, material=material)
        if geometry and not old.get("geometry"):
            snapshot.update(
                parameters=deepcopy(updated["parameters"]),
                style=deepcopy(updated.get("style") or styles.preset()),
                edit=deepcopy(parts[part]),
                treatment=deepcopy(updated.get("art_design", {}).get("treatment")),
            )
        if material and not old.get("material"):
            snapshot.update(
                material_parameters=deepcopy(updated["parameters"]),
                material_style=deepcopy(updated.get("style") or styles.preset()),
                material_edit=deepcopy(parts[part]),
                material_treatment=deepcopy(updated.get("art_design", {}).get("treatment")),
            )
        locks[part] = snapshot
    else:
        locks.pop(part, None)
    return prepare(
        updated["kind"],
        updated["parameters"],
        style=updated.get("style"),
        parts=parts,
        locks=locks,
        art_design=updated.get("art_design"),
    )
