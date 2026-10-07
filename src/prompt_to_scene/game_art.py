"""Project game context and reproducible asset briefs, interpreted by the connected AI host."""

from copy import deepcopy

from . import core, registry, styles

VIEWS = {
    "isometric": "Read the silhouette and top surfaces at an oblique game camera angle.",
    "top_down": "Emphasize the top silhouette and large color groups; omit tiny front details.",
    "third_person": "Balance silhouette, construction and readable interaction points.",
    "first_person": "Resolve close surfaces, joins, thickness and contact points without gaps.",
}
CONSTRUCTION = {
    "handcrafted": "Timber joinery, framed panels, shaped crests and restrained metal fittings.",
    "salvaged": "Functional repair plates and reinforcing straps; wear should explain use.",
    "machined": "Inset panels, consistent seams, mounting collars and serviceable fittings.",
}
DEFAULT = {
    "schema_version": 1,
    "gameplay": "",
    "world": "",
    "style_notes": "",
    "view": "third_person",
    "construction": "handcrafted",
    "detail": "auto",
}
ROLES = {"environment", "interactable", "hero"}


def root(project):
    return core.state_root(registry.resolve(project).root)


def text(value, name, limit):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{name} must be text of at most {limit} characters")
    return value.strip()


def configure(project, settings=None):
    path = root(project) / "game-art.json"
    saved = core.read_optional_json(path)
    if settings is None:
        return deepcopy(saved or DEFAULT)
    if not isinstance(settings, dict) or settings.keys() - (DEFAULT.keys() - {"schema_version"}):
        raise ValueError("Use gameplay, world, style_notes, view, construction and detail")
    result = {**DEFAULT, **(saved or {}), **settings}
    for key in ("gameplay", "world", "style_notes"):
        result[key] = text(result[key], key, 2000)
    if (
        not isinstance(result["view"], str)
        or result["view"] not in VIEWS
        or not isinstance(result["construction"], str)
        or result["construction"] not in CONSTRUCTION
    ):
        raise ValueError("Choose a listed view and construction method")
    if not isinstance(result["detail"], str) or result["detail"] not in {
        "auto",
        "readable",
        "balanced",
        "closeup",
    }:
        raise ValueError("Detail must be auto, readable, balanced or closeup")
    core.atomic_json(path, result)
    return result


def saved_plan(project, asset_id):
    return core.read_optional_json(root(project) / "designs" / (core.asset_id(asset_id) + ".json"))


def plan(
    project,
    asset_id,
    description=None,
    role="environment",
    focal_point="",
    recipe_kind=None,
    decisions=None,
):
    """A local design handoff, not a second LLM or an automatic visual assessment."""
    core.asset_id(asset_id)
    if description is None:
        return saved_plan(project, asset_id) or {"asset_id": asset_id, "status": "not_designed"}
    description = text(description, "description", 2000)
    if not description:
        raise ValueError("Describe the intended asset")
    if not isinstance(role, str) or role not in ROLES:
        raise ValueError("Choose environment, interactable or hero")
    if recipe_kind is not None:
        from . import recipes

        if recipe_kind not in recipes.DEFAULTS:
            raise ValueError("Choose a listed recipe or omit recipe_kind for custom modeling")
    focal_point = text(focal_point, "focal_point", 300)
    decisions = deepcopy(decisions) if decisions is not None else {}
    if not isinstance(decisions, dict) or decisions.keys() - {
        "silhouette",
        "structure",
        "materials",
        "story",
        "avoid",
    }:
        raise ValueError("Design decisions: silhouette, structure, materials, story, avoid")
    for key, value in decisions.items():
        decisions[key] = text(value, key, 1200)
    context = configure(project)
    detail = (
        "closeup"
        if role == "hero" or context["view"] == "first_person"
        else "readable"
        if context["view"] == "top_down"
        else "balanced"
    )
    if context.get("detail", "auto") != "auto":
        detail = context["detail"]
    reference = core.read_optional_json(root(project) / "art-brief.json") or {}
    result = {
        "schema_version": 1,
        "asset_id": asset_id,
        "description": description,
        "role": role,
        "focal_point": focal_point,
        "recipe_kind": recipe_kind,
        "method": "recipe" if recipe_kind else "custom_blender",
        "context": context,
        "style": styles.read(project),
        "decisions": decisions,
        "reference": {k: reference[k] for k in ("notes", "image", "sha256") if k in reference},
        "treatment": {
            "construction": context["construction"],
            "detail": detail,
            "emphasize_hardware": role == "interactable",
        },
        "modeling_guidance": [
            VIEWS[context["view"]],
            CONSTRUCTION[context["construction"]],
            "Design primary silhouette, then load-bearing construction, then a few focal details.",
            "The host AI interprets gameplay/world/decisions; filenames are not visual evidence.",
            "Use real thickness, connected supports, consistent material scale and quiet surfaces.",
            "Keep the saved palette and budget. Extra triangles alone do not improve appearance.",
            "Use custom Blender geometry when the described shape exceeds the recipe's vocabulary.",
        ],
        "review_focus": [
            "Recognizable silhouette and use from the saved game-camera direction",
            "Visible construction and story details match this brief",
            "Coherent grain, roughness and accents; no floating trim or noisy striping",
            "Inspect the actual render; this brief is not proof of visual quality",
        ],
    }
    matched = core.read_optional_json(root(project) / "style-match.json")
    if matched:
        result["style_reference"] = {
            "source_token": matched["source_token"],
            "analysis": matched["analysis"],
        }
    if role == "interactable":
        result["modeling_guidance"].append(
            "Make the interaction point readable, preserve moving-part clearance and pivots. "
            "Decorative handles do not implement gameplay; configure interaction separately."
        )
    core.atomic_json(root(project) / "designs" / (asset_id + ".json"), result)
    return result


def for_recipe(project, asset_id, kind):
    saved = saved_plan(project, asset_id)
    if saved:
        if saved.get("recipe_kind") != kind:
            raise ValueError(
                "The saved design calls for custom modeling or another recipe. Follow that design "
                "or update design_asset explicitly before choosing a template."
            )
        return saved
    if not (root(project) / "game-art.json").is_file():
        return None  # Preserve legacy recipes until the project opts into game art direction.
    return plan(project, asset_id, kind, recipe_kind=kind)


def provider_prompt(prompt, design, limit=800):
    """Keep the user's complete request; compact only appended context within the provider limit."""
    if not design:
        return prompt, []
    context = design["context"]
    fields = [
        ("World", context["world"]),
        ("Gameplay", context["gameplay"]),
        ("Style", context["style_notes"]),
        ("Focus", design["focal_point"]),
        ("Shape", design["decisions"].get("silhouette", "")),
        ("Structure", design["decisions"].get("structure", "")),
        ("Materials", design["decisions"].get("materials", "")),
        ("Story", design["decisions"].get("story", "")),
        ("Avoid", design["decisions"].get("avoid", "")),
        ("Reference notes", design["reference"].get("notes", "")),
        ("View", context["view"]),
        ("Craft", context["construction"]),
    ]
    fields = [(k, " ".join(v.split())) for k, v in fields if v]
    remaining = limit - len(prompt)
    allowance = (remaining - sum(len(k) + 4 for k, _ in fields)) // max(1, len(fields))
    if allowance < 8:
        return prompt, [k for k, _ in fields]
    additions, shortened = [], []
    for key, value in fields:
        if len(value) > allowance:
            shortened.append(key)
            value = value[: allowance - 1] + "…"
        additions.append(f"{key}: {value}")
    return prompt + "\n" + "; ".join(additions), shortened
