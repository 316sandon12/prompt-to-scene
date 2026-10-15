"""Selective linked updates with durable steps and revision-guarded, single-update undo."""

import uuid

from . import background, core, creations, game_art, image_assets, parts, visual_assets, workflow
from .creative_tasks import fingerprint


def dependencies(project, asset_id):
    """Inspect model → icon → item → UI dependencies and the exact revisions affected."""
    asset_id = core.asset_id(asset_id)
    info = workflow.inspect_asset(project, asset_id)
    if info["current"].get("status") != "imported":
        raise ValueError("Wait for the current model import")
    state = creations.catalog(project)
    items = [r for r in state["game-items"] if r["model_asset_id"] == asset_id]
    names = {r["item_id"] for r in items}
    images = {
        r["icon_asset_id"]: core.read_optional_json(
            game_art.root(project) / "image-receipts" / (r["icon_asset_id"] + ".json")
        )
        for r in items
    }
    row = dict(
        asset_id=asset_id,
        model_revision=info["current"]["request_id"],
        items=items,
        images=images,
        screens=[r for r in state["game-screens"] if names.intersection(r["item_ids"])],
    )
    row["token"] = fingerprint(row)
    row["parts"] = (info["metadata"].get("report") or {}).get("parts", {})
    return row


def plan(project, asset_id, part, changes, refresh_icons=True):
    """Preview a named-part edit and dependent updates. Disable refresh_icons for handmade icons.

    Inventory, rule IDs, scene transforms, item names and manually edited UI layouts are retained.
    Screens already refer to stable native item objects, so no layout recreation is necessary.
    """
    before = dependencies(project, asset_id)
    if part not in before["parts"] or not changes:
        raise ValueError("Choose an existing model part and at least one change")
    parts.validate_changes(changes)
    if type(refresh_icons) is not bool:
        raise ValueError("refresh_icons must be a boolean")
    locks = before["parts"][part].get("locks", {})
    if (
        set(changes) & {"scale", "offset", "rotation"}
        and locks.get("geometry")
        or set(changes) & {"color", "roughness", "metallic"}
        and locks.get("material")
    ):
        raise ValueError("This part is locked; unlock the intended properties before planning")
    # A shared handmade icon must never be silently replaced for unrelated items.
    all_items = creations.catalog(project)["game-items"]
    if refresh_icons and any(
        r["model_asset_id"] != asset_id and r["icon_asset_id"] in before["images"]
        for r in all_items
    ):
        raise ValueError(
            "An icon is shared with another model; keep it or assign a separate icon first"
        )
    row = dict(
        update_id=uuid.uuid4().hex,
        before=before,
        part=part,
        changes=changes,
        refresh_icons=refresh_icons,
        status="ready",
        created_utc=workflow.now(),
    )
    core.atomic_json(game_art.root(project) / "linked-updates" / (row["update_id"] + ".json"), row)
    return row


def catalog(project):
    """Read linked update receipts, including reversible completed updates."""
    return {
        "updates": [
            core.read_optional_json(p)
            for p in sorted((game_art.root(project) / "linked-updates").glob("*.json"))
        ]
    }


def execute(project, update_id, undo=False):
    """Apply a prepared update, or undo just that update if its dependencies are still current."""
    if type(undo) is not bool:
        raise ValueError("undo must be a boolean")
    path = game_art.root(project) / "linked-updates" / (workflow.identifier(update_id) + ".json")
    with background.lock(path):
        row = core.read_optional_json(path)
        if not row:
            raise ValueError("Unknown linked update")
        key = "undo_task" if undo else "task"
        if row.get(key):
            return workflow.job_status(project, row[key]["request_id"])
        expected = row.get("after") if undo else row["before"]
        if not expected or undo and row["status"] != "completed":
            raise ValueError("Only a completed update can be undone")
        if dependencies(project, row["before"]["asset_id"])["token"] != expected["token"]:
            raise ValueError("Linked assets changed; keep the later edits and prepare a new update")
        row[key] = background.submit(
            project,
            "linked_update",
            dict(update_id=update_id, undo=undo),
            row["before"]["asset_id"],
        )
        core.atomic_json(path, row)
        return row[key]


def run(job, update_id, undo):
    path = game_art.root(job.project) / "linked-updates" / (update_id + ".json")
    row = core.read_optional_json(path)
    asset = row["before"]["asset_id"]
    expected = row["after"] if undo else row["before"]
    if (
        not job.state.get("model_task")
        and dependencies(job.project, asset)["token"] != expected["token"]
    ):
        raise ValueError("Dependencies changed before the update started")
    job.update(stage="Restoring model" if undo else "Editing model part")
    model = creations.step(
        job,
        "model_task",
        lambda: (
            workflow.restore(job.project, asset, row["before"]["model_revision"])
            if undo
            else parts.edit(job.project, asset, row["part"], row["changes"])
        ),
    )
    if (
        workflow.inspect_asset(job.project, asset)["current"].get("request_id")
        != model["request_id"]
    ):
        raise ValueError("A newer model exists; this update will not overwrite it")
    for icon, previous in row["before"]["images"].items():
        if row["refresh_icons"]:
            if not job.state.get("icon_" + icon):
                actual = core.read_optional_json(job.root / "image-receipts" / (icon + ".json"))
                if actual != expected["images"][icon]:
                    raise ValueError("Icon changed outside this update: " + icon)
            job.update(stage="Refreshing linked artwork · " + icon)
            creations.step(
                job,
                "icon_" + icon,
                lambda: (
                    image_assets.publish(job.project, icon, previous["revision"])
                    if undo
                    else visual_assets.submit(job.project, asset, "icon", icon)
                ),
            )
    for item in row["before"]["items"]:
        if (
            workflow.inspect_asset(job.project, asset)["current"].get("request_id")
            != model["request_id"]
        ):
            raise ValueError("A newer model exists; keep its current dependencies")
        name = item["item_id"]
        saved = job.state.get("item_" + name)
        current = core.read_optional_json(
            game_art.root(job.project) / "game-items" / (name + ".json")
        )
        previous = next(r for r in expected["items"] if r["item_id"] == name)
        if not saved and current["revision"] != previous["revision"]:
            raise ValueError("Item changed outside this update: " + name)
        job.update(stage="Updating item reference · " + name)
        creations.step(
            job,
            "item_" + name,
            lambda: creations.create_item(
                job.project,
                name,
                model_asset_id=asset,
                icon_asset_id=item["icon_asset_id"],
                render_icon=False,
                place_pickup=False,
            ),
        )
    creations.step(job, "preview_task", lambda: visual_assets.submit(job.project, asset))
    # Merge with the launcher receipt so a fast worker cannot discard its task ID.
    with background.lock(path):
        current = core.read_optional_json(path)
        current.update(
            status="undone" if undo else "completed",
            **{"restored" if undo else "after": dependencies(job.project, asset)},
        )
        core.atomic_json(path, current)
    return dict(
        stage="Linked update restored" if undo else "Linked model, icons and item references ready",
        update_id=update_id,
        affected_items=[r["item_id"] for r in row["before"]["items"]],
        preserved_screens=[r["screen_id"] for r in row["before"]["screens"]],
    )
