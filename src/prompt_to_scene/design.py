"""Deterministic semantic construction plans, independent of Blender and the engines."""

import copy
import hashlib
import json
import math

DEFAULTS = {
    "crate": {"width": 1.0, "depth": 0.8, "height": 0.8, "planks": 5},
    "table": {"width": 1.5, "depth": 0.85, "height": 0.76, "thickness": 0.075},
    "chair": {"width": 0.52, "depth": 0.54, "height": 0.96, "seat_height": 0.46},
    "sign": {"width": 0.85, "depth": 0.12, "height": 1.65, "board_height": 0.55},
    "stool": {"width": 0.42, "depth": 0.42, "height": 0.46},
    "bench": {"width": 1.4, "depth": 0.44, "height": 0.46},
    "barrel": {"width": 0.7, "depth": 0.7, "height": 0.95},
    "cabinet": {"width": 1.05, "depth": 0.48, "height": 1.2},
    "shelf": {"width": 1.1, "depth": 0.38, "height": 1.6, "shelves": 4},
}
PARTS = {
    "crate": ["body", "lid", "straps", "hardware"],
    "table": ["top", "legs", "frame", "hardware"],
    "chair": ["seat", "legs", "backrest", "frame", "hardware"],
    "sign": ["post", "board", "frame", "hardware"],
    "stool": ["seat", "legs", "frame", "hardware"],
    "bench": ["seat", "legs", "frame", "hardware"],
    "barrel": ["body", "lid", "hoops", "hardware"],
    "cabinet": ["body", "doors", "legs", "top", "hardware"],
    "shelf": ["frame", "shelves", "back", "hardware"],
}
VARIANTS = {
    "crate": ["经典金属包边", "交叉加固运输箱", "彩漆板式储物箱"],
    "table": ["四腿长桌", "横梁双脚桌", "中央立柱桌"],
    "chair": ["竖条靠背椅", "交叉靠背椅", "板式扶手椅"],
    "sign": ["单柱木牌", "双柱告示牌", "悬臂指示牌"],
    "stool": ["圆面四腿凳", "方凳", "中央立柱圆凳"],
    "bench": ["轻巧板凳", "横梁长凳", "带靠背长凳"],
    "barrel": ["经典四箍木桶", "双箍提手木桶", "彩漆加强桶"],
    "cabinet": ["双门柜", "抽屉柜", "开放展示柜"],
    "shelf": ["竖条背板架", "交叉支撑架", "格子展示架"],
}


def primitives(kind, p, style):
    result = []
    w, d, h = p["width"], p["depth"], p["height"]
    thick = min(w, d) * 0.075
    taper = p.get("taper", style["taper"])
    industrial = style["preset"] == "workshop"
    support = "metal" if industrial else "wood"
    variant = int(p.get("variant", 0))

    def add(part, shape, center, size, material="wood", **extra):
        result.append(
            {
                "part": part,
                "shape": shape,
                "center": list(center),
                "size": list(size),
                "material": material,
                **extra,
            }
        )

    def box(part, center, size, material="wood", **extra):
        add(part, "box", center, size, material, **extra)

    def legs(top, count=4):
        leg = min(w, d) * (0.115 + 0.012 * variant)
        if variant == 1 and kind in {"table", "bench"}:
            for x in (-w * 0.32, w * 0.32):
                box("legs", (x, 0, top / 2), (leg * 1.7, leg * 1.7, top), support)
                box("legs", (x, 0, leg / 2), (leg * 2.4, d * 0.9, leg), support)
            box("frame", (0, 0, top * 0.28), (w * 0.75, leg, leg), support)
            return
        if variant == 2 and kind in {"table", "stool"}:
            add("legs", "cylinder", (0, 0, top / 2), (w * 0.23, d * 0.23, top), support)
            add("frame", "cylinder", (0, 0, leg / 2), (w * 0.68, d * 0.85, leg), support)
            return
        for x in (-w / 2 + leg, w / 2 - leg):
            for y in (-d / 2 + leg, d / 2 - leg):
                add("legs", "taper", (x, y, top / 2), (leg, leg, top), support, taper=taper)
        for y in (-d / 2 + leg, d / 2 - leg):
            box("frame", (0, y, top * 0.3), (w - 2 * leg, leg * 0.5, leg * 0.55), support)
        box("frame", (0, 0, top * 0.3), (leg * 0.5, d - 2.5 * leg, leg * 0.55), support)

    def screws(part, points, radius, axis="y"):
        if p.get("detail", 1) <= 0:
            return
        for point in points:
            add(
                part,
                "cylinder",
                point,
                (radius * 2, radius * 2, radius * 0.5),
                "metal",
                rotation=[math.pi / 2, 0, 0] if axis == "y" else [0, 0, 0],
            )

    if kind == "crate":
        n = int(p["planks"])
        plank = w / n
        for i in range(n):
            x = -w / 2 + (i + 0.5) * plank
            for y in (-d / 2 + thick / 2, d / 2 - thick / 2):
                box("body", (x, y, h / 2), (plank * 0.975, thick, h - thick))
            box("lid", (x, 0, h - thick / 2), (plank * 0.975, d, thick))
        for x in (-w / 2 + thick / 2, w / 2 - thick / 2):
            for i in range(n):
                z = (i + 0.5) * (h - thick) / n
                box("body", (x, 0, z), (thick, d - thick * 2, (h - thick) / n * 0.965))
        box("body", (0, 0, thick / 2), (w, d, thick))
        for x in (-w * (0.29 + variant * 0.04), w * (0.29 + variant * 0.04)):
            for y in (-d / 2 - 0.004, d / 2 + 0.004):
                box("straps", (x, y, h / 2), (w * 0.075, 0.014, h * 0.98), "metal")
            box("straps", (x, 0, h + 0.003), (w * 0.075, d, 0.014), "metal")
        screws(
            "hardware",
            [(x, -d / 2 - 0.014, z) for x in (-w * 0.33, w * 0.33) for z in (h * 0.12, h * 0.85)],
            min(w, h) * 0.015,
        )
    elif kind in {"table", "chair", "stool", "bench"}:
        top = p.get("seat_height", h) if kind == "chair" else h
        thickness = p.get("thickness", min(w, d) * 0.11)
        part = "top" if kind == "table" else "seat"
        if kind == "stool" and variant != 1:
            add(part, "cylinder", (0, 0, top - thickness / 2), (w, d, thickness), "wood")
        else:
            n = 3 + variant if kind in {"table", "bench"} else 2
            for i in range(n):
                box(
                    part,
                    (0, -d / 2 + (i + 0.5) * d / n, top - thickness / 2),
                    (w, d / n - 0.006, thickness),
                )
        legs(top - thickness)
        apron = min(top * 0.14, 0.1)
        for y in (-d * 0.36, d * 0.36):
            box("frame", (0, y, top - thickness - apron / 2), (w * 0.8, thick, apron), support)
        if kind == "chair":
            post = w * 0.085
            for x in (-w * 0.38, w * 0.38):
                box(
                    "backrest",
                    (x, d * 0.37, (top + h - post * 0.5) / 2),
                    (post, post, h - top - post * 0.5),
                )
            n = 3 if variant == 0 else 2 + variant
            for i in range(n):
                x = -w * 0.34 + (i + 0.5) * (w * 0.68 / n)
                box(
                    "backrest",
                    (x, d * 0.37, top + (h - top) * 0.62),
                    (w * 0.68 / n * 0.72, post * 0.58, (h - top) * 0.61),
                    "paint" if style["preset"] == "cozy" else "wood",
                )
            box("backrest", (0, d * 0.37, h - post / 2), (w * 0.9, post * 1.1, post))
            if variant == 1:
                result[:] = [
                    v for v in result if not (v["part"] == "backrest" and v["size"][1] < post)
                ]
                length = math.hypot(w * 0.6, (h - top) * 0.65)
                angle = math.atan2(w * 0.6, (h - top) * 0.65)
                for sign in (-1, 1):
                    box(
                        "backrest",
                        (0, d * 0.37, top + (h - top) * 0.53),
                        (post * 0.7, post * 0.6, length),
                        rotation=[0, sign * angle, 0],
                    )
            elif variant == 2:
                result[:] = [
                    v for v in result if not (v["part"] == "backrest" and v["size"][1] < post)
                ]
                box(
                    "backrest",
                    (0, d * 0.37, top + (h - top) * 0.58),
                    (w * 0.7, post * 0.7, (h - top) * 0.62),
                    "paint",
                )
                for x in (-w * 0.43, w * 0.43):
                    box("frame", (x, 0, top + (h - top) * 0.4), (post, d * 0.87, post), "paint")
                    box(
                        "frame", (x, -d * 0.3, top + (h - top) * 0.2), (post, post, (h - top) * 0.4)
                    )
        elif kind == "bench" and variant == 2:
            for x in (-w * 0.4, w * 0.4):
                box("frame", (x, d * 0.36, h * 1.2), (thick, thick, h * 0.65))
            box("seat", (0, d * 0.36, h * 1.4), (w, thick, h * 0.22), "paint")
        screws(
            "hardware",
            [
                (x, -d * 0.36 - thick / 2 - 0.002, top - thickness - apron / 2)
                for x in (-w * 0.3, w * 0.3)
            ],
            min(w, d) * 0.016,
        )
    elif kind == "sign":
        bh = p["board_height"]
        box("post", (0, 0, (h - bh / 2) / 2), (w * 0.115, d * 0.8, h - bh / 2))
        for i in range(3 + variant):
            box(
                "board",
                (0, 0, h - bh + (i + 0.5) * bh / (3 + variant)),
                (w, d, bh / (3 + variant) * 0.96),
                "paint",
            )
        for x in (-w * 0.4, w * 0.4):
            box("frame", (x, d * 0.55, h - bh / 2), (w * 0.06, d * 0.2, bh * 1.05), support)
        screws(
            "hardware",
            [
                (x, -d * 0.51, z)
                for x in (-w * 0.4, w * 0.4)
                for z in (h - bh * 0.85, h - bh * 0.15)
            ],
            w * 0.013,
        )
    elif kind == "barrel":
        add("body", "barrel", (0, 0, h / 2), (w, d, h * 0.98), "wood", bulge=0.08 + variant * 0.025)
        for z in (h * 0.06, h * 0.24, h * 0.76, h * 0.94):
            bulge = (0.08 + variant * 0.025) * 1.6
            ratio = 1 - bulge + bulge * math.sin(math.pi * z / h)
            add(
                "hoops",
                "ring",
                (0, 0, z),
                (w * ratio + 0.016, d * ratio + 0.016, h * 0.045),
                "metal",
                thickness=0.018,
            )
        add("lid", "cylinder", (0, 0, h * 0.965), (w * 0.84, d * 0.84, h * 0.035))
        add("hardware", "cylinder", (w * 0.19, 0, h * 0.991), (w * 0.095, w * 0.095, 0.016), "wood")
    elif kind == "cabinet":
        foot = h * 0.12
        panel = min(w, d) * 0.09
        for x in (-w / 2 + panel / 2, w / 2 - panel / 2):
            box("body", (x, 0, (h - panel + foot) / 2), (panel, d, h - foot - panel))
        box("body", (0, d / 2 - panel / 2, (h - panel + foot) / 2), (w, panel, h - foot - panel))
        for z in (foot, h * 0.53):
            box("body", (0, 0, z + panel / 2), (w, d, panel))
        box("top", (0, 0, h - panel / 2), (w * 1.035, d * 1.05, panel))
        for x in (-w * 0.25, w * 0.25):
            box(
                "doors",
                (x, -d / 2 - panel * 0.2, (h + foot) / 2),
                (w * 0.475, panel, (h - foot) * 0.94),
                "paint",
            )
            box(
                "doors",
                (x, -d / 2 - panel * 0.78, (h + foot) / 2),
                (w * (0.37 - 0.03 * variant), panel * 0.18, (h - foot) * 0.76),
                "wood" if variant == 1 else "paint",
            )
            add(
                "hardware",
                "cylinder",
                (x * 0.2, -d / 2 - panel * 1.1, h * 0.58),
                (w * 0.035, w * 0.035, panel * 0.65),
                "metal",
                rotation=[math.pi / 2, 0, 0],
            )
        for x in (-w * 0.39, w * 0.39):
            for y in (-d * 0.32, d * 0.32):
                add(
                    "legs",
                    "taper",
                    (x, y, foot / 2),
                    (panel * 1.5, panel * 1.5, foot),
                    support,
                    taper=taper,
                )
    else:  # shelf
        panel = min(w, d) * 0.11
        for x in (-w / 2 + panel / 2, w / 2 - panel / 2):
            box("frame", (x, 0, h / 2), (panel, d, h), support)
        for i in range(int(p["shelves"])):
            z = 0.08 + i * (h - 0.1) / (p["shelves"] - 1)
            box("shelves", (0, 0, z), (w, d, panel))
        for x in [(-0.32 + (i + 0.5) * 0.64 / (2 + variant)) * w for i in range(2 + variant)]:
            box("back", (x, d / 2 - panel / 2, h / 2), (w * 0.1, panel * 0.5, h), "paint")
        screws(
            "hardware",
            [(x, -d / 2, z) for x in (-w * 0.45, w * 0.45) for z in (0.12, h - 0.08)],
            min(w, d) * 0.025,
        )
    # Large structural differences, while retaining the same semantic part vocabulary.
    if kind == "crate" and variant == 1:
        length = math.hypot(w * 0.83, h * 0.78)
        for sign in (-1, 1):
            box(
                "straps",
                (0, -d / 2 - 0.025, h / 2),
                (w * 0.06, 0.025, length),
                "wood",
                rotation=[0, sign * math.atan2(w * 0.83, h * 0.78), 0],
            )
    if kind == "crate" and variant == 2:
        for item in result:
            if item["part"] == "body":
                item["material"] = "paint"
        box("hardware", (0, -d / 2 - 0.025, h * 0.62), (w * 0.28, 0.05, h * 0.065), "metal")
    if kind == "sign" and variant == 1:
        result[:] = [v for v in result if v["part"] != "post"]
        for x in (-w * 0.38, w * 0.38):
            box("post", (x, 0, h / 2), (w * 0.09, d * 0.8, h))
    if kind == "sign" and variant == 2:
        for item in result:
            if item["part"] == "post":
                item["center"][0] = -w * 0.43
        box("frame", (0, 0, h + d * 0.4), (w * 1.05, d, d * 0.6), support)
    if kind == "barrel" and variant == 1:
        result[:] = [
            v for v in result if v["part"] != "hoops" or v["center"][2] in (h * 0.24, h * 0.76)
        ]
        for x in (-w * 0.5, w * 0.5):
            add(
                "hardware",
                "ring",
                (x, 0, h * 0.72),
                (w * 0.26, w * 0.26, w * 0.035),
                "metal",
                thickness=w * 0.035,
                rotation=[math.pi / 2, 0, 0],
            )
    if kind == "barrel" and variant == 2:
        for item in result:
            if item["part"] == "body":
                item["material"] = "paint"
        for x in (-w * 0.26, w * 0.26):
            box("hoops", (x, -d * 0.46, h / 2), (w * 0.065, d * 0.065, h * 0.9), "metal")
    if kind == "cabinet" and variant in {1, 2}:
        result[:] = [v for v in result if v["part"] not in {"doors", "hardware"}]
        if variant == 1:
            for i in range(3):
                z = h * (0.28 + i * 0.28)
                box("doors", (0, -d / 2, z), (w * 0.88, panel, h * 0.25), "paint")
                box("hardware", (0, -d / 2 - panel, z), (w * 0.22, panel, panel * 0.65), "metal")
        else:
            box("doors", (-w * 0.27, -d / 2, h * 0.57), (w * 0.35, panel, h * 0.72), "paint")
            box(
                "hardware",
                (-w * 0.15, -d / 2 - panel, h * 0.57),
                (panel * 0.7, panel, panel * 2),
                "metal",
            )
    if kind == "shelf" and variant == 1:
        result[:] = [v for v in result if v["part"] != "back"]
        for sign in (-1, 1):
            box(
                "back",
                (0, d / 2, h / 2),
                (w * 0.055, panel * 0.6, math.hypot(w * 0.87, h * 0.93)),
                "metal",
                rotation=[0, sign * math.atan2(w * 0.87, h * 0.93), 0],
            )
    if kind == "shelf" and variant == 2:
        box("back", (0, d / 2, h / 2), (w * 0.9, panel * 0.5, h * 0.94), "paint")
        box("shelves", (0, 0, h / 2), (panel, d * 0.94, h * 0.94))
    return result


def plan(recipe):
    p, style = recipe["parameters"], recipe["style"]
    result = primitives(recipe["kind"], p, style)
    # Frozen inputs regenerate exactly the same primitives for locked geometry, even if
    # the shared dimensions or style change. Other parts continue to use current inputs.
    for part, frozen in recipe.get("locks", {}).items():
        if frozen.get("geometry"):
            result = [v for v in result if v["part"] != part] + [
                v
                for v in primitives(recipe["kind"], frozen["parameters"], frozen["style"])
                if v["part"] == part
            ]
    output = []
    for part in PARTS[recipe["kind"]]:
        pieces = [v for v in result if v["part"] == part]
        if not pieces:
            continue
        edits = recipe.get("parts", {}).get(part, {})
        frozen = recipe.get("locks", {}).get(part, {})
        if frozen.get("geometry"):
            edits = {
                **edits,
                **{
                    k: frozen.get("edit", {}).get(k, default)
                    for k, default in (
                        ("scale", [1, 1, 1]),
                        ("offset", [0, 0, 0]),
                        ("rotation", [0, 0, 0]),
                    )
                },
            }
        low = [min(v["center"][i] - v["size"][i] / 2 for v in pieces) for i in range(3)]
        high = [max(v["center"][i] + v["size"][i] / 2 for v in pieces) for i in range(3)]
        pivot = [(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2]]
        for n, v in enumerate(pieces):
            v = copy.deepcopy(v)
            v["name"] = f"PTS_{part}__{n:03d}"
            v["part_pivot"] = pivot
            v["part_scale"] = edits.get("scale", [1, 1, 1])
            v["part_offset"] = edits.get("offset", [0, 0, 0])
            v["part_rotation"] = edits.get("rotation", [0, 0, 0])
            v["roundness"] = (
                frozen.get("style", style)["roundness"]
                if frozen.get("geometry")
                else style["roundness"]
            )
            material_edit = frozen.get("material_edit", {}) if frozen.get("material") else edits
            material_style = (
                frozen.get("material_style", style) if frozen.get("material") else style
            )
            material_parameters = (
                frozen.get("material_parameters", p) if frozen.get("material") else p
            )
            v["quality"] = (
                frozen.get("style", style)["quality"]
                if frozen.get("geometry")
                else style["quality"]
            )
            role = material_edit.get("material", v["material"])
            v["material"] = role
            v["material_name"] = role.title() + (
                "_" + part
                if any(k in material_edit for k in ("color", "material", "roughness", "wear"))
                or frozen.get("material")
                else ""
            )
            v["surface"] = {
                "role": role,
                "color": material_edit.get("color", material_style["palette"][role]),
                "roughness": material_edit.get(
                    "roughness",
                    0.32 if role == "metal" else material_parameters.get("roughness", 0.68),
                ),
                "wear": material_edit.get("wear", material_style["wear"]),
                "seed": int(material_parameters.get("seed", 0)),
                "reuse_path": material_style.get("material_bindings", {}).get(role, ""),
            }
            if v["material_name"] == "Wood" and "color" in material_parameters:
                v["surface"]["color"] = material_parameters["color"]
            if v["material_name"] == "Metal" and "metal_color" in material_parameters:
                v["surface"]["color"] = material_parameters["metal_color"]
            output.append(v)
    return output


def part_hashes(items):
    result = {}
    for part in sorted({v["part"] for v in items}):
        geometry = [
            {k: v for k, v in item.items() if k not in {"material", "material_name", "surface"}}
            for item in items
            if item["part"] == part
        ]
        result[part] = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()
    return result
