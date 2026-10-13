"""Related game items and editable native UI, presented as one creation workspace."""

import json
import uuid
from copy import deepcopy

from . import (
    art_samples,
    background,
    core,
    development,
    game_art,
    image_assets,
    production,
    visual_assets,
    workflow,
)


def catalog(project):
    """List item relationships and native screens, including developer-retained properties."""
    root = game_art.root(project)
    return {
        kind: [core.read_optional_json(p) for p in sorted((root / kind).glob("*.json"))]
        for kind in ("game-items", "game-screens")
    }


def create_item(
    project,
    item_id,
    model_asset_id=None,
    model=None,
    name="",
    description="",
    icon_asset_id=None,
    render_icon=True,
    update_fields=None,
):
    """Make one linked item: model, transparent icon, native item data and pickup.

    Reuse model_asset_id or supply one produce item (recipe/custom/source/template).
    Updates preserve developer-edited name/description unless named in update_fields.
    Pass render_icon=False and an existing icon_asset_id to reuse artwork without Blender.
    """
    item_id = core.asset_id(item_id)
    if type(render_icon) is not bool:
        raise ValueError("render_icon must be a boolean")
    fields = update_fields or []
    if not isinstance(fields, list) or set(fields) - {"name", "description"}:
        raise ValueError("update_fields can contain name and description")
    name = game_art.text(name or item_id, "name", 120)
    description = game_art.text(description, "description", 1500)
    if (model is None) == (model_asset_id is None):
        raise ValueError("Choose an existing model_asset_id or a new model plan")
    if model is not None:
        if not isinstance(model, dict) or model.get("method") == "image":
            raise ValueError("An item model must be a 3D produce plan")
        model = deepcopy(model)
        model.setdefault("asset_id", item_id + "_model")
        model_asset_id = model["asset_id"]
    core.asset_id(model_asset_id)
    if (
        model is None
        and workflow.inspect_asset(project, model_asset_id)["current"].get("status") != "imported"
    ):
        raise ValueError("Import the model first or provide a model plan")
    icon_asset_id = core.asset_id(icon_asset_id or item_id + "_icon")
    if not render_icon:
        assets = image_assets.catalog(project, icon_asset_id)["assets"]
        if not assets or not assets[0].get("current"):
            raise ValueError("Import the selected icon first")
        if assets[0]["current"].get("kind") == "texture":
            raise ValueError("Item artwork must be a UI image")
    current = core.read_optional_json(game_art.root(project) / "game-items" / (item_id + ".json"))
    return background.submit(
        project,
        "game_item",
        dict(
            item_id=item_id,
            model_asset_id=model_asset_id,
            model=model,
            name=name,
            description=description,
            icon_asset_id=icon_asset_id,
            render_icon=render_icon,
            update_fields=fields,
            expected_revision=(current or {}).get("revision", ""),
        ),
        item_id,
    )


def step(job, key, create):
    task = job.state.get(key)
    if task:
        status = workflow.job_status(job.project, task["request_id"])
        if status["status"] in {"error", "cancelled"}:
            task = background.resume(job.project, task["request_id"]) if task.get("kind") else None
    if not task:
        job.check()
        task = job.track(create())
        job.update(**{key: task})
    return job.wait(task)


def run_item(
    job,
    item_id,
    model_asset_id,
    model,
    name,
    description,
    icon_asset_id,
    render_icon,
    update_fields,
    expected_revision,
):
    if model is not None:
        job.update(stage="Making item model")
        step(job, "model_task", lambda: production.submit(job.project, [model], description))
    if render_icon:
        job.update(stage="Rendering matching item icon")
        step(
            job,
            "icon_task",
            lambda: visual_assets.submit(job.project, model_asset_id, "icon", icon_asset_id),
        )
    root = game_art.root(job.project)
    info = workflow.inspect_asset(job.project, model_asset_id)
    image = core.read_optional_json(root / "image-receipts" / (icon_asset_id + ".json"))
    if info["current"].get("status") != "imported" or not image:
        raise ValueError("Wait for the model and icon imports")
    payload = job.state.get("item_payload")
    if not payload:
        payload = dict(
            schema_version=1,
            item_id=item_id,
            revision=uuid.uuid4().hex,
            expected_revision=expected_revision,
            model_asset_id=model_asset_id,
            model_revision=info["current"]["request_id"],
            icon_asset_id=icon_asset_id,
            icon_revision=image["revision"],
            name=name,
            description=description,
            update_fields=update_fields,
        )
        job.update(item_payload=payload)
    job.update(stage="Linking native item and pickup")
    result = step(
        job,
        "native_task",
        lambda: development.request(
            job.project, "game_item", content_json=json.dumps(payload, ensure_ascii=False)
        ),
    )
    return {"stage": "Game item ready", "item_id": item_id, "item_result": result}


def create_ui(
    project, screen_id, kind="inventory", item_ids=None, title="", place=True, update_theme=False
):
    """Create/update editable inventory, HUD or pause UI using native engine controls.

    Inventory exposes 16 item slots, details and selection hooks; HUD health/skill setters;
    pause UI exposes resume/settings hooks. Existing layout and event edits are retained.
    place adds one owned UI host to the scene. Native game logic can call the public hooks.
    """
    screen_id = core.asset_id(screen_id)
    if kind not in {"inventory", "hud", "pause"}:
        raise ValueError("Choose inventory, hud or pause")
    if type(place) is not bool or type(update_theme) is not bool:
        raise ValueError("Screen flags must be booleans")
    if not isinstance(item_ids or [], list) or len(item_ids or []) > (4 if kind == "hud" else 16):
        raise ValueError("Choose at most 4 HUD items or 16 inventory items")
    items = []
    for item in item_ids or []:
        item = core.asset_id(item)
        row = core.read_optional_json(game_art.root(project) / "game-items" / (item + ".json"))
        if not row:
            raise ValueError("Create the linked game item first: " + item)
        items.append(item)
    current = core.read_optional_json(
        game_art.root(project) / "game-screens" / (screen_id + ".json")
    )
    if current and current["kind"] != kind:
        raise ValueError("Choose a new screen ID for a different UI template")
    payload = dict(
        schema_version=1,
        screen_id=screen_id,
        kind=kind,
        revision=uuid.uuid4().hex,
        expected_revision=(current or {}).get("revision", ""),
        item_ids=items,
        title=game_art.text(title, "title", 120),
        theme=art_samples.theme(project),
        place=place,
        update_theme=update_theme,
    )
    return development.request(
        project, "game_ui", content_json=json.dumps(payload, ensure_ascii=False)
    )


def workspace(project, creation_id=None):
    """One page of linked model/icon/native UI, versions, tasks and available actions."""
    state = catalog(project)
    if not creation_id:
        return {**state, "art_samples": art_samples.catalog(project)}
    creation_id = core.asset_id(creation_id)
    item = next((r for r in state["game-items"] if r["item_id"] == creation_id), None)
    if not item:
        raise ValueError("Choose an existing game item")
    info = workflow.inspect_asset(project, item["model_asset_id"])
    return {
        "item": item,
        "model": info,
        "images": image_assets.catalog(project, item["icon_asset_id"])["assets"],
        "screens": [r for r in state["game-screens"] if creation_id in r["item_ids"]],
        "next_actions": ["view_model", "create_game_item", "plan_image_edit", "create_game_ui"],
    }


def example(project, item_id="example_herbalist_potion"):
    """Make the bundled editable herbalist potion, matching icon, data and pickup without an API."""
    from . import registry

    script = (registry.resources() / "examples/herbalist_potion.py").read_text(encoding="utf-8")
    return create_item(
        project,
        item_id,
        model={"method": "custom", "script": script},
        name="Herbalist potion",
        description="A jade ceramic potion with warm brass bands and a leaf seal.",
    )
