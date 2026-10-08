"""Portable contracts for gameplay, protected updates, scene looks and play checks."""

import json
import math

from . import background, core, registry, workflow

TEMPLATES = {"door", "chest", "pickup", "resource", "switch"}
LOOKS = {"warm_cartoon", "cool_scifi", "moonlit", "neutral"}


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(name + " must be a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return float(value)


def request(project, command, asset_id=None, **values):
    return workflow.action(
        project,
        "develop",
        asset_id=asset_id,
        scope="asset" if asset_id else "selected",
        values={"development_json": json.dumps({"command": command, **values}, allow_nan=False)},
    )


def interactive(project, kind, asset_id, dimensions=None, position=None, color=None):
    if kind not in TEMPLATES:
        raise ValueError("Choose door, chest or pickup")
    core.asset_id(asset_id)
    core.asset_id(asset_id + "_moving")
    defaults = {
        "door": [1.2, 0.14, 2.2],
        "chest": [1.1, 0.7, 0.8],
        "pickup": [0.35] * 3,
        "resource": [1.0, 0.8, 0.7],
        "switch": [0.3, 0.2, 0.4],
    }
    dimensions = dimensions or defaults[kind]
    if len(dimensions) != 3:
        raise ValueError("Dimensions are width, depth, height in meters")
    dimensions = [number(v, "Dimension", 0.1, 10) for v in dimensions]
    color = color or [0.30, 0.14, 0.055]
    if len(color) != 3:
        raise ValueError("Color needs three linear RGB channels")
    color = [number(v, "Color", 0, 1) for v in color]
    if position is not None:
        position = core.position_values(position)
    return background.submit(
        project,
        "interactive",
        dict(kind=kind, asset_id=asset_id, dimensions=dimensions, position=position, color=color),
        asset_id,
    )


def interaction_values(
    asset_id,
    kind,
    moving_asset_id=None,
    angle=90,
    distance=2.5,
    pivot=None,
    moving_offset=None,
    demo_input=True,
    preserve_configuration=False,
    uses=3,
    event_id="",
    label="",
    depleted_asset_id=None,
    interaction_point=None,
):
    if kind not in TEMPLATES:
        raise ValueError("Choose door, chest or pickup")
    core.asset_id(asset_id)
    if kind in {"door", "chest"} and not moving_asset_id:
        raise ValueError("Door/chest needs a separate moving mesh asset")
    if moving_asset_id:
        core.asset_id(moving_asset_id)
        if moving_asset_id == asset_id:
            raise ValueError("The moving part must be a separate asset")
    if type(uses) is not int or not 1 <= uses <= 1000:
        raise ValueError("Uses must be an integer between 1 and 1000")
    if not isinstance(label, str) or len(label) > 120:
        raise ValueError("Use a short interaction label")
    if event_id:
        core.asset_id(event_id)
    if depleted_asset_id:
        core.asset_id(depleted_asset_id)
        if kind != "resource":
            raise ValueError("Depleted-state geometry is only used by resource interactions")
        if depleted_asset_id == asset_id:
            raise ValueError("Choose a separate depleted-state mesh")
    return dict(
        template=kind,
        moving_asset_id=moving_asset_id,
        angle=number(angle, "Open angle", -170, 170),
        distance=number(distance, "Interaction distance", 0.1, 20),
        pivot=core.position_values(pivot),
        offset=core.position_values(moving_offset),
        demo_input=bool(demo_input),
        preserve_configuration=bool(preserve_configuration),
        uses=uses,
        event_id=event_id,
        label=label,
        depleted_asset_id=depleted_asset_id,
        interaction_point=core.position_values(interaction_point),
    )


def configure(
    project,
    asset_id,
    kind,
    moving_asset_id=None,
    angle=90,
    distance=2.5,
    pivot=None,
    moving_offset=None,
    demo_input=True,
    preserve_configuration=False,
    uses=3,
    event_id="",
    label="",
    depleted_asset_id=None,
    interaction_point=None,
):
    """Attach native gameplay hooks; existing game code owns rewards, inventory and quests."""
    values = interaction_values(
        asset_id,
        kind,
        moving_asset_id,
        angle,
        distance,
        pivot,
        moving_offset,
        demo_input,
        preserve_configuration,
        uses,
        event_id,
        label,
        depleted_asset_id,
        interaction_point,
    )
    return request(project, "interaction", asset_id, **values)


def protection(project, asset_id, mode="inspect", bindings=None, sockets=None):
    if mode not in {"inspect", "set", "clear"}:
        raise ValueError("Choose inspect, set or clear")
    core.asset_id(asset_id)
    bindings = bindings or []
    sockets = sockets or []
    if len(bindings) > 64 or len(sockets) > 32:
        raise ValueError("At most 64 material bindings and 32 sockets")
    for row in bindings:
        if set(row) != {"slot", "material_path"} or not all(
            isinstance(v, str) and v for v in row.values()
        ):
            raise ValueError("A binding needs slot and material_path")
    for row in sockets:
        if set(row) - {"name", "position", "rotation"}:
            raise ValueError("Socket supports name, position and rotation")
        core.asset_id(row["name"])
        row["position"] = core.position_values(row.get("position"))
        row["rotation"] = core.position_values(row.get("rotation"))
    if len({r["slot"] for r in bindings}) != len(bindings) or len(
        {r["name"] for r in sockets}
    ) != len(sockets):
        raise ValueError("Binding slots and socket names must be unique")
    return request(project, "protection", asset_id, mode=mode, bindings=bindings, sockets=sockets)


def review_update(project, asset_id, candidate_request_id):
    """Compare a prepared revision's slots against native protected overrides before publishing."""
    root = core.state_root(registry.resolve(project).root)
    path = root / "work" / core.asset_id(asset_id) / workflow.identifier(candidate_request_id)
    envelope = core.read_optional_json(path / "request.json")
    if not envelope or envelope["asset_id"] != asset_id:
        raise ValueError("Choose a finished preview/build request for this asset")
    return request(
        project,
        "update_review",
        asset_id,
        slots=[m["name"] for m in envelope["materials"]],
        object_names=envelope.get("object_names", []),
        candidate_request_id=candidate_request_id,
    )


def look(project, preset="warm_cartoon", mode="apply", position=None):
    if preset not in LOOKS or mode not in {"apply", "restore", "capture", "inspect"}:
        raise ValueError("Unknown scene look or mode")
    return request(
        project, "look", preset=preset, mode=mode, position=core.position_values(position)
    )


def playcheck(project, asset_ids=None, level_id=None, duration=3, capture=True):
    assets = list(dict.fromkeys(asset_ids or []))
    if len(assets) > 16:
        raise ValueError("Check at most 16 interactive assets per run")
    for name in assets:
        core.asset_id(name)
    if level_id:
        core.asset_id(level_id)
    if not assets and not level_id:
        raise ValueError("Choose interactive assets or a generated level to check")
    return request(
        project,
        "playcheck",
        asset_ids=assets,
        level_id=level_id,
        duration=number(duration, "Sample duration", 1, 20),
        capture=bool(capture),
    )


def run_interactive(job, kind, asset_id, dimensions, position, color):
    from .interactive import script

    target = registry.resolve(job.project)
    w, d, h = dimensions

    def vec(x, y, z):
        return [-x, z, -y] if target.engine == "unity" else [-y, -x, z]

    # Verified against imported vertices: Unity(-x,z,-y), UE(-y,-x,z).
    for role in ["base", "moving"] if kind in {"door", "chest"} else ["base"]:
        key = role + "_task"
        if job.state.get(key) and workflow.job_status(job.project, job.state[key]["request_id"])[
            "status"
        ] in {"error", "cancelled"}:
            job.update(**{key: None})
        if not job.state.get(key):
            name = asset_id if role == "base" else asset_id + "_moving"
            job.update(stage="Building " + kind + " " + role)
            task = workflow.submit(
                job.project, name, script(kind, role, dimensions, color), position, False
            )
            job.update(**{key: job.track(task)})
        job.wait(job.state[key])
    pivot = vec(-w / 2, 0, 0) if kind == "door" else vec(0, d / 2, h * 0.8)
    offset = vec(w / 2, 0, 0) if kind == "door" else vec(0, -d / 2, 0)
    if job.state.get("configure_task") and workflow.job_status(
        job.project, job.state["configure_task"]["request_id"]
    )["status"] in {"error", "cancelled"}:
        job.update(configure_task=None)
    if not job.state.get("configure_task"):
        job.update(
            configure_task=job.track(
                configure(
                    job.project,
                    asset_id,
                    kind,
                    asset_id + "_moving" if kind in {"door", "chest"} else None,
                    angle=95 if kind == "chest" else 90,
                    pivot=pivot,
                    moving_offset=offset,
                    preserve_configuration=True,
                )
            )
        )
    result = job.wait(job.state["configure_task"])
    core.atomic_json(
        job.root / "interactions" / (asset_id + ".json"),
        {
            "kind": kind,
            "dimensions": dimensions,
            "color": color,
            "asset_id": asset_id,
            "moving_asset_id": asset_id + "_moving",
            "request_id": job.id,
        },
    )
    return {"stage": "Interactive asset ready", "interaction": result}
