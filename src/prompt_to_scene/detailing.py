"""Bounded construction details for recipe props; custom designs still use host-authored bpy."""

import math


def apply(kind, items, p, treatment):
    if not treatment:
        return items
    craft, detail = treatment["construction"], treatment["detail"]
    close = detail == "closeup" and p.get("detail", 1)
    small = detail != "readable" and p.get("detail", 1)
    focus = 1.25 if treatment.get("emphasize_hardware") else 1
    w, d, h = (p[k] for k in ("width", "depth", "height"))

    def add(part, center, size, material="wood", shape="box", **values):
        items.append(
            dict(
                part=part,
                center=list(center),
                size=list(size),
                material=material,
                shape=shape,
                **values,
            )
        )

    def frame(part, x, y, z, width, height, rail, material="wood"):
        for side in (-1, 1):
            add(part, (x + side * (width - rail) / 2, y, z), (rail, rail * 0.65, height), material)
            add(
                part,
                (x, y, z + side * (height - rail) / 2),
                (width - rail * 2, rail * 0.65, rail),
                material,
            )

    def rivet(part, x, y, z, radius):
        add(
            part,
            (x, y, z),
            (radius * 2, radius * 2, radius * 0.55),
            "metal",
            "cylinder",
            rotation=[math.pi / 2, 0, 0],
        )

    # Details belong to their functional semantic group, so edits and locks include them.
    if kind == "cabinet":
        panel, foot = min(w, d) * 0.09, h * 0.12
        for item in items:
            if item["part"] == "body" and item["size"][2] == panel:
                # Internal shelves stop inside the side boards, avoiding coincident outer faces.
                item["size"][0] = w - panel * 2
                item["size"][1] = d - panel * 2
        # Keep the door slabs; replace the old floating overlay and knobs with real framing.
        items[:] = [
            i
            for i in items
            if not (
                i["part"] == "hardware" or (i["part"] == "doors" and i["size"][1] < panel * 0.5)
            )
        ]
        for z, scale in ((foot, 1.02), (h + panel * 0.25, 1.06)):
            add("top" if z > h else "body", (0, 0, z), (w * scale, d * scale, panel * 0.65))
        if craft == "handcrafted":
            # A shaped crown changes the silhouette without using ornaments everywhere.
            add(
                "top",
                (0, d * 0.37, h + h * 0.045),
                (w * 0.78, panel, h * 0.16),
                "wood",
                "profile",
                profile=[
                    [-0.5, -0.5],
                    [0.5, -0.5],
                    [0.5, -0.12],
                    [0.36, -0.08],
                    [0.22, 0.23],
                    [0, 0.5],
                    [-0.22, 0.23],
                    [-0.36, -0.08],
                    [-0.5, -0.12],
                ],
            )
        variant = int(p.get("variant", 0))
        if variant == 0:
            for side in (-1, 1):
                x, z = side * w * 0.25, (h + foot) / 2
                y = -d / 2 - panel * 0.73
                frame(
                    "doors",
                    x,
                    y,
                    z,
                    w * 0.43,
                    (h - foot) * 0.87,
                    w * 0.035,
                    "metal" if craft == "machined" else "wood",
                )
                # An inset face is bounded by stiles/rails, with quiet color at the center.
                add(
                    "doors",
                    (x, y + panel * 0.14, z),
                    (w * 0.34, panel * 0.18, (h - foot) * 0.72),
                    "paint",
                )
                hx, hz = side * w * 0.065, h * 0.58
                add(
                    "hardware",
                    (hx, y - panel * 0.48, hz),
                    (w * 0.05 * focus, panel * 0.32, h * 0.08 * focus),
                    "metal",
                )
                if craft == "handcrafted":
                    add(
                        "hardware",
                        (hx, y - panel * 1.05, hz - h * 0.022),
                        (w * 0.061 * focus, h * 0.057 * focus, panel * 0.34),
                        "metal",
                        "ring",
                        thickness=w * 0.008,
                        rotation=[math.pi / 2, 0, 0],
                    )
                    rivet("hardware", hx, y - panel * 1.03, hz + h * 0.005, w * 0.012)
                else:
                    for dz in (-h * 0.027, h * 0.027):
                        add(
                            "hardware",
                            (hx, y - panel * 0.8, hz + dz),
                            (w * 0.019, panel * 0.9, h * 0.014),
                            "metal",
                        )
                    add(
                        "hardware",
                        (hx, y - panel * 1.4, hz),
                        (w * 0.022 * focus, panel * 0.45, h * 0.07 * focus),
                        "metal",
                    )
                if small:
                    for hinge in (h * 0.29, h * 0.85):
                        add(
                            "hardware",
                            (side * w * 0.436, y - panel * 0.38, hinge),
                            (w * 0.085, panel * 0.28, h * 0.031),
                            "metal",
                        )
                        rivet("hardware", side * w * 0.46, y - panel * 0.55, hinge, w * 0.007)
                if craft == "machined" and small:
                    for i in range(4 if close else 3):
                        add(
                            "doors",
                            (x, y - panel * 0.04, h * (0.28 + i * 0.036)),
                            (w * 0.22, panel * 0.24, h * 0.01),
                            "metal",
                        )
                if craft == "salvaged":
                    add(
                        "doors",
                        (x, y - panel * 0.7, h * 0.35),
                        (w * 0.31, panel * 0.35, h * 0.052),
                        "wood",
                        rotation=[0, side * 0.1, 0],
                    )
                if close and craft == "handcrafted":
                    add(
                        "doors",
                        (x, y - panel * 0.04, h * 0.69),
                        (w * 0.07, panel * 0.28, h * 0.07),
                        "wood",
                        "profile",
                        profile=[[0, -0.5], [0.5, 0], [0, 0.5], [-0.5, 0]],
                    )
        else:
            for slab in [i for i in items if i["part"] == "doors" and i["size"][1] >= panel * 0.5]:
                x, y, z = slab["center"]
                sw, _, sh = slab["size"]
                frame("doors", x, y - panel * 0.55, z, sw * 0.93, sh * 0.91, min(sw, sh) * 0.065)
                add(
                    "hardware",
                    (x, y - panel * 1.2, z),
                    (sw * 0.24, panel * 0.85, sh * 0.07),
                    "metal",
                )
        if close:
            for side in (-1, 1):
                # Side panel edging follows the same joinery, facing outward on each side.
                for y in (-d * 0.38, d * 0.38):
                    add(
                        "body",
                        (side * (w / 2 + panel * 0.06), y, h * 0.57),
                        (panel * 0.15, d * 0.045, h * 0.68),
                    )
                for z in (h * 0.23, h * 0.91):
                    add(
                        "body",
                        (side * (w / 2 + panel * 0.06), 0, z),
                        (panel * 0.15, d * 0.715, h * 0.025),
                    )
    elif kind == "chair":
        post, seat = w * 0.085, p["seat_height"]
        if craft == "handcrafted":
            items[:] = [
                i
                for i in items
                if not (i["part"] == "backrest" and abs(i["center"][2] - (h - post / 2)) < 0.00001)
            ]
            add(
                "backrest",
                (0, d * 0.37, h - post * 0.3),
                (w * 0.94, post * 1.3, post * 2.2),
                "wood",
                "profile",
                profile=[
                    [-0.5, -0.5],
                    [0.5, -0.5],
                    [0.5, 0.12],
                    [0.25, 0.35],
                    [0, 0.5],
                    [-0.25, 0.35],
                    [-0.5, 0.12],
                ],
            )
        # Joinery connecting the back to the seat; the old slats otherwise feel pasted on.
        add(
            "backrest",
            (0, d * 0.37, seat + (h - seat) * 0.28),
            (w * 0.76, post * 0.9, post * 0.8),
            "metal" if craft == "machined" else "wood",
        )
    elif kind in {"table", "bench", "shelf"}:
        part = "top" if kind == "table" else "seat" if kind == "bench" else "shelves"
        horizontal = [i for i in items if i["part"] == part and i["size"][2] < h * 0.3]
        for z in sorted({round(i["center"][2], 6) for i in horizontal}):
            add(
                part,
                (0, -d * 0.485, z),
                (w * 0.98, d * 0.028, min(d * 0.07, h * 0.035)),
                "metal" if craft == "machined" else "wood",
            )
    elif kind == "crate":
        for side in (-1, 1):
            add(
                "straps",
                (side * w * 0.44, -d / 2 - 0.012, h * 0.075),
                (w * 0.095, 0.025, h * 0.15),
                "metal",
            )
        add("hardware", (0, -d / 2 - 0.025, h * 0.84), (w * 0.14, 0.03, h * 0.13), "metal")
        if small:
            add("hardware", (0, -d / 2 - 0.045, h * 0.8), (w * 0.06, 0.032, h * 0.08), "paint")
    elif kind == "sign":
        bh = p["board_height"]
        frame(
            "board",
            0,
            -d * 0.53,
            h - bh / 2,
            w * 1.02,
            bh * 1.03,
            min(w, bh) * 0.055,
            "metal" if craft == "machined" else "wood",
        )
    elif kind == "barrel" and small:
        for angle in (-2.35, -1.57, -0.78):
            for z in (h * 0.24, h * 0.76):
                rivet(
                    "hardware",
                    math.cos(angle) * w * 0.475,
                    math.sin(angle) * d * 0.48,
                    z,
                    w * 0.012,
                )

    if craft == "handcrafted" and kind in {"chair", "cabinet", "stool", "table", "bench"}:
        for item in items:
            if item["part"] == "legs" and item["shape"] == "taper":
                item["shape"] = "spindle"
    elif craft == "machined":
        for item in items:
            if item["part"] in {"legs", "frame", "body", "post"}:
                item["material"] = "metal"
    return items
