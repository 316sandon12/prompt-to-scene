"""Deterministic room/corridor/stair modules with matching ports and walk clearance."""

import math
from collections import deque

from . import core, development, registry

DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def plan(
    engine,
    modules=None,
    cell_size=4,
    story_height=3,
    door_width=1.2,
    door_height=2.3,
    player_radius=0.3,
    player_height=1.8,
    max_step=0.22,
    position=None,
    yaw=0,
):
    cell_size = development.number(cell_size, "Cell size", 3, 10)
    story_height = development.number(story_height, "Story height", 2.6, 5)
    door_width = development.number(door_width, "Door width", 0.5, cell_size - 0.6)
    door_height = development.number(door_height, "Door height", 1, story_height - 0.15)
    player_radius = development.number(player_radius, "Player radius", 0.1, 1)
    player_height = development.number(player_height, "Player height", 0.5, 2.5)
    if player_height < 2 * player_radius:
        raise ValueError("Player capsule height must be at least its diameter")
    max_step = development.number(max_step, "Max step", 0.1, 0.4)
    yaw = development.number(yaw, "Yaw", -360, 360)
    if door_width < 2 * player_radius + 0.15 or door_height < player_height + 0.15:
        raise ValueError("Door clearance is smaller than the player plus 15 cm margin")
    modules = modules or [
        dict(cell=[0, 0, 0], kind="room"),
        dict(cell=[0, 1, 0], kind="corridor", direction=2),
        dict(cell=[0, 2, 0], kind="room"),
    ]
    if not isinstance(modules, list) or not 1 <= len(modules) <= 24:
        raise ValueError("Use one to 24 grid modules")
    origin = core.position_values(position)
    rows, ports, boxes, checks = [], {}, [], []
    angle = math.radians(yaw)

    def vector(p):
        x, y, z = p
        local = [x, z, y] if engine == "unity" else [x, -y, z]
        a, b = (0, 2) if engine == "unity" else (0, 1)
        x, y = local[a], local[b]
        # Unity positive yaw rotates +Z toward +X; Unreal +X toward +Y.
        sign = -1 if engine == "unity" else 1
        local[a] = x * math.cos(angle) - sign * y * math.sin(angle)
        local[b] = sign * x * math.sin(angle) + y * math.cos(angle)
        return [round(v + origin[i], 5) for i, v in enumerate(local)]

    def box(name, center, size, material):
        boxes.append(
            dict(
                name=name,
                position=vector(center),
                size=[size[0], size[2], size[1]] if engine == "unity" else size,
                yaw=yaw,
                material=material,
            )
        )

    for i, item in enumerate(modules):
        cell = item.get("cell")
        if (
            not isinstance(cell, list)
            or len(cell) != 3
            or any(type(n) is not int or abs(n) > 20 for n in cell)
        ):
            raise ValueError(
                "Each cell is [grid_x, grid_y, floor] with integers between -20 and 20"
            )
        if item.get("kind") not in {"room", "corridor", "stair"}:
            raise ValueError("Module kind is room, corridor or stair")
        direction = item.get("direction", 2)
        if type(direction) is not int or direction not in range(4):
            raise ValueError("Direction is 0=south, 1=east, 2=north, 3=west")
        if any(r["cell"] == cell for r in rows):
            raise ValueError("Two modules occupy the same grid cell")
        row = {"cell": cell, "kind": item["kind"], "direction": direction, "index": i}
        rows.append(row)
        x, y, z = cell
        directions = range(4) if row["kind"] == "room" else ((direction + 2) % 4, direction)
        row["ports"] = []
        for side in directions:
            dx, dy = DIRECTIONS[side]
            elevation = z + int(row["kind"] == "stair" and side == direction)
            key = (2 * x + dx, 2 * y + dy, elevation)
            ports.setdefault(key, []).append((i, side))
            row["ports"].append((key, side))
    for a in rows:
        if a["kind"] == "stair" and any(
            b["cell"] == [*a["cell"][:2], a["cell"][2] + 1] for b in rows
        ):
            raise ValueError("A stair's headroom occupies the cell immediately above it")
    graph = {i: [] for i in range(len(rows))}
    connections = []
    for port, members in ports.items():
        if len(members) > 2:
            raise ValueError("Ambiguous module connector")
        if len(members) == 2:
            (a, sa), (b, sb) = members
            if (sa + 2) % 4 != sb:
                raise ValueError("Connector directions do not face each other")
            graph[a].append(b)
            graph[b].append(a)
            connections.append(
                dict(
                    a=a,
                    b=b,
                    position=vector(
                        [port[0] * cell_size / 2, port[1] * cell_size / 2, port[2] * story_height]
                    ),
                )
            )
    reached, queue = {0}, deque([0])
    while queue:
        for n in graph[queue.popleft()]:
            if n not in reached:
                reached.add(n)
                queue.append(n)
    if len(reached) != len(rows):
        raise ValueError("Disconnected modules: " + str(sorted(set(graph) - reached)))

    corridor_width = max(door_width + 0.35, 2 * player_radius + 0.4)
    for row in rows:
        i, (gx, gy, gz), kind = row["index"], row["cell"], row["kind"]
        x, y, z = gx * cell_size, gy * cell_size, gz * story_height
        d = row["direction"]
        sx = sy = cell_size
        if kind in {"corridor", "stair"}:
            if d % 2 == 0:
                sx = corridor_width
            else:
                sy = corridor_width
        if kind != "stair":
            box(f"floor_{i}", [x, y, z - 0.1], [sx, sy, 0.2], "floor")
        else:
            count = math.ceil(story_height / max_step)
            dx, dy = DIRECTIONS[d]
            for step in range(count):
                rise = (step + 1) * story_height / count
                along = -cell_size / 2 + (step + 0.5) * cell_size / count
                size = (
                    [sx, cell_size / count, rise] if d % 2 == 0 else [cell_size / count, sy, rise]
                )
                box(
                    f"stair_{i}_{step}",
                    [x + dx * along, y + dy * along, z + rise / 2],
                    size,
                    "floor",
                )
            # Headroom and player width are checked along every tread in the engine.
            for step in range(count):
                along = -cell_size / 2 + (step + 0.5) * cell_size / count
                checks.append(
                    vector(
                        [
                            x + dx * along,
                            y + dy * along,
                            z + (step + 1) * story_height / count + 0.025,
                        ]
                    )
                )
        for side in range(4):
            dx, dy = DIRECTIONS[side]
            connected = any(s == side and len(ports[key]) == 2 for key, s in row["ports"])
            if kind == "stair" and side in {d, (d + 2) % 4}:
                if not connected:
                    raise ValueError("Both stair ends must connect to a landing/room/corridor")
                continue
            length = sx if dx == 0 else sy
            cx, cy = x + dx * sx / 2, y + dy * sy / 2
            wall_size = [length, 0.15, story_height] if dx == 0 else [0.15, length, story_height]
            if not connected:
                box(f"wall_{i}_{side}", [cx, cy, z + story_height / 2], wall_size, "wall")
            else:
                # Only one shared wall is emitted; the two modules share this port.
                key = next(k for k, s in row["ports"] if s == side)
                if ports[key][0][0] != i:
                    continue
                span = (length - door_width) / 2
                for sign in (-1, 1):
                    center = [
                        cx + (0 if dx else sign * (door_width + span) / 2),
                        cy + (sign * (door_width + span) / 2 if dx else 0),
                        z + story_height / 2,
                    ]
                    size = [0.15, span, story_height] if dx else [span, 0.15, story_height]
                    box(f"doorpost_{i}_{side}_{sign}", center, size, "trim")
                size = (
                    [0.15, door_width, story_height - door_height]
                    if dx
                    else [door_width, 0.15, story_height - door_height]
                )
                box(
                    f"lintel_{i}_{side}",
                    [cx, cy, z + (story_height + door_height) / 2],
                    size,
                    "trim",
                )
        if kind != "stair":
            checks.append(vector([x, y, z + 0.025]))
            for key, side in row["ports"]:
                if len(ports[key]) != 2:
                    continue
                dx, dy = DIRECTIONS[side]
                samples = math.ceil(cell_size / 2 / 0.15)
                for n in range(samples + 1):
                    t = n / samples * cell_size / 2
                    foot = z + 0.025
                    neighbor = next(rows[index] for index, _ in ports[key] if index != i)
                    if n == samples and neighbor["kind"] == "stair" and neighbor["cell"][2] == gz:
                        foot += story_height / math.ceil(story_height / max_step)
                    checks.append(vector([x + dx * t, y + dy * t, foot]))
    return {
        "boxes": boxes,
        "checkpoints": [{"position": p} for p in checks],
        "connections": connections,
        "reachable_modules": sorted(reached),
        "module_count": len(rows),
        "player_radius": player_radius,
        "player_height": player_height,
        "max_step": max_step,
        "modules": modules,
        "validation": "Matched ports and connected graph; native capsule clearance after creation",
    }


def build(project, level_id, mode="build", **settings):
    core.asset_id(level_id)
    if mode not in {"build", "plan", "check", "remove"}:
        raise ValueError("Choose plan, build, check or remove")
    target = registry.resolve(project)
    if mode in {"check", "remove"}:
        return development.request(project, "level", level_id=level_id, mode=mode)
    result = plan(target.engine, **settings)
    if mode == "plan":
        return result
    return development.request(project, "level", level_id=level_id, mode=mode, **result)
