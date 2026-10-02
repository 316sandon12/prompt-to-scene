"""The same workbench actions serve the local app and an optional MCP App surface."""

import base64
from pathlib import Path

from . import (
    authoring,
    background,
    compositions,
    core,
    development,
    generation,
    levels,
    parts,
    performance,
    project_library,
    quality,
    registry,
    reviews,
    sources,
    studies,
    workflow,
)

URI = "ui://prompt-to-scene/workbench.html"


def page():
    source = Path(__file__).with_name("workbench.html").read_text(encoding="utf-8")
    script = Path(__file__).with_name("workbench.js").read_text(encoding="utf-8")
    return source.replace(
        '<script src="/workbench.js" defer></script>', "<script>" + script + "</script>"
    )


def image(kind, request_id=None, asset_id=None, view="studio"):
    root = core.state_root(registry.resolve().root)
    if kind == "reference":
        path = Path(quality.brief(None).get("image", ""))
        if path.parent != root / "references":
            raise ValueError("No reference image saved")
    elif kind == "studio":
        path = studies.preview_path(None, asset_id, request_id, view)
    elif kind in {"engine", "play_before"}:
        suffix = "_before" if kind == "play_before" else ""
        path = root / "previews" / (workflow.identifier(request_id) + suffix + ".png")
        if workflow.job_status(None, request_id)["status"] != "completed":
            raise ValueError("Wait for this capture to finish")
    else:
        raise ValueError("Choose an engine, studio or reference image")
    if not path.is_file() or path.stat().st_size > 10 * 1024**2:
        raise ValueError("Image missing or too large")
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if not mime:
        raise ValueError("Unsupported image format")
    return {
        "kind": kind,
        "url": "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode(),
    }


def dispatch(action, values=None):
    values = values or {}
    if not isinstance(values, dict):
        raise ValueError("Action values must be an object")
    if action == "state":
        from .setup import state

        return state()
    routes = {
        "inspect_asset": lambda asset_id: workflow.inspect_asset(None, asset_id),
        "create": lambda **v: authoring.create(None, **v),
        "import": lambda **v: sources.submit(None, **v),
        "scene": lambda: workflow.action(None, "inspect"),
        "select": lambda object_id: workflow.action(
            None, "select", values={"object_id": object_id}
        ),
        "compose": lambda **v: compositions.submit(None, **v),
        "part": lambda **v: authoring.edit_part(None, **v),
        "external_part": lambda **v: parts.edit(None, **v),
        "art_brief": lambda **v: quality.set_brief(None, **v),
        "quality": lambda **v: quality.start(None, **v),
        "repair": lambda **v: quality.repair(None, **v),
        "performance": lambda **v: performance.inspect(None, **v),
        "optimize": lambda **v: performance.optimize(None, **v),
        "generate": lambda **v: generation.submit(None, **v),
        "interactive": lambda **v: development.interactive(None, **v),
        "interaction": lambda **v: development.configure(None, **v),
        "protection": lambda **v: development.protection(None, **v),
        "update_review": lambda **v: development.review_update(None, **v),
        "look": lambda **v: development.look(None, **v),
        "level": lambda **v: levels.build(None, **v),
        "playcheck": lambda **v: development.playcheck(None, **v),
        "library": lambda **v: project_library.search(None, **v),
        "reuse": lambda **v: project_library.reuse(None, **v),
        "tag": lambda **v: project_library.annotate(None, **v),
        "publish": lambda **v: sources.publish(None, **v),
        "preview": lambda asset_id: workflow.action(
            None, "preview", asset_id=asset_id, scope="asset"
        ),
        "task": lambda request_id: workflow.job_status(None, request_id),
        "cancel": lambda request_id: workflow.cancel(None, request_id),
        "resume": lambda request_id: background.resume(None, request_id),
        "undo": lambda undo_id: workflow.action(None, "undo", undo_id=undo_id),
        "review": lambda review_id: reviews.read(None, review_id),
        "image": image,
    }
    if action not in routes:
        raise ValueError("Unknown workbench action")
    return routes[action](**values)
