"""Conservative, engine-coordinate layout planning from actual editor bounds."""

import math


def overlaps(a, b, epsilon=0.005):
    return all(
        min(a["bounds_max"][i], b["bounds_max"][i]) - max(a["bounds_min"][i], b["bounds_min"][i])
        > epsilon
        for i in range(3)
    )


def plan(scene, items, relation="around", anchor_id=None, gap=0.12, fit=False, clearance=None):
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
