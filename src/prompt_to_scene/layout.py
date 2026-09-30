"""Conservative, engine-coordinate layout planning from actual editor bounds."""

import math
from copy import deepcopy


def overlaps(a, b, epsilon=0.005):
    if not all(
        min(a["bounds_max"][i], b["bounds_max"][i]) - max(a["bounds_min"][i], b["bounds_min"][i])
        > epsilon
        for i in range(3)
    ):
        return False
    if not a.get("footprint") or not b.get("footprint"):
        return True
    pa, pb = [list(zip(o["footprint"][::2], o["footprint"][1::2])) for o in (a, b)]
    for polygon in (pa, pb):
        for p, q in zip(polygon, polygon[1:] + polygon[:1]):
            normal = (p[1] - q[1], q[0] - p[0])
            length = math.hypot(*normal)
            if length < 1e-8:
                continue
            projections = [
                [sum(v * n for v, n in zip(corner, normal)) / length for corner in poly]
                for poly in (pa, pb)
            ]
            if min(map(max, projections)) - max(map(min, projections)) <= epsilon:
                return False
    return True


def yaw(obj, engine):
    up = 1 if engine == "unity" else 2
    if any(abs((v + 180) % 360 - 180) > 0.1 for i, v in enumerate(obj["rotation"]) if i != up):
        raise ValueError("Layout supports upright objects; remove pitch/roll first")
    return obj["rotation"][up]


def rotate(vector, degrees, engine):
    up = 1 if engine == "unity" else 2
    a, b = [i for i in range(3) if i != up]
    angle = math.radians(degrees * (-1 if engine == "unity" else 1))
    c, s = math.cos(angle), math.sin(angle)
    result = list(vector)
    result[a], result[b] = c * vector[a] - s * vector[b], s * vector[a] + c * vector[b]
    return result


def pose(obj, position, rotation, scale, engine):
    """Use native oriented bounds when available, retaining the original pivot offset."""
    old_yaw = yaw(obj, engine)
    local_low, local_high = obj.get("oriented_min"), obj.get("oriented_max")
    if local_low is None:
        # Older bridges supply a conservative world box. No guessed mesh geometry.
        corners = [
            rotate([v[i] - obj["position"][i] for i in range(3)], -old_yaw, engine)
            for v in box_corners(obj["bounds_min"], obj["bounds_max"])
        ]
        local_low = [min(v[i] for v in corners) for i in range(3)]
        local_high = [max(v[i] for v in corners) for i in range(3)]
    factors = [scale[i] / obj["scale"][i] for i in range(3)]
    low, high = [[v[i] * factors[i] for i in range(3)] for v in (local_low, local_high)]
    angle = rotation[1 if engine == "unity" else 2]
    corners = [
        [p[i] + position[i] for i in range(3)]
        for p in [rotate(v, angle, engine) for v in box_corners(low, high)]
    ]
    up = 1 if engine == "unity" else 2
    a, b = [i for i in range(3) if i != up]
    footprint = []
    for x, y in ((low[a], low[b]), (high[a], low[b]), (high[a], high[b]), (low[a], high[b])):
        p = [0, 0, 0]
        p[a], p[b] = x, y
        p = rotate(p, angle, engine)
        footprint += [p[a] + position[a], p[b] + position[b]]
    return {
        **deepcopy(obj),
        "position": list(position),
        "rotation": list(rotation),
        "scale": list(scale),
        "oriented_min": low,
        "oriented_max": high,
        "bounds_min": [min(v[i] for v in corners) for i in range(3)],
        "bounds_max": [max(v[i] for v in corners) for i in range(3)],
        "footprint": footprint,
    }


def box_corners(low, high):
    return [[(high if n & (1 << i) else low)[i] for i in range(3)] for n in range(8)]


def placement(obj, placed, duplicate=False):
    return {
        **{
            k: placed[k]
            for k in ("position", "rotation", "scale", "bounds_min", "bounds_max", "footprint")
        },
        "source_id": obj["id"],
        "asset_id": obj["asset_id"],
        "duplicate": duplicate,
        "expected": {
            k: obj[k] for k in ("id", "position", "rotation", "scale", "bounds_min", "bounds_max")
        },
    }


def plan(
    scene,
    items,
    relation="around",
    anchor_id=None,
    gap=0.12,
    fit=False,
    clearance=None,
    face_anchor=False,
):
    engine = scene.get("engine", "unity")
    context = scene.get("context", []) + scene.get("selected_context", [])
    if anchor_id is None and len(scene.get("selected_context", [])) == 1:
        anchor_id = scene["selected_context"][0]["id"]
    anchor = next((o for o in context if o["id"] == anchor_id), None)
    if not anchor:
        raise ValueError("Select one anchor object in the editor, or specify anchor_id")
    angle = yaw(anchor, engine)
    up = 1 if engine == "unity" else 2
    local = deepcopy(scene)
    originals = {o["id"]: o for o in context + scene.get("assets", [])}
    for key in ("context", "selected_context", "assets", "selected"):
        local[key] = []
        for obj in scene.get(key, []):
            rotation = list(obj["rotation"])
            rotation[up] -= angle
            local[key].append(
                pose(obj, rotate(obj["position"], -angle, engine), rotation, obj["scale"], engine)
            )
    planned = _axis_plan(local, items, relation, anchor_id, gap, fit, clearance)
    rows = []
    for row in planned["placements"]:
        obj = originals[row["source_id"]]
        position = rotate(row["position"], angle, engine)
        rotation = list(obj["rotation"])
        if face_anchor and relation == "around":
            delta = [anchor["position"][i] - position[i] for i in range(3)]
            rotation[up] = (
                math.degrees(math.atan2(delta[0], delta[2]))
                if engine == "unity"
                else math.degrees(math.atan2(delta[1], delta[0]))
            )
        placed = pose(obj, position, rotation, row["scale"], engine)
        rows.append(placement(obj, placed, row["duplicate"]))
    check_placements(scene, rows, anchor_id)
    return {
        **planned,
        "anchor": anchor,
        "placements": rows,
        "message": "Upright oriented layout; native editor rechecks scene state before applying",
    }


def check_placements(scene, rows, anchor_id):
    moved = {r["source_id"] for r in rows if not r["duplicate"]}
    for i, row in enumerate(rows):
        for other in rows[:i]:
            if overlaps(row, other):
                raise ValueError("Planned instances overlap; increase spacing")
        for obstacle in scene.get("context", []):
            if obstacle["id"] not in moved | {anchor_id} and overlaps(row, obstacle):
                raise ValueError(
                    "Layout would overlap " + obstacle["name"] + "; choose a clearer area"
                )


def _axis_plan(
    scene, items, relation="around", anchor_id=None, gap=0.12, fit=False, clearance=None
):
    if relation not in {"around", "along", "under", "right", "front"}:
        raise ValueError("Relation must be around, along, under, right or front")
    if not isinstance(gap, (int, float)) or not math.isfinite(gap) or not 0 <= gap <= 10:
        raise ValueError("Gap must be from 0 to 10 meters")
    if not isinstance(items, list) or not 1 <= len(items) <= 8:
        raise ValueError("Provide one to eight asset groups")
    context = scene.get("context", [])
    selected = scene.get("selected_context", [])
    if anchor_id is None:
        if len(selected) != 1:
            raise ValueError("Select one anchor object in the editor, or specify anchor_id")
        anchor_id = selected[0]["id"]
    anchor = next((o for o in context + selected if o["id"] == anchor_id), None)
    if not anchor:
        raise ValueError("Anchor is no longer loaded")
    if any(abs(a % 90) > 0.1 and abs(a % 90 - 90) > 0.1 for a in anchor.get("rotation", [])):
        raise ValueError(
            "This layout uses axis-aligned bounds; align the anchor to 90-degree axes first"
        )
    up = 1 if scene.get("engine") == "unity" else 2
    axes = [i for i in range(3) if i != up]
    x, y = axes
    low, high = anchor["bounds_min"], anchor["bounds_max"]
    center = [(a + b) / 2 for a, b in zip(low, high)]
    sizes = [b - a for a, b in zip(low, high)]
    entries, touched = [], set()
    for item in items:
        if not isinstance(item, dict) or set(item) - {"asset_id", "count", "object_id"}:
            raise ValueError("Each group needs asset_id and optional count/object_id")
        count = item.get("count", 1)
        if type(count) is not int or not 1 <= count <= 16:
            raise ValueError("Count must be from 1 to 16")
        matches = [
            o
            for o in scene.get("assets", [])
            if o["asset_id"] == item.get("asset_id") and o["id"] != anchor_id
        ]
        if item.get("object_id"):
            matches = [o for o in matches if o["id"] == item["object_id"]]
        if not matches:
            raise ValueError(
                "Import a source instance before arranging: " + str(item.get("asset_id"))
            )
        if item.get("asset_id") in touched:
            raise ValueError("Use one group per asset")
        touched.add(item["asset_id"])
        for i in range(count):
            source = matches[i] if i < len(matches) else matches[0]
            entries.append({"source": source, "duplicate": i >= len(matches)})
    if len(entries) > 32:
        raise ValueError("A layout is limited to 32 instances")
    total = len(entries)
    placed = []
    for index, entry in enumerate(entries):
        obj = entry["source"]
        extent = [b - a for a, b in zip(obj["bounds_min"], obj["bounds_max"])]
        factor = 1
        if relation == "under" and fit:
            available = [max(0.001, s - 2 * gap) for s in sizes]
            available[up] = (
                clearance if clearance is not None else max(0.001, sizes[up] * 0.65 - gap)
            )
            factor = min(
                1,
                max(0.001, available[x] - gap * (total - 1)) / max(extent[x] * total, 0.001),
                available[y] / max(extent[y], 0.001),
                available[up] / max(extent[up], 0.001),
            )
        extent = [v * factor for v in extent]
        target_center = center.copy()
        target_center[up] = low[up] + extent[up] / 2
        if relation == "around":
            side = index % 4
            count_side = (total - side + 3) // 4
            rank = index // 4
            axis, other = (y, x) if side < 2 else (x, y)
            sign = -1 if side in (0, 2) else 1
            target_center[axis] += sign * (sizes[axis] / 2 + gap + extent[axis] / 2)
            target_center[other] += (rank - (count_side - 1) / 2) * (extent[other] + gap)
        elif relation == "under":
            target_center[x] += (index - (total - 1) / 2) * (extent[x] + gap)
            available_height = clearance if clearance is not None else sizes[up] * 0.65
            if (
                extent[up] > available_height + 0.005
                or extent[y] + 2 * gap > sizes[y]
                or total * extent[x] + (total - 1) * gap + 2 * gap > sizes[x]
            ):
                raise ValueError(
                    "Objects do not fit under the anchor; enable fit or reduce count/gap"
                )
        elif relation == "right":
            target_center[x] += sizes[x] / 2 + gap + extent[x] / 2
            target_center[y] += (index - (total - 1) / 2) * (extent[y] + gap)
        else:
            target_center[y] -= sizes[y] / 2 + gap + extent[y] / 2
            target_center[x] += (index - (total - 1) / 2) * (extent[x] + gap)
        old_center = [(a + b) / 2 for a, b in zip(obj["bounds_min"], obj["bounds_max"])]
        position = [
            target_center[i] - (old_center[i] - obj["position"][i]) * factor for i in range(3)
        ]
        row = {
            "source_id": obj["id"],
            "asset_id": obj["asset_id"],
            "duplicate": entry["duplicate"],
            "position": position,
            "rotation": obj["rotation"],
            "scale": [v * factor for v in obj["scale"]],
            "bounds_min": [target_center[i] - extent[i] / 2 for i in range(3)],
            "bounds_max": [target_center[i] + extent[i] / 2 for i in range(3)],
            "expected": {
                k: obj[k]
                for k in ("id", "position", "rotation", "scale", "bounds_min", "bounds_max")
            },
        }
        if any(overlaps(row, other) for other in placed):
            raise ValueError("Planned instances overlap; increase spacing or reduce count")
        placed.append(row)
    moved = {row["source_id"] for row in placed if not row["duplicate"]}
    obstacles = [o for o in context if o["id"] not in moved | {anchor_id}]
    for row in placed:
        for obstacle in obstacles:
            if overlaps(row, obstacle):
                raise ValueError(
                    "Layout would overlap " + obstacle["name"] + "; choose a clearer area"
                )
    return {
        "scene": scene["scene"],
        "anchor_id": anchor_id,
        "anchor": anchor,
        "placements": placed,
        "relation": relation,
        "gap": gap,
        "message": (
            "Layout uses world-axis bounds; "
            "inspect the result for intentional architectural overlaps"
        ),
    }
