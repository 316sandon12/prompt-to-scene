"""Validated game-asset preparation options; shared by all creation entry points."""

import math

from . import styles


def options(values=None, quality="desktop"):
    if quality not in styles.QUALITY or quality == "draft":
        raise ValueError("Preparation quality must be mobile, desktop or hero")
    budget = styles.QUALITY[quality]
    result = {
        "triangle_budget": budget["triangles"],
        "texture_size": budget["texture_size"],
        "max_deviation_percent": 2.0,
        "lod_ratios": [0.5, 0.25],
        "collision": "convex",
        "target_size": None,
        "unit_scale": 1.0,
        "up_axis": "auto",
        "ground": True,
    }
    if values is not None and (not isinstance(values, dict) or set(values) - result.keys()):
        raise ValueError("Unknown preparation option")
    result.update(values or {})
    for key, low, high in (
        ("triangle_budget", 12, 200000),
        ("max_deviation_percent", 0.001, 10),
        ("unit_scale", 0.000001, 10000),
        ("target_size", 0.001, 1000),
    ):
        value = result[key]
        if key == "target_size" and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(key + " must be numeric")
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}")
    if type(result["triangle_budget"]) is not int:
        raise ValueError("triangle_budget must be an integer")
    if type(result["texture_size"]) is not int or result["texture_size"] not in {
        256,
        512,
        1024,
        2048,
    }:
        raise ValueError("texture_size must be 256, 512, 1024 or 2048")
    if result["collision"] not in {"none", "box", "convex"}:
        raise ValueError("collision must be none, box or convex")
    if result["up_axis"] not in {"auto", "X", "Y", "Z", "-X", "-Y", "-Z"}:
        raise ValueError("up_axis describes the imported mesh's up axis, or auto")
    if type(result["ground"]) is not bool:
        raise ValueError("ground must be a boolean")
    ratios = result["lod_ratios"]
    if not isinstance(ratios, list) or len(ratios) > 3:
        raise ValueError("Choose zero to three decreasing LOD ratios")
    last = 1.0
    for ratio in ratios:
        if isinstance(ratio, bool) or not isinstance(ratio, (float, int)):
            raise ValueError("LOD ratios must be numbers")
        if not math.isfinite(ratio) or not 0.05 <= ratio < last:
            raise ValueError("LOD ratios must decrease, between 0.05 and 1")
        last = ratio
    return result
