"""Project art direction: concrete, versioned defaults shared by both AI hosts."""

import math
from copy import deepcopy

from . import core, registry

PRESETS = {
    "cozy": {
        "label": "温暖卡通 / Cozy",
        "description": "Rounded silhouettes, warm wood and muted teal accents",
        "roundness": 0.75,
        "taper": 0.72,
        "wear": 0.12,
        "palette": {
            "wood": [0.34, 0.16, 0.065],
            "metal": [0.065, 0.085, 0.09],
            "paint": [0.045, 0.26, 0.23],
            "stone": [0.32, 0.29, 0.25],
        },
    },
    "heritage": {
        "label": "乡村旧木 / Heritage",
        "description": "Slatted timber, iron hardware and restrained weathering",
        "roundness": 0.3,
        "taper": 0.88,
        "wear": 0.55,
        "palette": {
            "wood": [0.21, 0.085, 0.028],
            "metal": [0.075, 0.065, 0.055],
            "paint": [0.28, 0.055, 0.028],
            "stone": [0.27, 0.25, 0.22],
        },
    },
    "workshop": {
        "label": "工业工坊 / Workshop",
        "description": "Crisp panels, steel supports and ochre painted surfaces",
        "roundness": 0.15,
        "taper": 1.0,
        "wear": 0.22,
        "palette": {
            "wood": [0.24, 0.13, 0.058],
            "metal": [0.14, 0.18, 0.21],
            "paint": [0.58, 0.28, 0.025],
            "stone": [0.2, 0.22, 0.24],
        },
    },
}
QUALITY = {
    "draft": {"texture_size": 0, "segments": 1, "radial_segments": 12, "triangles": 12000},
    "mobile": {"texture_size": 256, "segments": 2, "radial_segments": 16, "triangles": 18000},
    "desktop": {"texture_size": 512, "segments": 3, "radial_segments": 24, "triangles": 50000},
    "hero": {"texture_size": 1024, "segments": 4, "radial_segments": 32, "triangles": 100000},
}


def unit(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(name + " must be a finite number from 0 to 1")
    return value


def validate(data):
    if data.get("preset") not in PRESETS or data.get("quality") not in QUALITY:
        raise ValueError("Choose a listed style and quality preset")
    if set(data) - {
        "schema_version",
        "preset",
        "quality",
        "palette",
        "roundness",
        "taper",
        "wear",
        "material_bindings",
        "roughness",
    }:
        raise ValueError("Unknown style field")
    for key in ("roundness", "taper", "wear"):
        unit(data[key], key)
    if data["taper"] < 0.3:
        raise ValueError("taper must be at least 0.3")
    if set(data["palette"]) != {"wood", "metal", "paint", "stone"}:
        raise ValueError("Palette needs wood, metal, paint and stone")
    for color in data["palette"].values():
        if not isinstance(color, list) or len(color) != 3:
            raise ValueError("Palette colors are three linear RGB values")
        for v in color:
            unit(v, "color")
    roughness = data.get("roughness", {})
    if not isinstance(roughness, dict) or roughness.keys() - data["palette"].keys():
        raise ValueError("Roughness maps material roles to values from 0 to 1")
    for value in roughness.values():
        unit(value, "roughness")
    for role, path in data.get("material_bindings", {}).items():
        if role not in data["palette"] or not isinstance(path, str):
            raise ValueError("Material bindings map material roles to engine asset paths")
        if not path.startswith(("Assets/", "/Game/")) or ".." in path or "\\" in path:
            raise ValueError("Reuse a material inside Assets/ or /Game/")
    return data


def preset(name="cozy", quality="desktop"):
    if name not in PRESETS:
        raise ValueError("Unknown style: " + name)
    source = deepcopy(PRESETS[name])
    source.pop("label")
    source.pop("description")
    return validate(
        {"schema_version": 1, "preset": name, "quality": quality, "material_bindings": {}, **source}
    )


def read(project=None):
    root = core.state_root(registry.resolve(project).root)
    return validate(core.read_optional_json(root / "art-direction.json") or preset())


def save(project=None, name=None, quality=None, overrides=None):
    old = read(project)
    data = preset(name, quality or old["quality"]) if name else deepcopy(old)
    if quality:
        data["quality"] = quality
    overrides = overrides or {}
    if set(overrides) - {"palette", "roundness", "taper", "wear", "material_bindings", "roughness"}:
        raise ValueError("Unknown art-direction override")
    for key, value in overrides.items():
        data[key] = {**data.get(key, {}), **value} if key in {"palette", "roughness"} else value
    validate(data)
    root = core.state_root(registry.resolve(project).root)
    core.atomic_json(root / "art-direction.json", data)
    (root / "design-family.json").unlink(missing_ok=True)
    return data
