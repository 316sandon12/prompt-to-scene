"""Named art directions for rooms/regions; visual decisions do not reuse spatial snapshots."""

import uuid
from copy import deepcopy

from . import core, game_art, styles, workflow


def active(project):
    return core.read_optional_json(game_art.root(project) / "active-scene-profile.json") or {}


def read(project, profile_id, revision=None):
    folder = game_art.root(project) / "scene-profiles" / core.asset_id(profile_id)
    row = core.read_optional_json(
        folder / ((workflow.identifier(revision) + ".json") if revision else "current.json")
    )
    if not row:
        raise ValueError("Unknown scene art profile")
    return row


def catalog(project):
    return {
        "active": active(project),
        "profiles": [
            core.read_optional_json(p)
            for p in sorted((game_art.root(project) / "scene-profiles").glob("*/current.json"))
        ],
    }


def save(project, name, profile_id=None, notes="", locks=None):
    """Save this region's current style/reference. Locks: silhouette, palette, proportions,
    materials and detail; values describe concrete traits to preserve, not numeric scores.
    New revisions retain older decisions. Activation is a separate operation.
    """
    from . import art_samples, scene_context

    name = game_art.text(name, "name", 120)
    notes = game_art.text(notes, "notes", 1500)
    if not name:
        raise ValueError("Name this scene art profile")
    locks = locks or {}
    if not isinstance(locks, dict) or locks.keys() - {
        "silhouette",
        "palette",
        "proportions",
        "materials",
        "detail",
    }:
        raise ValueError("Choose silhouette, palette, proportions, materials or detail locks")
    locks = {k: game_art.text(v, k, 800) for k, v in locks.items() if v}
    profile_id = core.asset_id(profile_id) if profile_id else "region_" + uuid.uuid4().hex[:12]
    root = game_art.root(project)
    scene = scene_context.read(project)
    result = dict(
        profile_id=profile_id,
        revision=uuid.uuid4().hex,
        name=name,
        notes=notes,
        locks=locks,
        style=styles.read(project),
        game_art=game_art.configure(project),
        theme=art_samples.theme(project),
        reference=scene.get("reference"),
        scene=(scene.get("snapshot") or {}).get("scene"),
        style_match=core.read_optional_json(root / "style-match.json"),
        updated_utc=workflow.now(),
    )
    core.atomic_json(root / "scene-profiles" / profile_id / (result["revision"] + ".json"), result)
    core.atomic_json(root / "scene-profiles" / profile_id / "current.json", result)
    if active(project).get("profile_id") == profile_id:
        core.atomic_json(
            root / "active-scene-profile.json",
            {k: result[k] for k in ("profile_id", "revision", "name")},
        )
    return result


def activate(project, profile_id, revision=None):
    """Use a region's retained visual direction; recapture location before spatial fitting.

    Does not rewrite existing assets or their frozen generation briefs.
    """
    from . import art_samples, image_assets, scene_context

    row = read(project, profile_id, revision)
    root = game_art.root(project)
    styles.validate(row["style"])
    reference = row.get("reference")
    if reference:
        source, data = image_assets.read_source(reference["path"])
        if image_assets.digest(data) != reference["sha256"]:
            raise ValueError("This region's reference changed; save a new profile")
    # All payloads originate from validated, retained local settings.
    core.atomic_json(root / "art-direction.json", row["style"])
    game_art.configure(project, {k: v for k, v in row["game_art"].items() if k != "schema_version"})
    art_samples.theme(project, {k: row["theme"][k] for k in art_samples.DEFAULT_THEME})
    for filename in ("design-family.json", "style-match.json"):
        path = root / filename
        if path.is_file():
            core.atomic_json(
                root / "scene-profile-history" / (uuid.uuid4().hex + ".json"),
                {"file": filename, "content": core.read_optional_json(path)},
            )
            path.unlink()
    if row.get("style_match"):
        core.atomic_json(root / "style-match.json", row["style_match"])
    scene = dict(
        schema_version=1,
        revision=uuid.uuid4().hex,
        settings=deepcopy(scene_context.DEFAULTS),
        snapshot=None,
        reference=row.get("reference"),
        updated_utc=workflow.now(),
    )
    core.atomic_json(root / "scene-context.json", scene)
    chosen = {k: row[k] for k in ("profile_id", "revision", "name")}
    core.atomic_json(root / "active-scene-profile.json", chosen)
    return {
        **chosen,
        "message": "Art direction selected. Capture the current scene before placement.",
    }


def brief(project):
    choice = active(project)
    if not choice:
        return None
    row = read(project, choice["profile_id"], choice["revision"])
    return {k: deepcopy(row[k]) for k in ("profile_id", "revision", "name", "notes", "locks")}


def preferences(project):
    scope = active(project).get("profile_id")
    rows = core.read_optional_json(game_art.root(project) / "visual-preferences.json") or []
    return [r for r in rows if r.get("profile_id") in {None, scope}]
