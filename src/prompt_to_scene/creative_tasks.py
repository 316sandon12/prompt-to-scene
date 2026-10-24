"""Persistent, reviewable game-development tasks composed from the existing native actions."""

import hashlib
import inspect
import json
import uuid
from copy import deepcopy

from . import background, core, creations, game_art, registry, workflow

ALLOWED = {
    "produce",
    "create_game_item",
    "create_game_ui",
    "create_art_kit",
    "configure_gameplay",
    "reuse_recommendation",
    "interaction",
    "furnish",
    "update_creation",
    "install_project_adapter",
    "attach_gameplay",
    "review",
    "build_game",
}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def context(project, request="", inspect_scene=False):
    """Read the actual project, retained style, existing creations and rule definitions.

    The connected host interprets natural language; no second LLM or paid service is invoked.
    Set inspect_scene to request current native selection/camera/bounds, then wait for scene_task.
    Ask only for missing decisions, save a typed plan, and execute that one task.
    """
    from . import art_samples, gameplay, project_profiles, scene_context, styles

    target = registry.resolve(project)
    request = game_art.text(request, "request", 4000)
    state = {
        "project": str(target.project_file or target.root),
        "engine": target.engine,
        "game": game_art.configure(project),
        "scene_context": scene_context.brief(project),
        "style": styles.read(project),
        "samples": art_samples.context(project, "model"),
        "creations": creations.catalog(project),
        "gameplay": gameplay.catalog(project),
        "conventions": project_profiles.configure(project),
        "model_revisions": {
            p.stem: core.read_optional_json(p).get("request_id")
            for p in sorted((game_art.root(project) / "receipts").glob("*.json"))
        },
        "art_direction": core.read_optional_json(game_art.root(project) / "kit-direction.json"),
    }
    state["context_token"] = fingerprint(state)
    state["request"] = request
    state["scene_task"] = workflow.action(project, "inspect") if inspect_scene else None
    state["guidance"] = (
        "Use existing project assets and APIs where suitable. Compare actual game-camera images. "
        "Represent reuse, generation, linking and review as ordered plan steps; "
        "preserve controllers, "
        "lighting and manual data. Unresolved questions block execution, not inspection. "
        "Do not claim the host has seen images until it reads them."
    )
    return state


def save(project, title, request, steps, context_token, questions=None, plan_id=None):
    """Save a concrete ordered plan. Each step has id, action, values and a human-readable reason.

    Up to 24 steps. Use describe on each action for its exact contract. No shell commands,
    arbitrary tool names or remote generation services are accepted by this task runner.
    """
    from . import production

    current = context(project)
    if context_token != current["context_token"]:
        raise ValueError("Project context changed; read task_context and revise the plan")
    questions = questions or []
    if not isinstance(questions, list) or len(questions) > 5:
        raise ValueError("Keep at most five unresolved decisions")
    questions = [game_art.text(q, "question", 500) for q in questions]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 24:
        raise ValueError("A creative task contains 1–24 concrete steps")
    actions = production.routes()
    seen, cooked = set(), []
    for row in steps:
        if not isinstance(row, dict) or row.keys() != {"id", "action", "values", "reason"}:
            raise ValueError("Each step needs id, action, values and reason")
        key = core.asset_id(row["id"])
        if (
            key in seen
            or row["action"] not in actions
            or row["action"] not in ALLOWED
            or not isinstance(row["values"], dict)
        ):
            raise ValueError("Choose distinct step IDs and supported task actions")
        seen.add(key)
        if "project" in row["values"]:
            raise ValueError("Every step must target this task's project")
        inspect.signature(actions[row["action"]]).bind(project, **row["values"])
        reason = game_art.text(row["reason"], "reason", 1000)
        if not reason:
            raise ValueError("Explain what the step changes")
        cooked.append({**deepcopy(row), "reason": reason})
    plan_id = workflow.identifier(plan_id) if plan_id else uuid.uuid4().hex
    path = game_art.root(project) / "creative-tasks" / (plan_id + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with background.lock(path):
        old = core.read_optional_json(path)
        if old and old.get("request_id"):
            raise ValueError("An executed plan is immutable; save a new plan for further changes")
        row = dict(
            plan_id=plan_id,
            title=game_art.text(title, "title", 120),
            request=game_art.text(request, "request", 4000),
            context_token=context_token,
            steps=cooked,
            questions=questions,
            revision=uuid.uuid4().hex,
            created_utc=workflow.now(),
            status="needs_input" if questions else "ready",
        )
        core.atomic_json(path, row)
    return row


def catalog(project, plan_id=None):
    """Inspect saved task plans and their actual execution progress."""
    root = game_art.root(project) / "creative-tasks"
    paths = (
        [root / (workflow.identifier(plan_id) + ".json")]
        if plan_id
        else sorted(root.glob("*.json"))
    )
    rows = []
    for path in paths:
        row = core.read_optional_json(path)
        if not row:
            raise ValueError("Unknown creative task")
        if row.get("request_id"):
            row["execution"] = workflow.job_status(project, row["request_id"])
        rows.append(row)
    return {"plans": rows}


def execute(project, plan_id, revision):
    """Execute a reviewed task once. Repeated calls return its existing resumable job."""
    path = game_art.root(project) / "creative-tasks" / (workflow.identifier(plan_id) + ".json")
    with background.lock(path):
        row = core.read_optional_json(path)
        if not row or row["revision"] != revision:
            raise ValueError("Task plan changed; inspect the current plan")
        if row.get("request_id"):
            return workflow.job_status(project, row["request_id"])
        if row["questions"]:
            raise ValueError("Resolve the plan's missing decisions before execution")
        if row["context_token"] != context(project)["context_token"]:
            raise ValueError("Project changed since planning; refresh the plan before execution")
        task = background.submit(project, "creative_task", {"plan": row})
        row.update(request_id=task["request_id"], status="submitted")
        core.atomic_json(path, row)
        return task


def run(job, plan):
    from . import production

    results = []
    for index, step in enumerate(plan["steps"]):
        job.update(stage=f"{index + 1}/{len(plan['steps'])} · {step['reason']}", step=step["id"])
        key = "step_" + step["id"]
        cached = job.state.get(key)
        if cached and not cached.get("request_id"):
            result = cached
        else:

            def create():
                return production.routes()[step["action"]](job.project, **step["values"])

            if not cached:
                job.check()
                cached = create()
                if not cached.get("request_id") and cached.get("status") != "completed":
                    raise ValueError("This action did not produce an executable task")
                job.update(**{key: cached})
            result = creations.step(job, key, create) if cached.get("request_id") else cached
        results.append(
            dict(
                id=step["id"],
                action=step["action"],
                request_id=result.get("request_id"),
                status=result.get("status"),
            )
        )
    return {"stage": "Creative task completed", "plan_id": plan["plan_id"], "results": results}
