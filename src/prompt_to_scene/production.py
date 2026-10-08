"""One durable request from an AI-authored plan to reusable, playable scene content."""

import inspect
from copy import deepcopy

from . import (
    asset_templates,
    authoring,
    background,
    core,
    development,
    game_art,
    project_library,
    quality,
    recipes,
    scene_dressing,
    sources,
    visual_feedback,
    workflow,
)


def submit(project, items, description="", furnish=None, review_view=None):
    if not isinstance(items, list) or not 1 <= len(items) <= 12:
        raise ValueError("A task contains one to twelve assets")
    description = game_art.text(description, "description", 2000)
    if review_view not in {None, "game", "studio", "front", "back"}:
        raise ValueError("Choose a supported review view or omit it")
    names, prepared = set(), []
    for original in items:
        row = deepcopy(original)
        if not isinstance(row, dict) or row.keys() - {
            "asset_id",
            "method",
            "kind",
            "parameters",
            "script",
            "source",
            "template",
            "version",
            "part_changes",
            "position",
            "interaction",
            "description",
            "decisions",
        }:
            raise ValueError("Unknown asset plan field; describe produce for its contract")
        name = core.asset_id(row["asset_id"])
        if name in names or workflow.inspect_asset(project, name)["current"]["status"] != "unknown":
            raise ValueError("Choose unique new asset IDs; use part edits for existing assets")
        names.add(name)
        method = row.get("method", "recipe")
        if method not in {"recipe", "custom", "source", "template", "interactive"}:
            raise ValueError("Choose recipe, custom, source, template or interactive")
        if row.get("position") is not None:
            core.position_values(row["position"])
        if method == "recipe":
            if row.get("kind") not in recipes.DEFAULTS:
                raise ValueError("Choose a recipe from context, or provide custom Blender code")
            recipes.prepare(row["kind"], row.get("parameters"))
        if method == "custom" and (
            not isinstance(row.get("script"), str) or not row["script"].strip()
        ):
            raise ValueError("The connected AI must provide the modeling script")
        if method == "source":
            row["source"] = sources.validate_source({"path": row["source"]})
        if method == "template":
            template, _ = asset_templates.read(project, row["template"], row.get("version"))
            row["version"] = template["version"]
        if method == "interactive" and row.get("kind") not in development.TEMPLATES:
            raise ValueError("Unknown interaction template")
        if row.get("interaction"):
            # Validate the full command now, before any geometry is built.
            development.interaction_values(name, **row["interaction"])
        row["method"] = method
        row["design"] = game_art.plan(
            project,
            name,
            row.get("description") or description or name,
            recipe_kind=row.get("kind") if method == "recipe" else None,
            role="interactable"
            if row.get("interaction") or method == "interactive"
            else "environment",
            decisions=row.get("decisions"),
        )
        if furnish and row.get("position") is None:
            # Owned new instances are subsequently moved into the room, never duplicated.
            row["position"] = [-30 - len(prepared) * 4, 0, 0]
        prepared.append(row)
    if furnish:
        if not isinstance(furnish, dict) or furnish.keys() - {
            "level_id",
            "room_index",
            "approach",
            "protected_zones",
        }:
            raise ValueError(
                "Furnish needs an existing level_id and optional "
                "room_index/approach/protected_zones"
            )
        core.asset_id(furnish["level_id"])
    return background.submit(
        project,
        "production",
        dict(items=prepared, description=description, furnish=furnish, review_view=review_view),
    )


def run(job, items, description, furnish, review_view):
    def step(key, create):
        task = job.state.get(key)
        if task and workflow.job_status(job.project, task["request_id"])["status"] in {
            "error",
            "cancelled",
        }:
            if task.get("kind"):
                task = background.resume(job.project, task["request_id"])
            else:
                task = None
        if not task:
            job.check()
            task = job.track(create())
        job.update(**{key: task})
        return job.wait(task)

    results = []
    for index, row in enumerate(items):
        name = row["asset_id"]
        job.update(stage="Making " + name, active_asset=name)

        def make():
            method, position = row["method"], row.get("position")
            previous = job.state.get("asset_" + str(index))
            if previous and method != "interactive":
                current = workflow.inspect_asset(job.project, name)["current"]
                if current.get("request_id") != previous["request_id"]:
                    raise ValueError("Asset changed outside this task; keep the current revision")
            if method == "recipe":
                script, recipe = recipes.prepare(
                    row["kind"],
                    row.get("parameters"),
                    style=row["design"]["style"],
                    art_design=row["design"],
                )
                return authoring.submit_recipe(job.project, name, script, recipe, position)
            if method == "custom":
                from . import preparation, project_profiles

                return workflow.submit(
                    job.project,
                    name,
                    row["script"],
                    position,
                    preparation=preparation.options(
                        project_profiles.preparation_defaults(job.project, {"ground": False}),
                        row["design"]["style"]["quality"],
                    ),
                    provenance={"art_design": row["design"]},
                )
            if method == "source":
                return sources.submit(job.project, name, row["source"], position=position)
            if method == "template":
                return asset_templates.instantiate(
                    job.project,
                    row["template"],
                    name,
                    version=row["version"],
                    parameters=row.get("parameters"),
                    part_changes=row.get("part_changes"),
                    position=position,
                    retry_request_id=previous["request_id"] if previous else None,
                )
            return development.interactive(
                job.project,
                row["kind"],
                name,
                position=position,
                color=row["design"]["style"]["palette"]["wood"],
            )

        results.append(step("asset_" + str(index), make))
    # A custom base can refer to a moving/depleted asset later in the same plan.
    # Make the full set available before attaching any gameplay dependencies.
    for index, row in enumerate(items):
        if row.get("interaction"):
            name = row["asset_id"]
            job.update(stage="Connecting gameplay for " + name, active_asset=name)
            step(
                "interaction_" + str(index),
                lambda: development.configure(job.project, name, **row["interaction"]),
            )
    dressing = None
    if furnish:
        dressing = step(
            "furnishing",
            lambda: scene_dressing.submit(
                job.project, asset_ids=[r["asset_id"] for r in items], duplicate=False, **furnish
            ),
        )
    review = None
    if review_view:
        review = step(
            "review_task",
            lambda: quality.start(job.project, items[-1]["asset_id"], view=review_view),
        )
    return {
        "stage": "Ready in the game project",
        "description": description,
        "assets": [
            {"asset_id": r["asset_id"], "request_id": t["request_id"]}
            for r, t in zip(items, results)
        ],
        "dressing": dressing,
        "review": review,
        "appearance_accepted": False,
    }


def task_status(project, request_id, wait_seconds=0):
    """Wait for this exact task, up to 30 seconds; a wait timeout does not cancel it."""
    return workflow.job_status(project, request_id, wait_seconds)


def routes():
    return {
        "context": authoring.catalog,
        "produce": submit,
        "find_assets": project_library.search,
        "reuse_asset": project_library.reuse,
        "find_designs": asset_templates.search,
        "save_design": asset_templates.save,
        "reuse_design": asset_templates.instantiate,
        "review": quality.start,
        "review_images": visual_feedback.evidence,
        "feedback": visual_feedback.save,
        "repair": quality.repair,
        "furnish": scene_dressing.submit,
        "interaction": development.configure,
        "task": task_status,
        "resume": background.resume,
        "cancel": workflow.cancel,
        "play": development.playcheck,
    }


EXAMPLES = {
    "produce": {
        "description": "Matching herbalist furniture",
        "items": [
            {
                "asset_id": "herb_counter",
                "method": "recipe",
                "kind": "table",
                "parameters": {"width": 1.4},
                "description": "Quiet wood grain and visible joinery",
            }
        ],
    },
    "review": {"asset_id": "herb_counter", "view": "game"},
    "furnish": {"level_id": "shop", "asset_ids": ["herb_counter"]},
    "interaction": {
        "asset_id": "ore",
        "kind": "resource",
        "uses": 3,
        "event_id": "ore_mined",
        "label": "Mine",
        "demo_input": False,
    },
    "task": {"request_id": "<returned request_id>", "wait_seconds": 30},
    "save_design": {"name": "shop_counter", "asset_id": "herb_counter", "tags": ["wood"]},
    "reuse_design": {"name": "shop_counter", "asset_id": "new_counter", "family_style": True},
    "feedback": {
        "request_id": "<review request_id>",
        "token": "<review_images token>",
        "observations": "Handle reads clearly; wood grain stays quiet at game distance.",
        "accepted": True,
        "preference": "Keep restrained wood contrast for this family.",
    },
    "find_assets": {
        "query": "cabinet",
        "requirements": {"materials": ["wood"], "uses": ["storage"], "max_triangles": 12000},
    },
}


def dispatch(project, operation="search", action=None, values=None, query=""):
    functions = routes()
    if operation == "search":
        return {
            "actions": [
                {"action": name, "description": function.__doc__ or name.replace("_", " ")}
                for name, function in functions.items()
                if not query or query.lower() in (name + " " + (function.__doc__ or "")).lower()
            ],
            "next": "describe an action, then execute it with values; "
            "the host supplies natural-language understanding",
        }
    if action not in functions:
        raise ValueError("Unknown action; search available workflow actions first")
    function = functions[action]
    if operation == "describe":
        signature = inspect.signature(function)
        return {
            "action": action,
            "parameters": {
                key: {
                    "required": p.default is inspect.Parameter.empty,
                    **({"default": p.default} if p.default is not inspect.Parameter.empty else {}),
                }
                for key, p in signature.parameters.items()
                if key != "project"
            },
            "example": EXAMPLES.get(action),
            "asset_methods": {
                "recipe": "kind + parameters",
                "custom": "script containing bpy",
                "source": "local source path",
                "template": "template + optional version/part_changes",
                "interactive": "door/chest/pickup/resource/switch",
            }
            if action == "produce"
            else None,
        }
    if operation != "execute" or not isinstance(values or {}, dict):
        raise ValueError("Use search, describe or execute with an object of values")
    inspect.signature(function).bind(project, **(values or {}))
    return function(project, **(values or {}))
