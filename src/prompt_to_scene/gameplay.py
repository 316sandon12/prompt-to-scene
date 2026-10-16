"""Editable, bounded gameplay rules shared by the two native runtime adapters."""

import hashlib
import json
import uuid
from copy import deepcopy

from . import core, development, game_art


def _integer(value, name, low=0, high=9999):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return value


def _counts(rows, items, name, maximum=16):
    if not isinstance(rows, list) or len(rows) > maximum:
        raise ValueError(name + f" accepts at most {maximum} item quantities")
    seen, result = set(), []
    for row in rows:
        if not isinstance(row, dict) or row.keys() != {"item_id", "quantity"}:
            raise ValueError(name + " rows need item_id and quantity")
        item = core.asset_id(row["item_id"])
        if item not in items or item in seen:
            raise ValueError(name + " contains an unknown or repeated item: " + item)
        seen.add(item)
        result.append(dict(item_id=item, quantity=_integer(row["quantity"], name, 1)))
    return result


def validate(settings):
    """Validate before any native mutation; no code or arbitrary expressions are accepted."""
    if not isinstance(settings, dict) or settings.keys() - {
        "title",
        "item_ids",
        "initial_inventory",
        "rules",
        "max_health",
        "initial_health",
        "autosave",
        "slot",
        "screen_ids",
        "save_version",
        "item_aliases",
        "rule_aliases",
        "persist_on_travel",
    }:
        raise ValueError("Unknown gameplay setting")
    settings = deepcopy(settings)
    items = settings.get("item_ids", [])
    if not isinstance(items, list) or not 1 <= len(items) <= 128:
        raise ValueError("Choose 1–128 linked game items")
    items = [core.asset_id(item) for item in items]
    if len(set(items)) != len(items):
        raise ValueError("Game item IDs must be unique")
    maximum = development.number(settings.get("max_health", 100), "max_health", 1, 1e6)
    health = development.number(
        settings.get("initial_health", maximum), "initial_health", 0, maximum
    )
    rules = settings.get("rules", [])
    if not isinstance(rules, list) or not 1 <= len(rules) <= 128:
        raise ValueError("Choose 1–128 gameplay rules")
    known = set()
    cooked = []
    for row in rules:
        if not isinstance(row, dict) or row.keys() - {
            "rule_id",
            "label",
            "trigger",
            "item_id",
            "costs",
            "rewards",
            "heal",
            "once",
            "requires",
            "asset_id",
            "pickup_id",
        }:
            raise ValueError("Unknown rule field")
        name = core.asset_id(row.get("rule_id"))
        if name in known:
            raise ValueError("Rule IDs must be unique")
        known.add(name)
        trigger = row.get("trigger", "interact")
        if trigger not in {"interact", "craft", "use"}:
            raise ValueError("Rule trigger must be interact, craft or use")
        item = core.asset_id(row["item_id"]) if row.get("item_id") else ""
        if trigger == "use" and item not in items:
            raise ValueError("Use rules need a linked item_id")
        if item and trigger != "use":
            raise ValueError("item_id is only used by use rules")
        if any(r["item_id"] == item for r in cooked) and item:
            raise ValueError("Each item has at most one use rule")
        costs = _counts(row.get("costs", []), items, "costs")
        if trigger == "use" and not any(c["item_id"] == item for c in costs):
            raise ValueError("A use rule must consume the used item")
        once = row.get("once", False)
        if type(once) is not bool:
            raise ValueError("once must be a boolean")
        requires = row.get("requires", [])
        if not isinstance(requires, list) or len(requires) > 16:
            raise ValueError("A rule accepts at most 16 prerequisite rule IDs")
        asset, pickup = row.get("asset_id", ""), row.get("pickup_id", "")
        if asset and pickup:
            raise ValueError("Bind one model or one pickup per rule")
        if (asset or pickup) and trigger != "interact":
            raise ValueError("Scene bindings are only for interact rules")
        cooked.append(
            dict(
                rule_id=name,
                label=game_art.text(row.get("label", name), "label", 120),
                trigger=trigger,
                item_id=item,
                costs=costs,
                rewards=_counts(row.get("rewards", []), items, "rewards"),
                heal=development.number(row.get("heal", 0), "heal", 0, 1e6),
                once=once,
                requires=list(dict.fromkeys(core.asset_id(r) for r in requires)),
                asset_id=core.asset_id(asset) if asset else "",
                pickup_id=core.asset_id(pickup) if pickup else "",
            )
        )
    for row in cooked:
        if set(row["requires"]) - known or row["rule_id"] in row["requires"]:
            raise ValueError("A prerequisite must reference another rule in this flow")
    graph = {r["rule_id"]: r["requires"] for r in cooked}
    visited = set()

    def visit(node, path):
        if node in path:
            raise ValueError("Gameplay prerequisites contain a cycle")
        if node not in visited:
            for dep in graph[node]:
                visit(dep, path | {node})
            visited.add(node)

    for name in known:
        visit(name, set())
    bindings = [
        r["asset_id"] or "pickup:" + r["pickup_id"]
        for r in cooked
        if r["asset_id"] or r["pickup_id"]
    ]
    if len(set(bindings)) != len(bindings):
        raise ValueError("Each scene asset can trigger only one rule in a flow")
    screens = settings.get("screen_ids", [])
    if not isinstance(screens, list) or len(screens) > 16:
        raise ValueError("Bind at most 16 native screens")
    autosave = settings.get("autosave", True)
    if type(autosave) is not bool:
        raise ValueError("autosave must be a boolean")
    aliases = {}
    for key, allowed in (("item_aliases", set(items)), ("rule_aliases", known)):
        rows = settings.get(key, [])
        if not isinstance(rows, list) or len(rows) > 128:
            raise ValueError("Use at most 128 save aliases")
        mapping = {}
        for row in rows:
            if not isinstance(row, dict) or row.keys() != {"from_id", "to_id"}:
                raise ValueError("Save aliases need from_id and to_id")
            old, new = core.asset_id(row["from_id"]), core.asset_id(row["to_id"])
            if old in mapping or old == new or new not in allowed or old in allowed:
                raise ValueError("Alias an obsolete ID to one current ID")
            mapping[old] = new
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("Use distinct alias destinations to avoid ambiguous save merges")
        aliases[key] = [dict(from_id=k, to_id=v) for k, v in mapping.items()]
    travel = settings.get("persist_on_travel", True)
    if type(travel) is not bool:
        raise ValueError("persist_on_travel must be a boolean")
    return dict(
        save_version=_integer(settings.get("save_version", 1), "save_version", 1, 10000),
        persist_on_travel=travel,
        **aliases,
        title=game_art.text(settings.get("title", "Gameplay"), "title", 120),
        item_ids=items,
        initial_inventory=_counts(
            settings.get("initial_inventory", []), items, "initial_inventory", 128
        ),
        rules=cooked,
        max_health=maximum,
        initial_health=health,
        autosave=autosave,
        slot=core.asset_id(settings.get("slot", "main")),
        screen_ids=list(dict.fromkeys(core.asset_id(s) for s in screens)),
    )


def catalog(project):
    """List installed gameplay flows and their native bindings, without reading player saves."""
    root = game_art.root(project)
    return {
        "flows": [core.read_optional_json(p) for p in sorted((root / "gameplay").glob("*.json"))]
    }


def configure(project, flow_id, settings, expected_revision=None):
    """Create/update native inventory, crafting, use, conditions and persistent progress.

    A rule has rule_id, trigger (interact/craft/use), label, costs/rewards
    [{item_id,quantity}], heal, once, prerequisite rule IDs in requires, and optional
    asset_id/pickup_id for an existing scene interaction. Use rules also need item_id.
    Updates keep asset identity, adapter bindings and player save data. A changed rule
    definition does not reset an already completed once-only rule. Use a new slot for that.
    """
    flow_id = core.asset_id(flow_id)
    settings = validate(settings)
    root = game_art.root(project)
    previous = core.read_optional_json(root / "gameplay" / (flow_id + ".json")) or {}
    if expected_revision is not None and expected_revision != previous.get("revision", ""):
        raise ValueError("Gameplay changed; refresh the flow before updating")
    if settings["save_version"] < previous.get("save_version", 1):
        raise ValueError("Save version cannot go backwards")
    if (
        previous
        and any(settings[k] != previous.get(k, []) for k in ("item_aliases", "rule_aliases"))
        and settings["save_version"] <= previous.get("save_version", 1)
    ):
        raise ValueError("Increase save_version when changing migration aliases")
    for item in settings["item_ids"]:
        if not (root / "game-items" / (item + ".json")).is_file():
            raise ValueError("Create the linked game item first: " + item)
    for screen in settings["screen_ids"]:
        if not (root / "game-screens" / (screen + ".json")).is_file():
            raise ValueError("Create the native screen first: " + screen)
    identity_path = root / "gameplay-project.json"
    identity = core.read_optional_json(identity_path)
    if not identity:
        identity = {"project_id": uuid.uuid4().hex}
        core.atomic_json(identity_path, identity)
    spec = dict(
        schema_version=1,
        flow_id=flow_id,
        revision=uuid.uuid4().hex,
        expected_revision=previous.get("revision", ""),
        **settings,
        save_key="pts_"
        + hashlib.sha256(
            (identity["project_id"] + ":" + flow_id + ":" + settings["slot"]).encode()
        ).hexdigest()[:32],
    )
    return development.request(project, "gameplay", mode="configure", content_json=json.dumps(spec))


def adapters(project, flow_id, mode="inspect", target=""):
    """Inspect compatible native project adapters or bind/unbind one for a flow.

    Unity adapters implement IGameProjectAdapter; UE actors implement BPI_PTSProjectAdapter.
    The adapter owns its inventory/health and commits a whole transaction atomically.
    Select a target ID returned by inspect. bind validates it again; unknown private fields
    are never guessed. unbind returns to the flow's built-in runtime state.
    """
    core.asset_id(flow_id)
    if mode not in {"inspect", "bind", "unbind"}:
        raise ValueError("Choose inspect, bind or unbind")
    if not isinstance(target, str) or len(target) > 1000 or mode == "bind" and not target:
        raise ValueError("Choose a target returned by adapter inspection")
    return development.request(
        project,
        "gameplay",
        mode=mode,
        content_json=json.dumps(dict(flow_id=flow_id, target=target)),
    )


def evaluate(settings, state, rule_id, capacities=None):
    """Pure reference semantics used by previews/tests; actual play runs inside each engine."""
    config = validate(settings)
    rule = next((r for r in config["rules"] if r["rule_id"] == rule_id), None)
    if not rule:
        raise ValueError("Unknown gameplay rule")
    inventory = dict(state.get("inventory", {}))
    completed = set(state.get("completed", []))
    health = state.get("health", config["initial_health"])
    error = ""
    if rule["once"] and rule_id in completed:
        error = "already_completed"
    elif not set(rule["requires"]) <= completed:
        error = "prerequisite"
    elif rule["heal"] and health >= config["max_health"]:
        error = "health_full"
    elif any(inventory.get(c["item_id"], 0) < c["quantity"] for c in rule["costs"]):
        error = "missing_items"
    if error:
        return dict(success=False, reason=error, state=deepcopy(state))
    for c in rule["costs"]:
        inventory[c["item_id"]] = inventory.get(c["item_id"], 0) - c["quantity"]
    for r in rule["rewards"]:
        inventory[r["item_id"]] = inventory.get(r["item_id"], 0) + r["quantity"]
    if any(q > (capacities or {}).get(item, 9999) for item, q in inventory.items()):
        return dict(success=False, reason="capacity", state=deepcopy(state))
    return dict(
        success=True,
        reason="",
        state=dict(
            inventory=inventory,
            health=min(config["max_health"], health + rule["heal"]),
            completed=sorted(completed | {rule_id}),
        ),
    )


def attach(project, flow_id):
    """Attach an existing flow to the active scene, binding only matching present objects/UI.

    Keeps the definition, rule IDs and save namespace. Unity shares session state in memory;
    UE persists during level travel when persist_on_travel is enabled. External adapters own
    their inventory persistence and must be present/bound in each scene as needed.
    """
    name = core.asset_id(flow_id)
    row = core.read_optional_json(game_art.root(project) / "gameplay" / (name + ".json"))
    if not row:
        raise ValueError("Create the gameplay flow first")
    return development.request(
        project,
        "gameplay",
        mode="attach",
        content_json=json.dumps(dict(flow_id=name, expected_revision=row["revision"])),
    )
