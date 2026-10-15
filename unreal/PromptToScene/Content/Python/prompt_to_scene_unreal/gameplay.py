"""Author engine-only gameplay assets and bind explicit project adapter interfaces."""

import json
import math
import re

import unreal

from . import actions
from .game_creations import TEMPLATES, generated, identifier, mark, owned, read
from .protocol import write_json


def prop(obj, name, fallback=None):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return fallback


def result(value, message):
    return {
        "development": {
            "command": "gameplay",
            "passed": True,
            "plan_json": json.dumps(value),
            "message": message,
        }
    }


def execute(request, command, root):
    spec = json.loads(command.get("content_json", "{}"))
    name = identifier(spec.get("flow_id"))
    mode = command.get("mode", "configure")
    actors = actions.actors().get_all_level_actors()
    sessions = [a for a in actors if "PTS.Flow:" + name in map(str, a.tags)]
    if len(sessions) > 1:
        raise ValueError("Keep one session per gameplay flow in the current level")
    if mode != "configure":
        interface = generated(TEMPLATES + "BPI_PTSProjectAdapter")
        candidates = [
            a for a in actors if unreal.SystemLibrary.does_implement_interface(a, interface)
        ]
        if mode in {"bind", "unbind"}:
            if not sessions:
                raise ValueError("Place the gameplay flow in this level first")
            target = None
            if mode == "bind":
                target = next(
                    (a for a in candidates if a.get_path_name() == spec.get("target")), None
                )
                if not target:
                    raise ValueError("Adapter changed; inspect this level again")
            sessions[0].modify()
            sessions[0].set_editor_property("Adapter", target)
        elif mode != "inspect":
            raise ValueError("Unknown adapter operation")
        bound = prop(sessions[0], "Adapter") if sessions else None
        return result(
            {
                "flow_id": name,
                "bound_target": bound.get_path_name() if bound else "",
                "adapters": [
                    {
                        "target": a.get_path_name(),
                        "name": a.get_actor_label(),
                        "component": a.get_class().get_name(),
                    }
                    for a in candidates
                ],
            },
            "Compatible project adapters inspected",
        )

    record = root / "gameplay" / (name + ".json")
    old = read(record)
    if spec.get("schema_version") != 1 or not re.fullmatch(
        r"[a-f0-9]{32}", spec.get("revision", "")
    ):
        raise ValueError("Invalid gameplay protocol")
    if old and old["revision"] == spec["revision"]:
        return result(old, "Gameplay already configured")
    if (old or {}).get("revision", "") != spec.get("expected_revision", ""):
        raise ValueError("Gameplay changed since submission; refresh first")
    if not re.fullmatch(r"pts_[a-f0-9]{32}", spec.get("save_key", "")):
        raise ValueError("Invalid project save namespace")
    ids, rules = spec.get("item_ids", []), spec.get("rules", [])
    if not 1 <= len(ids) <= 128 or len(set(ids)) != len(ids) or not 1 <= len(rules) <= 128:
        raise ValueError("Choose 1–128 distinct items and rules")
    items = {}
    for item_id in ids:
        row = read(root / "game-items" / (identifier(item_id) + ".json"))
        item = unreal.load_asset(row["item_path"]) if row else None
        if not item:
            raise ValueError("Create the linked item first: " + item_id)
        items[item_id] = item
    limits = {key: max(1, prop(value, "MaxStack", 99)) for key, value in items.items()}

    def counts(rows):
        if not isinstance(rows, list) or len(rows) > 128:
            raise ValueError("Invalid item quantities")
        values = {}
        for row in rows:
            key, count = row.get("item_id"), row.get("quantity")
            if (
                key not in items
                or key in values
                or type(count) is not int
                or not 1 <= count <= 9999
            ):
                raise ValueError("Invalid item quantity")
            values[key] = count
        return values

    inventory = counts(spec.get("initial_inventory", []))
    if any(q > limits[k] for k, q in inventory.items()):
        raise ValueError("Initial inventory exceeds stack capacity")
    maximum, health = spec.get("max_health"), spec.get("initial_health")
    if (
        not all(type(v) in (int, float) and math.isfinite(v) for v in (maximum, health))
        or not 1 <= maximum <= 1000000
        or not 0 <= health <= maximum
    ):
        raise ValueError("Invalid health values")
    rule_ids = [identifier(r.get("rule_id")) for r in rules]
    if len(set(rule_ids)) != len(rule_ids):
        raise ValueError("Repeated rule IDs")
    bindings, uses = {}, {}
    for rule in rules:
        costs, _ = counts(rule["costs"]), counts(rule["rewards"])
        if rule["trigger"] not in {"interact", "craft", "use"} or not set(rule["requires"]) <= set(
            rule_ids
        ):
            raise ValueError("Invalid gameplay trigger or prerequisite")
        if not math.isfinite(rule["heal"]) or rule["heal"] < 0:
            raise ValueError("Invalid healing amount")
        if rule["trigger"] == "use":
            key = rule.get("item_id")
            if key not in costs or key in uses:
                raise ValueError("Each use rule must consume its own unique item")
            uses[key] = rule["rule_id"]
        if rule.get("asset_id") and rule.get("pickup_id"):
            raise ValueError("Choose one interaction binding")
        targets = []
        if rule.get("asset_id"):
            targets = actions.targets({"scope": "asset", "asset_id": identifier(rule["asset_id"])})
        elif rule.get("pickup_id"):
            tag = "PTS.Item:" + identifier(rule["pickup_id"])
            targets = [a for a in actors if tag in map(str, a.tags)]
        if rule.get("asset_id") or rule.get("pickup_id"):
            if rule["trigger"] != "interact" or not targets:
                raise ValueError("Place the referenced interaction before configuring gameplay")
        for actor in targets:
            if prop(actor, "FlowRuleId") is None:
                raise ValueError("Update this interaction to the current native template first")
            bound = prop(actor, "FlowSession")
            if actor in bindings or bound and prop(bound, "FlowId") != name:
                raise ValueError("An interaction already belongs to another rule or flow")
            bindings[actor] = rule["rule_id"]
    graph = {r["rule_id"]: r["requires"] for r in rules}
    visited = set()

    def visit(key, stack):
        if key in stack:
            raise ValueError("Cyclic prerequisites")
        if key not in visited:
            for dependency in graph[key]:
                visit(dependency, stack | {key})
            visited.add(key)

    for key in graph:
        visit(key, set())
    screens = []
    for screen_id in spec.get("screen_ids", []):
        identifier(screen_id)
        matches = [a for a in actors if "PTS.Screen:" + screen_id in map(str, a.tags)]
        if not matches:
            raise ValueError("Place every referenced screen in this level first")
        row = read(root / "game-screens" / (screen_id + ".json")) or {}
        defaults = unreal.get_default_object(generated(row["prefab_path"]))
        if prop(defaults, "FlowId") is None:
            raise ValueError(
                "This v0.13 screen keeps its custom layout. "
                "Create a new screen ID to use gameplay UI."
            )
        if prop(defaults, "FlowId", "") not in ("", name):
            raise ValueError("Widget already belongs to another gameplay flow")
        if any(prop(a, "FlowId", "") not in ("", name) for a in matches):
            raise ValueError("Screen already belongs to another gameplay flow")
        screens.extend(matches)

    native = name.replace("-", "_")
    base = "/Game/PromptToScene/Gameplay/" + native
    path = (old or {}).get("definition_path", base + "/BP_" + native)
    bp = owned(path, name, old)
    rule_assets = {}
    for rule in rules:
        destination = base + "/DA_" + rule["rule_id"].replace("-", "_")
        rule_assets[rule["rule_id"]] = (destination, owned(destination, name, False))
    if not bp:
        bp = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(
            path, generated(TEMPLATES + "BP_PTSGameSession")
        )
    if not bp:
        raise RuntimeError("Gameplay templates are missing; reinstall the current bridge")
    for rule in rules:
        destination, asset = rule_assets[rule["rule_id"]]
        if not asset:
            factory = unreal.DataAssetFactory()
            factory.set_editor_property("data_asset_class", generated(TEMPLATES + "BP_PTSGameRule"))
            folder, asset_name = destination.rsplit("/", 1)
            asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                asset_name, folder, None, factory
            )
        for key, value in {
            "RuleId": rule["rule_id"],
            "Label": rule["label"],
            "Trigger": rule["trigger"],
            "ItemId": rule.get("item_id", ""),
            "Costs": counts(rule["costs"]),
            "Rewards": counts(rule["rewards"]),
            "Requires": rule["requires"],
            "Heal": float(rule["heal"]),
            "Once": rule["once"],
        }.items():
            asset.set_editor_property(key, value)
        mark(asset, name)
        rule_assets[rule["rule_id"]] = asset
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    cls = generated(path)
    values = {
        "FlowId": name,
        "SaveKey": spec["save_key"],
        "Health": float(health),
        "MaxHealth": float(maximum),
        "Inventory": inventory,
        "Limits": limits,
        "Rules": rule_assets,
        "UseRules": uses,
        "CraftRules": [r["rule_id"] for r in rules if r["trigger"] == "craft"],
        "ItemIds": ids,
        "Autosave": spec["autosave"],
    }
    defaults = unreal.get_default_object(cls)
    for key, value in values.items():
        defaults.set_editor_property(key, value)
    mark(bp, name)
    session = (
        sessions[0] if sessions else actions.actors().spawn_actor_from_class(cls, unreal.Vector())
    )
    session.modify()
    session.tags = [unreal.Name("PTS.Flow:" + name)]
    session.set_actor_label(spec["title"] + " · Gameplay")
    for key, value in values.items():
        session.set_editor_property(key, value)
    for actor in actors:
        if prop(actor, "FlowSession") == session and actor not in bindings:
            actor.modify()
            actor.set_editor_property("FlowSession", None)
            actor.set_editor_property("FlowRuleId", "")
        if prop(actor, "FlowId") == name and actor != session and actor not in screens:
            actor.modify()
            actor.set_editor_property("FlowId", "")
    for actor, rule in bindings.items():
        actor.modify()
        actor.set_editor_property("FlowSession", session)
        actor.set_editor_property("FlowRuleId", rule)
    for screen in screens:
        screen.modify()
        screen.set_editor_property("FlowId", name)
    for screen_id in set((old or {}).get("screen_ids", [])) - set(spec.get("screen_ids", [])):
        row = read(root / "game-screens" / (screen_id + ".json"))
        if row:
            widget = unreal.load_asset(row["prefab_path"])
            defaults = unreal.get_default_object(generated(row["prefab_path"]))
            if prop(defaults, "FlowId") == name:
                defaults.set_editor_property("FlowId", "")
                mark(widget, screen_id)
    for screen_id in spec.get("screen_ids", []):
        row = read(root / "game-screens" / (screen_id + ".json"))
        widget = unreal.load_asset(row["prefab_path"])
        unreal.get_default_object(generated(row["prefab_path"])).set_editor_property("FlowId", name)
        mark(widget, screen_id)
    spec["definition_path"] = path
    write_json(record, spec)
    write_json(root / "gameplay-history" / name / (spec["revision"] + ".json"), spec)
    return result(spec, "Native gameplay and project bindings ready")
