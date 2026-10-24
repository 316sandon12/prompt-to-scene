"""Camera reference and temporary static-mesh placement, with guarded adopt/undo."""

import json
import math
import re

import unreal

from . import actions, layout
from .protocol import write_json


def objects():
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).get_current_level()
    return {
        actions.guid(a): a
        for a in actions.actors().get_all_level_actors()
        if isinstance(a, unreal.StaticMeshActor) and a.get_level() == level
    }


def same(actual, expected):
    return all(
        layout.near(actual[k], expected.get(k))
        for k in ("position", "rotation", "scale", "bounds_min", "bounds_max")
    ) and actual.get("materials") == expected.get("materials")


def validate(plan, root, undo=False):
    if plan["scene"] != actions.scene():
        raise ValueError("Level changed; capture the target again")
    receipt = root / "receipts" / (plan["asset_id"] + ".json")
    if (
        not receipt.exists()
        or json.loads(receipt.read_text())["request_id"] != plan["model_revision"]
    ):
        raise ValueError("Model revision changed; prepare another preview")
    current = objects()
    if undo:
        return current
    for key in ("source", "target"):
        actor = current.get(plan[key]["id"])
        if not actor or not same(actions.describe(actor), plan[key]):
            raise ValueError("Target or model changed; prepare another preview")
    if plan["camera"] not in actions.cameras():
        raise ValueError("Camera changed; prepare another preview")
    for key, actor in current.items():
        if not actions.describe(actor)["has_collision"]:
            continue
        if (
            key not in {plan["source"]["id"], plan["target"]["id"]}
            and not actor.is_temporarily_hidden_in_editor()
        ):
            if layout.overlap(plan["placement"], actions.describe(actor)):
                raise ValueError("Placement overlaps " + actor.get_actor_label())
            margin = plan.get("clearance_m", [0, 0, 0])
            if any(margin):
                reserved = {
                    "bounds_min": [
                        v - margin[i] for i, v in enumerate(plan["placement"]["bounds_min"])
                    ],
                    "bounds_max": [
                        v + margin[i] for i, v in enumerate(plan["placement"]["bounds_max"])
                    ],
                }
                if layout.overlap(reserved, actions.describe(actor)):
                    raise ValueError(
                        "Reserved interaction space overlaps " + actor.get_actor_label()
                    )
    return current


def pose(actor, row):
    actor.set_actor_location(unreal.Vector(*(v * 100 for v in row["position"])), False, False)
    actor.set_actor_rotation(
        unreal.Rotator(roll=row["rotation"][0], pitch=row["rotation"][1], yaw=row["rotation"][2]),
        False,
    )
    actor.set_actor_scale3d(unreal.Vector(*row["scale"]))


def visibility(actor):
    return {
        "editor": actor.is_temporarily_hidden_in_editor(),
        "game": bool(actor.get_editor_property("hidden")),
        "collision": actor.get_actor_enable_collision(),
    }


def restore_visibility(actor, state):
    actor.set_is_temporarily_hidden_in_editor(state["editor"])
    actor.set_actor_hidden_in_game(state["game"])
    actor.set_actor_enable_collision(state["collision"])


def execute(request, root):
    plan = json.loads(request["scene_json"])
    mode, revision = plan["mode"], request["request_id"]
    result = {"scene": actions.scene()}
    if mode == "reference":
        result = actions.execute({**request, "operation": "inspect"}, root)
        cameras = result["cameras"]
        choices = [c for c in cameras if c["primary"]] or cameras
        chosen = plan.get("camera_id") or (choices[0]["id"] if len(choices) == 1 else "")
        if not chosen:
            raise ValueError("Choose one game camera before capturing the scene")
        plan["camera_id"] = chosen
        result["reference_camera_id"] = chosen
        from .adaptation import material_values

        result["materials"] = []
        nearby = {o["id"]: o for o in [*result["context"], *result["selected_context"]]}
        center = (result["selected_context"] or [c for c in cameras if c["id"] == chosen])[0][
            "position"
        ]
        for o in sorted(nearby.values(), key=lambda o: math.dist(o["position"], center))[:40]:
            for path in o["materials"][:8]:
                material = unreal.load_asset(path) if path else None
                values = material_values(material) if material else {}
                result["materials"].append(
                    {"object_id": o["id"], "path": path, "parameters": values}
                )
    else:
        if not re.fullmatch(r"[a-f0-9]{32}", plan.get("plan_id", "")):
            raise ValueError("Invalid preview ID")
        journal_path = root / "native-scene-trials" / (plan["plan_id"] + ".json")
        if mode == "undo":
            journal = json.loads(journal_path.read_text())
            current = validate(journal["plan"], root, undo=True)
            if journal.get("undone"):
                return result
            original = current.get(journal["after"]["id"])
            anchor = current.get(journal["plan"]["target"]["id"])
            if (
                not original
                or not anchor
                or not same(actions.describe(original), journal["after"])
                or (
                    journal["plan"]["replace_target"]
                    and visibility(anchor) != journal["target_after"]
                )
            ):
                raise ValueError("Objects changed after adoption; undo was not applied")
            with unreal.ScopedEditorTransaction("Restore scene placement"):
                original.modify()
                pose(original, journal["plan"]["source"])
                if journal["plan"]["replace_target"]:
                    anchor.modify()
                    restore_visibility(anchor, journal["target_before"])
            journal["undone"] = True
            write_json(journal_path, journal)
            return {**result, "changed": 1}
        if mode == "adopt" and journal_path.exists():
            journal = json.loads(journal_path.read_text())
            if journal.get("undone"):
                raise ValueError("This preview was undone; prepare a new one")
            return {**result, "scene_trial_id": plan["plan_id"]}
        current = validate(plan, root)
        original, anchor = (current[plan[k]["id"]] for k in ("source", "target"))
        if mode == "adopt":
            before = visibility(anchor)
            layout.arrange(
                {
                    **request,
                    "scene": plan["scene"],
                    "anchor": plan["target"],
                    "placements": [plan["placement"]],
                    "ignore_noncolliding": True,
                },
                root,
            )
            if plan["replace_target"]:
                anchor.modify()
                restore_visibility(anchor, {"editor": True, "game": True, "collision": False})
            write_json(
                journal_path,
                {
                    "plan": plan,
                    "after": actions.describe(original),
                    "target_before": before,
                    "target_after": visibility(anchor),
                },
            )
            return {**result, "scene_trial_id": plan["plan_id"], "changed": 1}
        if mode not in {"before", "trial"}:
            raise ValueError("Unknown scene operation")
    selection = list(actions.actors().get_selected_level_actors())
    temporary, hidden = [], []

    def cleanup():
        for actor, state in hidden:
            restore_visibility(actor, state)
        for actor in temporary:
            actions.actors().destroy_actor(actor)
        actions.actors().set_selected_level_actors(selection)

    try:
        if mode == "trial":
            clone = actions.actors().spawn_actor_from_class(
                unreal.StaticMeshActor, original.get_actor_location(), transient=True
            )
            temporary.append(clone)
            clone.static_mesh_component.set_static_mesh(original.static_mesh_component.static_mesh)
            for i in range(original.static_mesh_component.get_num_materials()):
                clone.static_mesh_component.set_material(
                    i, original.static_mesh_component.get_material(i)
                )
            pose(clone, plan["placement"])
            for actor in [original] + ([anchor] if plan["replace_target"] else []):
                hidden.append((actor, visibility(actor)))
                actor.set_is_temporarily_hidden_in_editor(True)
                actor.set_actor_hidden_in_game(True)
        actions.execute(
            {
                **request,
                "operation": "preview",
                "view": "game",
                "scene_capture": True,
                "camera_id": plan.get("camera_id", ""),
            },
            root,
        )
        actions._capture_results[revision] = result
        actions._capture_cleanup[revision] = cleanup
    except Exception:
        cleanup()
        raise
    return None
