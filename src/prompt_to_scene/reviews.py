"""Persistent native before/after captures with an engine-owned fixed camera frame."""

import uuid

from . import core, registry, workflow


def capture(project, asset_id, review_id=None, stage="before", view="studio", refresh=False):
    core.asset_id(asset_id)
    if stage not in {"before", "after"} or view not in {"studio", "front", "back", "game"}:
        raise ValueError("Choose before/after and studio/front/back/game")
    target = registry.resolve(project)
    root = core.state_root(target.root)
    if review_id:
        workflow.identifier(review_id)
    elif stage != "before":
        raise ValueError("Start with a before capture and reuse its review_id")
    review_id = review_id or uuid.uuid4().hex
    path = root / "reviews" / (review_id + ".json")
    record = core.read_optional_json(path)
    if record:
        if record["asset_id"] != asset_id or record["view"] != view:
            raise ValueError("A comparison must keep the same asset and view")
    else:
        if stage != "before":
            raise ValueError("Unknown review")
        record = {
            "review_id": review_id,
            "asset_id": asset_id,
            "view": view,
            "engine": target.engine,
            "created_utc": workflow.now(),
        }
    if stage == "after" and workflow.job_status(project, record["before"])["status"] != "completed":
        raise ValueError("Wait for the before image to finish")
    if record.get(stage) and not (stage == "after" and refresh):
        state = workflow.job_status(project, record[stage])
        if state["status"] not in {"error", "cancelled"}:
            return {**state, "review_id": review_id}
    task = workflow.action(
        project,
        "preview",
        asset_id=asset_id,
        scope="asset",
        values={"view": view, "frame_id": review_id, "review_stage": stage},
    )
    if record.get(stage) and refresh:
        record.setdefault("previous_after", []).append(record[stage])
    record[stage] = task["request_id"]
    core.atomic_json(path, record)
    return {**task, "review_id": review_id}


def read(project, review_id):
    workflow.identifier(review_id)
    root = core.state_root(registry.resolve(project).root)
    record = core.read_optional_json(root / "reviews" / (review_id + ".json"))
    if not record:
        raise ValueError("Unknown review")
    return {
        **record,
        "captures": {
            stage: workflow.job_status(project, record[stage])
            for stage in ("before", "after")
            if stage in record
        },
    }
