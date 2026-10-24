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
    image_assets,
    image_provider,
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
        if (
            name in names
            or workflow.inspect_asset(project, name)["current"]["status"] != "unknown"
            or image_assets.catalog(project, name)["assets"]
        ):
            raise ValueError("Choose unique new asset IDs; use part edits for existing assets")
        names.add(name)
        method = row.get("method", "recipe")
        if method not in {"recipe", "custom", "source", "template", "interactive", "image"}:
            raise ValueError("Choose recipe, custom, source, template, interactive or image")
        if method == "image":
            if row.get("position") is not None or row.get("interaction"):
                raise ValueError(
                    "Image artwork goes to the asset library, without 3D placement or interaction"
                )
            source, data = image_assets.read_source(row["source"])
            parameters = row.get("parameters") or {}
            image_assets.settings(row.get("kind", "icon"), **parameters)
            row["source"] = {"path": str(source), "sha256": image_assets.digest(data)}
            row["design"] = image_assets.plan(
                project,
                name,
                row.get("description") or description or name,
                kind=row.get("kind", "icon"),
                **parameters,
            )
            row["method"] = method
            prepared.append(row)
            continue
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
    if (furnish or review_view) and all(row["method"] == "image" for row in prepared):
        raise ValueError(
            "Image-only tasks use image_preview; furnishing/game-camera review requires a model"
        )
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
            if method == "image":
                if previous and previous.get("revision"):
                    return image_assets.publish(job.project, name, previous["revision"])
                path, data = image_assets.read_source(row["source"]["path"])
                if image_assets.digest(data) != row["source"]["sha256"]:
                    raise ValueError("Source image changed after the task was planned")
                return image_assets.import_image(
                    job.project, name, str(path), row["design"]["plan_id"]
                )
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
                job.project,
                asset_ids=[r["asset_id"] for r in items if r["method"] != "image"],
                duplicate=False,
                **furnish,
            ),
        )
    review = None
    if review_view:
        review = step(
            "review_task",
            lambda: quality.start(
                job.project,
                [r for r in items if r["method"] != "image"][-1]["asset_id"],
                view=review_view,
            ),
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
    from . import (
        art_directions,
        art_kits,
        art_samples,
        asset_recommendations,
        creations,
        creative_tasks,
        delivery,
        gameplay,
        image_edits,
        linked_updates,
        project_adapters,
        scene_context,
        visual_assets,
    )

    return {
        "capture_scene_context": scene_context.capture,
        "save_scene_context": scene_context.save,
        "check_scene_fit": scene_context.check_model,
        "task_context": creative_tasks.context,
        "save_creative_task": creative_tasks.save,
        "creative_tasks": creative_tasks.catalog,
        "execute_creative_task": creative_tasks.execute,
        "art_directions": art_directions.catalog,
        "select_art_direction": art_directions.select,
        "compare_art_directions": art_directions.preview,
        "creation_dependencies": linked_updates.dependencies,
        "plan_creation_update": linked_updates.plan,
        "update_creation": linked_updates.execute,
        "creation_updates": linked_updates.catalog,
        "inspect_project_system": project_adapters.inspect_system,
        "prepare_project_adapter": project_adapters.prepare,
        "install_project_adapter": project_adapters.install,
        "adapter_plans": project_adapters.catalog,
        "create_adapter_starter": project_adapters.starter,
        "attach_gameplay": gameplay.attach,
        "delivery_context": delivery.inspect_project,
        "build_game": delivery.build,
        "game_deliveries": delivery.catalog,
        "launch_game": delivery.launch,
        "cleanup_delivery": delivery.cleanup,
        "art_kits": art_kits.catalog,
        "create_art_kit": art_kits.create,
        "gameplay_flows": gameplay.catalog,
        "configure_gameplay": gameplay.configure,
        "project_adapters": gameplay.adapters,
        "recommend_assets": asset_recommendations.start,
        "recommendation_images": asset_recommendations.evidence,
        "save_asset_matches": asset_recommendations.assess,
        "reuse_recommendation": asset_recommendations.reuse,
        "create_game_item": creations.create_item,
        "game_item_example": creations.example,
        "create_game_ui": creations.create_ui,
        "creation_workspace": creations.workspace,
        "view_model": visual_assets.submit,
        "model_view_data": visual_assets.read,
        "plan_image_edit": image_edits.plan,
        "save_art_sample": art_samples.save,
        "art_samples": art_samples.catalog,
        "restore_art_sample": art_samples.restore,
        "art_theme": art_samples.theme,
        "context": authoring.catalog,
        "plan_image": image_assets.plan,
        "import_image": image_assets.import_image,
        "generate_image": image_assets.generate,
        "publish_image": image_assets.publish,
        "image_library": image_assets.catalog,
        "image_preview": image_assets.preview,
        "image_provider": image_provider.configure,
        "image_example": image_assets.example,
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
    "save_scene_context": {
        "inspection_id": "<completed capture_scene_context request_id>",
        "settings": {"fit": "fit", "usage": "Readable herb chest beside the shop counter"},
    },
    "check_scene_fit": {
        "asset_id": "herb_chest",
        "inspection_id": "<fresh capture_scene_context request_id>",
    },
    "create_game_item": {
        "item_id": "forest_potion",
        "model_asset_id": "potion_model",
        "name": "Forest potion",
        "description": "Restores health.",
    },
    "create_game_ui": {
        "screen_id": "inventory",
        "kind": "inventory",
        "item_ids": ["forest_potion"],
        "title": "SATCHEL",
    },
    "plan_image_edit": {
        "asset_id": "forest_potion_icon",
        "revision": "from image_library",
        "rectangle": [0.25, 0.25, 0.5, 0.5],
        "prompt": "A golden leaf seal",
    },
    "save_art_sample": {
        "name": "Forest glaze",
        "category": "model",
        "source": "/absolute/reference.png",
        "notes": "Keep soft edges and jade ceramic",
        "verdict": "accepted",
    },
    "plan_image": {
        "asset_id": "healing_potion",
        "prompt": "A cozy herbalist healing potion icon",
        "kind": "icon",
    },
    "import_image": {
        "asset_id": "healing_potion",
        "source": "/absolute/path/generated.png",
        "plan_id": "<plan_image plan_id>",
    },
    "generate_image": {"plan_id": "<plan_image plan_id>", "allow_remote": False},
    "publish_image": {"asset_id": "healing_potion", "revision": "<retained image revision>"},
    "image_preview": {"asset_id": "healing_potion", "revision": "<retained image revision>"},
    "image_provider": {
        "endpoint": "http://localhost:8189/v1",
        "model": "<your image model>",
        "api_style": "gpt_image",
    },
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
                "image": "source image path + kind (icon/button/panel/portrait/background/texture) "
                "+ optional image settings in parameters",
            }
            if action == "produce"
            else None,
        }
    if operation != "execute" or not isinstance(values or {}, dict):
        raise ValueError("Use search, describe or execute with an object of values")
    inspect.signature(function).bind(project, **(values or {}))
    return function(project, **(values or {}))
