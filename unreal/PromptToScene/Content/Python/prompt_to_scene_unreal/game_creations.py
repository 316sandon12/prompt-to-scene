"""Linked native game items and editable UMG screens; no runtime Python dependency."""

import json
import re

import unreal

from . import actions, protection
from .protocol import write_json

LIB = unreal.EditorAssetLibrary
TEMPLATES = "/PromptToScene/Templates/"


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
        raise ValueError("Invalid creation ID")
    return value


def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def generated(path):
    cls = unreal.load_class(None, path + "." + path.rsplit("/", 1)[-1] + "_C")
    if not cls:
        raise ValueError("Missing native template: " + path)
    return cls


def save(asset):
    if not LIB.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError("Could not save native creation")


def owned(path, owner, previous):
    asset = unreal.load_asset(path) if LIB.does_asset_exist(path) else None
    if asset and LIB.get_metadata_tag(asset, "PTS.Creation") != owner:
        raise ValueError("Destination contains an unowned asset: " + path)
    if previous and not asset:
        raise ValueError("Restore the missing creation before updating: " + path)
    return asset


def mark(asset, owner):
    LIB.set_metadata_tag(asset, "PTS.Creation", owner)
    save(asset)


def execute(request, command, root):
    spec = json.loads(command.get("content_json", "{}"))
    item = command["command"] == "game_item"
    key, folder = ("item_id", "game-items") if item else ("screen_id", "game-screens")
    name = identifier(spec.get(key))
    if spec.get("schema_version") != 1 or not re.fullmatch(
        r"[a-f0-9]{32}", spec.get("revision", "")
    ):
        raise ValueError("Invalid creation protocol")
    record = root / folder / (name + ".json")
    previous = read(record)
    if previous and previous["revision"] == spec["revision"]:
        return {
            "development": {
                "command": command["command"],
                "passed": True,
                "plan_json": json.dumps(previous),
            }
        }
    if (previous or {}).get("revision", "") != spec.get("expected_revision", ""):
        raise ValueError("Creation changed after submission; refresh and try again")
    if item:
        create_item(spec, previous, root)
    else:
        create_screen(spec, previous, root)
    write_json(record, spec)
    history = "game-item-history" if item else "game-screen-history"
    write_json(root / history / name / (spec["revision"] + ".json"), spec)
    return {
        "development": {
            "command": command["command"],
            "passed": True,
            "plan_json": json.dumps(spec),
            "message": "Editable native creation ready",
        }
    }


def create_item(s, previous, root):
    name = s["item_id"]
    model_id, icon_id = identifier(s["model_asset_id"]), identifier(s["icon_asset_id"])
    if set(s.get("update_fields", [])) - {"name", "description"}:
        raise ValueError("Invalid item fields")
    model_receipt = read(root / "receipts" / (model_id + ".json")) or {}
    icon_receipt = read(root / "image-receipts" / (icon_id + ".json")) or {}
    if (
        model_receipt.get("request_id") != s["model_revision"]
        or model_receipt.get("status") != "imported"
    ):
        raise ValueError("Model revision changed")
    if icon_receipt.get("revision") != s["icon_revision"]:
        raise ValueError("Icon revision changed")
    mesh = protection.mesh_for(model_id)
    texture = unreal.load_asset(icon_receipt["texture_path"])
    if not isinstance(texture, unreal.Texture2D):
        raise ValueError("Missing item icon")
    # Hyphens are valid protocol IDs, but object names use underscores in UE.
    native_name = name.replace("-", "_")
    base = "/Game/PromptToScene/Items/" + native_name
    s["item_path"] = (previous or {}).get("item_path", base + "/DA_" + native_name)
    s["pickup_path"] = (previous or {}).get("pickup_path", base + "/BP_" + native_name)
    data = owned(s["item_path"], name, previous)
    pickup = owned(s["pickup_path"], name, previous)
    if not data:
        factory = unreal.DataAssetFactory()
        factory.set_editor_property("data_asset_class", generated(TEMPLATES + "BP_PTSGameItem"))
        folder, asset_name = s["item_path"].rsplit("/", 1)
        data = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_name, folder, None, factory
        )
    if not pickup:
        pickup = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(
            s["pickup_path"], generated(TEMPLATES + "BP_PTSItemPickup")
        )
    if not data or not pickup:
        raise RuntimeError("Native item creation failed")
    mark(data, name)
    mark(pickup, name)
    unreal.BlueprintEditorLibrary.compile_blueprint(pickup)
    cls = generated(s["pickup_path"])
    defaults = unreal.get_default_object(cls)
    data.set_editor_property("ItemId", name)
    for native, field in (("DisplayName", "name"), ("Description", "description")):
        if not previous or field in s.get("update_fields", []):
            data.set_editor_property(native, unreal.Text(s[field]))
    data.set_editor_property("Icon", texture)
    data.set_editor_property("Model", mesh)
    data.set_editor_property("PickupClass", cls)
    defaults.set_editor_property("ItemData", data)
    if not previous:
        defaults.set_editor_property("TemplateKind", 2)
        defaults.set_editor_property("GameEventId", name)
        defaults.set_editor_property("InteractionLabel", s["name"])
    defaults.static_mesh_component.set_static_mesh(mesh)
    unreal.BlueprintEditorLibrary.compile_blueprint(pickup)
    mark(data, name)
    mark(pickup, name)
    s["name"] = str(data.get_editor_property("DisplayName"))
    s["description"] = str(data.get_editor_property("Description"))
    # Place one separate pickup; never convert or destroy developer actors.
    tag = "PTS.Item:" + name
    found = [a for a in actions.actors().get_all_level_actors() if tag in [str(t) for t in a.tags]]
    if not found:
        sources = actions.targets({"scope": "asset", "asset_id": model_id})
        location = sources[0].get_actor_location() if sources else unreal.Vector()
        # Keep the source model available but put the usable pickup beside it.
        location.y += 150
        actor = actions.actors().spawn_actor_from_class(cls, location)
        actor.tags = [unreal.Name(tag)]
        actor.set_actor_label(s["name"] + " · Pickup")
    protection_mesh = mesh
    from .development import enable_collision

    enable_collision(protection_mesh)


def widgets(bp):
    tree = unreal.find_object(bp, "WidgetTree")
    if not tree:
        raise ValueError("The editable widget tree is missing")
    root = unreal.find_object(tree, "Panel")
    if not isinstance(root, unreal.PanelWidget):
        raise ValueError("The named Panel widget is missing")
    result = []

    def visit(widget):
        result.append(widget)
        if isinstance(widget, unreal.PanelWidget):
            for child in widget.get_all_children():
                visit(child)

    visit(root)
    return result


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Invalid UI color")
    channels = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return unreal.LinearColor(
        *[v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels], 1
    )


def create_screen(s, previous, root):
    name, kind = s["screen_id"], s["kind"]
    if kind not in {"inventory", "hud", "pause"} or previous and previous["kind"] != kind:
        raise ValueError("Choose a new screen ID for a different UI template")
    if not isinstance(s["item_ids"], list) or len(s["item_ids"]) > (4 if kind == "hud" else 16):
        raise ValueError("Too many item slots for this template")
    theme = s["theme"]
    colors = {
        key: color(theme[key]) for key in ("background", "surface", "accent", "text", "muted")
    }
    items = []
    for item_id in s["item_ids"]:
        item = read(root / "game-items" / (identifier(item_id) + ".json"))
        asset = unreal.load_asset(item["item_path"]) if item else None
        if not asset:
            raise ValueError("Missing linked game item: " + item_id)
        items.append(asset)
    native_name = name.replace("-", "_")
    base = "/Game/PromptToScene/UI/" + native_name
    s["prefab_path"] = (previous or {}).get("prefab_path", base + "/WBP_" + native_name)
    s["host_path"] = (previous or {}).get("host_path", base + "/BP_" + native_name)
    bp = owned(s["prefab_path"], name, previous)
    host = owned(s["host_path"], name, previous)
    fresh = not previous
    if not bp:
        bp = LIB.duplicate_asset(TEMPLATES + "WBP_PTS_" + kind, s["prefab_path"])
    if not host:
        host = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(
            s["host_path"], generated(TEMPLATES + "BP_PTSUIHost_" + kind)
        )
    if not bp or not host:
        raise RuntimeError("UI templates missing; install the current UE bridge")
    mark(bp, name)
    mark(host, name)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    defaults = unreal.get_default_object(generated(s["prefab_path"]))
    count = 16 if kind == "inventory" else 4 if kind == "hud" else 0
    for i in range(count):
        defaults.set_editor_property("Item" + str(i), items[i] if i < len(items) else None)
    if fresh or s.get("update_theme"):
        for widget in widgets(bp):
            if isinstance(widget, unreal.TextBlock):
                widget.set_color_and_opacity(unreal.SlateColor(specified_color=colors["text"]))
                font = widget.get_editor_property("font")
                font.size = theme["font_size"] + (10 if widget.get_name() == "Title" else 0)
                widget.set_font(font)
                if fresh and s["title"] and widget.get_name() == "Title":
                    widget.set_text(unreal.Text(s["title"]))
            elif isinstance(widget, unreal.Border):
                widget.set_brush_color(colors["background"])
            elif isinstance(widget, unreal.Button):
                widget.set_background_color(colors["surface"])
            elif isinstance(widget, unreal.ProgressBar):
                widget.set_fill_color_and_opacity(colors["accent"])
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    titles = [w for w in widgets(bp) if w.get_name() == "Title"]
    if titles:
        s["title"] = str(titles[0].get_text())
    unreal.BlueprintEditorLibrary.compile_blueprint(host)
    host_class = generated(s["host_path"])
    unreal.get_default_object(host_class).set_editor_property(
        "WidgetClass", generated(s["prefab_path"])
    )
    mark(bp, name)
    mark(host, name)
    tag = "PTS.Screen:" + name
    if s.get("place") and not any(
        tag in [str(t) for t in a.tags] for a in actions.actors().get_all_level_actors()
    ):
        actor = actions.actors().spawn_actor_from_class(host_class, unreal.Vector())
        actor.tags = [unreal.Name(tag)]
        actor.set_actor_label(name + " · UI")
