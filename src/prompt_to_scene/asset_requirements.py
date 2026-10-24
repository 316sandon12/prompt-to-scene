"""Per-asset usage requirements, preserved in briefs and checked before placement."""

import json
import uuid
from copy import deepcopy

from . import core, development, game_art, registry, workflow

KINDS = {
    "prop": "场景道具",
    "door": "门",
    "chest": "宝箱",
    "weapon": "持握物品",
    "ui": "游戏界面",
}
DEFAULTS = dict(
    kind="prop",
    min_size_m=[0, 0, 0],
    clearance_m=[0, 0, 0],
    lock_scale=False,
    moving_asset_id="",
    pivot=None,
    axis=None,
    angle=90,
    sockets=[],
    safe_area=[0.1, 0.1, 0.8, 0.8],
    states=["normal"],
    notes="",
)


def save(project, asset_id, settings=None):
    """Read/save usage: engine XYZ metres, moving asset/pivot/axis, sockets and UI safe area.

    min_size_m and clearance_m use engine WORLD axes. Sockets/pivot use engine LOCAL axes.
    Zero means no minimum/extra clearance. States are named image variants to supply, not
    generated automatically. Saving requirements does not change an existing asset.
    """
    from .scene_context import numbers

    path = game_art.root(project) / "usage-requirements" / (core.asset_id(asset_id) + ".json")
    old = core.read_optional_json(path)
    if settings is None:
        return old or {"asset_id": asset_id, "settings": deepcopy(DEFAULTS), "revision": None}
    if not isinstance(settings, dict) or settings.keys() - DEFAULTS.keys():
        raise ValueError("Unknown usage requirement")
    config = {**deepcopy(DEFAULTS), **((old or {}).get("settings") or {}), **settings}
    if not isinstance(config["kind"], str) or config["kind"] not in KINDS:
        raise ValueError("Choose prop, door, chest, weapon or ui")
    if type(config["lock_scale"]) is not bool:
        raise ValueError("lock_scale must be boolean")
    for k in ("min_size_m", "clearance_m"):
        numbers(config[k], 3, 0, 1000, k)
    for k in ("pivot", "axis"):
        if config[k] is not None:
            numbers(config[k], 3, -1000, 1000, k)
    if config["axis"] is not None and sum(v * v for v in config["axis"]) < 0.000001:
        raise ValueError("Movement axis cannot be zero")
    numbers([config["angle"]], 1, -170, 170, "angle")
    config["moving_asset_id"] = game_art.text(config["moving_asset_id"], "moving_asset_id", 64)
    if config["moving_asset_id"]:
        core.asset_id(config["moving_asset_id"])
        if config["moving_asset_id"] == asset_id:
            raise ValueError("Use a separate moving asset")
    config["notes"] = game_art.text(config["notes"], "notes", 1500)
    numbers(config["safe_area"], 4, 0, 1, "safe_area")
    x, y, w, h = config["safe_area"]
    if not w or not h or x + w > 1 or y + h > 1:
        raise ValueError("UI safe area must fit inside the image")
    if not isinstance(config["states"], list) or not 1 <= len(config["states"]) <= 8:
        raise ValueError("Provide one to eight UI states")
    config["states"] = list(dict.fromkeys(core.asset_id(s) for s in config["states"]))
    for state in config["states"]:
        if state != "normal":
            core.asset_id(asset_id + "_" + state)
    if not isinstance(config["sockets"], list) or len(config["sockets"]) > 16:
        raise ValueError("Use at most 16 attachment points")
    names = set()
    for row in config["sockets"]:
        if not isinstance(row, dict) or set(row) != {"name", "position", "rotation"}:
            raise ValueError("Attachment points need name, position and rotation")
        core.asset_id(row["name"])
        if row["name"] in names:
            raise ValueError("Attachment names must be unique")
        names.add(row["name"])
        numbers(row["position"], 3, -1000, 1000, "attachment position")
        numbers(row["rotation"], 3, -360, 360, "attachment rotation")
    result = dict(
        asset_id=asset_id,
        revision=uuid.uuid4().hex,
        settings=config,
        engine=registry.resolve(project).engine,
        updated_utc=workflow.now(),
    )
    core.atomic_json(path, result)
    core.atomic_json(path.parent / "history" / asset_id / (result["revision"] + ".json"), result)
    return result


def guidance(row):
    if not row or not row.get("revision"):
        return ""
    c = row["settings"]
    return "\n".join(
        [
            "Usage requirements: " + json.dumps(c, ensure_ascii=False),
            "WORLD size/clearance and LOCAL pivot/attachment positions use engine axes in metres; "
            "Convert to Blender Z-up. Keep gameplay dimensions when fitting; "
            "ask for a larger space "
            "instead of shrinking below the minimum. Keep model, icon "
            "and state variants consistent.",
            "For doors/chests build the moving panel/lid as a SEPARATE managed asset with its own "
            "pivot; configure interaction only after both assets import. "
            "Preserve opening clearance.",
            "For UI keep localized text inside safe_area, preserve nine-slice corners and prepare "
            "every named state. A decorative grip or hinge alone does not implement interaction.",
        ]
    )


def validate_placement(row, placed, scene, ignored, scale_factor):
    from . import layout

    if not row or not row.get("revision"):
        return
    c = row["settings"]
    if c["lock_scale"] and abs(scale_factor - 1) > 0.00001:
        raise ValueError("Scale is locked for this asset; choose a larger target")
    size = [b - a for a, b in zip(placed["bounds_min"], placed["bounds_max"])]
    if any(size[i] + 0.002 < c["min_size_m"][i] for i in range(3)):
        raise ValueError(
            "Placement would violate the gameplay minimum size; choose a larger target"
        )
    if any(c["clearance_m"]):
        volume = {
            "bounds_min": [v - c["clearance_m"][i] for i, v in enumerate(placed["bounds_min"])],
            "bounds_max": [v + c["clearance_m"][i] for i, v in enumerate(placed["bounds_max"])],
        }
        for obstacle in scene["context"]:
            if obstacle["id"] not in ignored and layout.overlaps(volume, obstacle):
                raise ValueError("Reserved interaction space overlaps " + obstacle["name"])


def apply(project, asset_id):
    """Install the saved moving-part interaction, or weapon attachment points, after import.

    This uses existing native interaction/protection operations. Play the actual game to verify
    motion and input; a declared clearance box is not a swept collision or navigation test.
    """
    row = save(project, asset_id)
    c = row["settings"]
    if workflow.inspect_asset(project, asset_id)["current"].get("status") != "imported":
        raise ValueError("Import the asset first")
    if c["kind"] in {"door", "chest"}:
        if not c["moving_asset_id"] or c["pivot"] is None or c["axis"] is None:
            raise ValueError("Set the separate moving asset, local pivot and movement axis first")
        if (
            workflow.inspect_asset(project, c["moving_asset_id"])["current"].get("status")
            != "imported"
        ):
            raise ValueError("Import the separate moving asset first")
        axes = {
            "unity": {"door": [0, 1, 0], "chest": [-1, 0, 0]},
            "unreal": {"door": [0, 0, 1], "chest": [0, 1, 0]},
        }
        if c["axis"] != axes[row["engine"]][c["kind"]]:
            raise ValueError(
                "This interaction template uses local axis " + str(axes[row["engine"]][c["kind"]])
            )
        return development.configure(
            project,
            asset_id,
            c["kind"],
            moving_asset_id=c["moving_asset_id"],
            pivot=c["pivot"],
            angle=c["angle"],
            demo_input=False,
        )
    if c["kind"] == "weapon" and c["sockets"]:
        # Native 'set' updates named entries; other sockets/material bindings remain intact.
        return development.protection(project, asset_id, mode="set", sockets=c["sockets"])
    return {
        "status": "requirements_saved",
        "requirements": row,
        "message": "Use these requirements in the next model/image plan; review at game size",
    }
