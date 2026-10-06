"""Native material variants with actual preview images and selective, journalled assignment."""

from . import background, core, development, project_library, registry, workflow


def start(
    project, paths=None, reference=None, fields=None, mode="preview", plan_id=None, selected=None
):
    if mode in {"apply", "undo", "inspect"}:
        plan_id = workflow.identifier(plan_id)
        root = core.state_root(registry.resolve(project).root)
        plan = core.read_optional_json(root / "adaptation" / (plan_id + ".json"))
        if not plan:
            raise ValueError("Preview a reference adaptation first")
        if mode == "inspect":
            return plan
        ids = {row["id"] for row in plan["entries"]}
        if selected is not None and (
            not isinstance(selected, list) or not selected or not set(selected) <= ids
        ):
            raise ValueError("Select row IDs from this preview")
        return development.request(
            project, "adapt", mode=mode, plan_id=plan_id, slots=selected or []
        )
    if mode != "preview" or not isinstance(paths, list) or not 1 <= len(paths) <= 20:
        raise ValueError("Preview 1–20 model/prefab assets")
    paths = list(dict.fromkeys(project_library.asset_path(project, p) for p in paths))
    project_library.asset_path(project, reference)
    if reference in paths:
        raise ValueError("Select target assets separately from the reference")
    fields = fields or ["color", "roughness", "texture_scale"]
    if (
        not isinstance(fields, list)
        or not fields
        or set(fields) - {"color", "roughness", "texture_scale"}
    ):
        raise ValueError("Choose color, roughness and/or texture_scale")
    return background.submit(
        project, "adaptation", dict(paths=paths, reference=reference, fields=fields)
    )


def run(job, paths, reference, fields):
    task = job.state.get("plan_task")
    if not task:
        task = development.request(
            job.project, "adapt", mode="preview", paths=paths, path=reference, slots=fields
        )
        job.update(plan_task=task)
    result = job.wait(task)
    plan_id = result["development"]["plan_id"]
    plan = start(job.project, mode="inspect", plan_id=plan_id)
    previews = list(job.state.get("previews", []))
    done = {row["path"] for row in previews}
    for row in plan["assets"]:
        if row["path"] in done:
            continue
        job.check()
        job.update(stage="Rendering before/after: " + row["path"], plan_id=plan_id)
        before = job.wait(project_library.reuse(job.project, row["path"], "preview"))
        after = job.wait(project_library.reuse(job.project, row["variant"], "preview"))
        previews.append(
            {"path": row["path"], "before": before["request_id"], "after": after["request_id"]}
        )
        job.update(previews=previews)
    return {
        "plan_id": plan_id,
        "previews": previews,
        "entries": plan["entries"],
        "message": "Preview variants are separate assets. Select material rows to "
        "apply; the reference and geometry stay intact.",
    }
