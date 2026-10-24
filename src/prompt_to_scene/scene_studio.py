"""Scene reference, temporary placement and targeted correction using retained evidence."""

import json
import uuid
from copy import deepcopy
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from . import background, core, game_art, image_assets, layout, scene_context, workflow


def reference(project, camera_id=""):
    """Capture scene selection, geometry, nearby materials and a real game-camera image.

    Poll task, then save_scene_context(inspection_id). No asset or paid generation is started.
    A missing/ambiguous camera fails explicitly; choose camera_id from capture_scene_context.
    """
    camera_id = game_art.text(camera_id, "camera_id", 256)
    return native(project, {"mode": "reference", "camera_id": camera_id})


def native(project, values):
    return workflow.action(project, "scene_stage", values={"scene_json": json.dumps(values)})


def read(project, plan_id):
    row = core.read_optional_json(
        game_art.root(project) / "scene-trials" / (workflow.identifier(plan_id) + ".json")
    )
    if not row:
        raise ValueError("Unknown scene preview")
    return row


def write(project, row):
    core.atomic_json(game_art.root(project) / "scene-trials" / (row["plan_id"] + ".json"), row)
    return row


def catalog(project, asset_id=None):
    if asset_id:
        core.asset_id(asset_id)
    rows = [
        core.read_optional_json(p)
        for p in sorted(
            (game_art.root(project) / "scene-trials").glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    ]
    rows = [r for r in rows if not asset_id or r["asset_id"] == asset_id][:20]
    for row in rows:
        for operation in ("adopt", "undo"):
            if row.get(operation):
                row[operation] = workflow.job_status(project, row[operation]["request_id"])
    return {"previews": rows}


def preview_model(
    project,
    asset_id,
    inspection_id,
    object_id=None,
    placement="surface",
    resize=False,
    replace_target=False,
):
    """Preview an imported model on a surface or inside a placeholder, without changing it.

    The saved scene target/camera and fresh inspection must agree. resize only shrinks uniformly;
    gameplay minimum size, clearance and scale locks are enforced. replace_target explicitly
    hides the placeholder during preview/adoption; otherwise it stays visible. Poll this task
    then scene_preview_images(plan_id). Adoption/undo are separate guarded operations.
    """
    from . import asset_requirements, scene_profiles

    core.asset_id(asset_id)
    if placement not in {"surface", "volume"} or any(
        type(v) is not bool for v in (resize, replace_target)
    ):
        raise ValueError("Choose surface/volume and boolean resize/replace_target")
    if replace_target and placement != "volume":
        raise ValueError("Replacing a placeholder uses volume placement")
    state = scene_context.inspection(project, inspection_id)
    brief = scene_context.brief(project)
    if not brief or not brief["target"] or not brief["camera"]:
        raise ValueError("Capture a target and game camera first")
    if state["scene"] != brief["scene"]:
        raise ValueError("Scene changed; capture the target again")
    target, camera = brief["target"], brief["camera"]
    current = {o["id"]: o for o in [*state["context"], *state.get("selected_context", [])]}
    if current.get(target["id"]) != target or camera not in state.get("cameras", []):
        raise ValueError("Target or camera changed; capture the target again")
    choices = [
        o
        for o in state["assets"]
        if o["asset_id"] == asset_id and (not object_id or o["id"] == object_id)
    ]
    if len(choices) != 1:
        raise ValueError("Choose one model instance by object_id")
    source = choices[0]
    if source["id"] == target["id"]:
        raise ValueError("Choose a target separate from the generated model")
    info = workflow.inspect_asset(project, asset_id)
    if info["current"].get("status") != "imported":
        raise ValueError("Wait for the current model import")
    limits = brief["max_size_m"]
    size = [b - a for a, b in zip(source["bounds_min"], source["bounds_max"])]
    target_size = [b - a for a, b in zip(target["bounds_min"], target["bounds_max"])]
    up = 1 if brief["engine"] == "unity" else 2
    if placement == "volume":
        limits = [min(target_size[i], limits[i]) if limits else target_size[i] for i in range(3)]
    elif resize:
        limits = [
            min(target_size[i], limits[i])
            if limits and i != up
            else limits[i]
            if limits
            else target_size[i]
            if i != up
            else max(size[i], 0.001)
            for i in range(3)
        ]
    factor = (
        min([1, *[limits[i] / max(size[i], 0.000001) for i in range(3)]])
        if limits and resize
        else 1
    )
    if limits and any(size[i] * factor > limits[i] + 0.002 for i in range(3)):
        raise ValueError("Model exceeds the target; enable uniform fit or choose a larger target")
    center = [(a + b) / 2 for a, b in zip(target["bounds_min"], target["bounds_max"])]
    center[up] = (
        target["bounds_max"][up] if placement == "surface" else target["bounds_min"][up]
    ) + size[up] * factor / 2
    old_center = [(a + b) / 2 for a, b in zip(source["bounds_min"], source["bounds_max"])]
    position = [center[i] - (old_center[i] - source["position"][i]) * factor for i in range(3)]
    posed = layout.pose(
        source, position, source["rotation"], [s * factor for s in source["scale"]], brief["engine"]
    )
    row = layout.placement(source, posed)
    physical = {**state, "context": [o for o in state["context"] if o.get("has_collision", True)]}
    layout.check_placements(physical, [row], target["id"])
    usage = asset_requirements.save(project, asset_id)
    asset_requirements.validate_placement(
        usage, posed, physical, {source["id"], target["id"]}, factor
    )
    frozen_parts = ((info.get("metadata") or {}).get("report") or {}).get("parts", {})
    if factor != 1 and any(p.get("locks", {}).get("geometry") for p in frozen_parts.values()):
        raise ValueError("Model contains locked geometry; preview without resizing")
    result = dict(
        plan_id=uuid.uuid4().hex,
        kind="model",
        scene=state["scene"],
        asset_id=asset_id,
        model_revision=info["current"]["request_id"],
        camera_id=camera["id"],
        camera=camera,
        target=target,
        source=source,
        placement=row,
        replace_target=replace_target,
        requirements=usage,
        clearance_m=usage["settings"]["clearance_m"],
        scene_profile=scene_profiles.brief(project),
        scale_factor=factor,
        framing=scene_context.projected_bounds(posed, camera),
        created_utc=workflow.now(),
        brief_revision=brief["revision"],
    )
    write(project, result)
    task = background.submit(project, "scene_trial", {"plan_id": result["plan_id"]}, asset_id)
    path = game_art.root(project) / "scene-trials" / (result["plan_id"] + ".json")
    with background.lock(path):
        saved = read(project, result["plan_id"])
        saved["task"] = task
        write(project, saved)
    return {**task, "plan_id": result["plan_id"], "scale_factor": factor}


def run(job, plan_id):
    row = read(job.project, plan_id)
    for stage in ("before", "trial"):
        job.check()
        task = job.state.get(stage)
        if not task:
            task = native(job.project, {**row, "mode": stage})
            job.update(**{stage: task})
        result = job.wait(task)
        path = game_art.root(job.project) / "scene-trials" / (plan_id + ".json")
        with background.lock(path):
            row = read(job.project, plan_id)
            if row.get("discarded"):
                raise InterruptedError("Preview was discarded")
            row[stage] = result["request_id"]
            write(job.project, row)
    return {
        "plan_id": plan_id,
        "asset_id": row["asset_id"],
        "message": "Compare the two real game-camera images, then adopt or discard.",
    }


def evidence(project, plan_id):
    """Actual reference/trial pixels; compare before adopting. No automatic beauty verdict."""
    row = read(project, plan_id)
    images = []
    for stage in ("before", "trial") if row["kind"] == "model" else ("scene", "sizes", "ui"):
        if row["kind"] == "model":
            state = workflow.job_status(project, row.get(stage, "0" * 32))
            if state["status"] != "completed":
                raise ValueError("Wait for both game-camera captures")
            path = game_art.root(project) / "previews" / (row[stage] + ".png")
        else:
            path = game_art.root(project) / "scene-image-previews" / plan_id / (stage + ".png")
        if not path.is_file() or path.stat().st_size > 10 * 1024**2:
            raise ValueError("Preview image missing or too large")
        images.append(
            {"stage": stage, "path": str(path), "sha256": image_assets.digest(path.read_bytes())}
        )
    return {
        "plan_id": plan_id,
        "kind": row["kind"],
        "asset_id": row["asset_id"],
        "images": images,
        "display_size_px": row.get("display_size_px"),
        "report": row.get("report"),
        "note": "Image overlays are flat layout previews; model images use the editor camera. "
        "Inspect the actual game for motion, input and occlusion.",
    }


def act(project, plan_id, mode="adopt"):
    """Adopt, discard or undo a preview. Refuses stale assets, scene poses and usage settings."""
    path = game_art.root(project) / "scene-trials" / (workflow.identifier(plan_id) + ".json")
    if not path.is_file():
        raise ValueError("Unknown scene preview")
    with background.lock(path):
        return _act(project, plan_id, mode)


def _act(project, plan_id, mode):
    from . import asset_requirements, scene_profiles

    if mode not in {"adopt", "undo", "discard"}:
        raise ValueError("Choose adopt, undo or discard")
    row = read(project, plan_id)
    if mode == "discard":
        if row.get("adopt") and workflow.job_status(project, row["adopt"]["request_id"])[
            "status"
        ] not in {"error", "cancelled"}:
            raise ValueError("Undo an adopted placement first")
        row["discarded"] = True
        if row.get("task"):
            workflow.cancel(project, row["task"]["request_id"])
        return write(project, row)
    if row.get("discarded"):
        raise ValueError("This preview was discarded")
    if mode == "adopt":
        evidence(project, plan_id)
        if row.get("scene_profile") != scene_profiles.brief(project):
            raise ValueError("Scene art profile changed; prepare another preview")
        if (row.get("requirements") or {}).get("revision") != asset_requirements.save(
            project, row["asset_id"]
        )["revision"]:
            raise ValueError("Usage requirements changed; prepare another preview")
    previous = row.get(mode)
    if previous:
        state = workflow.job_status(project, previous["request_id"])
        if state["status"] not in {"error", "cancelled"}:
            return state
    if mode == "adopt" and row.get("undo"):
        raise ValueError("This preview was undone; prepare another one")
    if mode == "undo":
        if (
            not row.get("adopt")
            or workflow.job_status(project, row["adopt"]["request_id"])["status"] != "completed"
        ):
            raise ValueError("Wait for adoption before undoing")
    if row["kind"] == "model":
        task = native(project, {**row, "mode": mode})
    else:
        current = core.read_optional_json(
            game_art.root(project) / "image-receipts" / (row["asset_id"] + ".json")
        )
        current_revision = (current or {}).get("revision")
        if mode == "undo":
            if not row["previous_revision"]:
                raise ValueError("This was the first import; no earlier image revision to restore")
            if current_revision != row["image_revision"]:
                raise ValueError("Image changed after adoption; undo was not applied")
            revision = row["previous_revision"]
        else:
            if current_revision != row["previous_revision"]:
                raise ValueError("Image changed; prepare another preview")
            revision = row["image_revision"]
        task = image_assets.publish(project, row["asset_id"], revision)
    row[mode] = task
    write(project, row)
    return task


def preview_image(
    project, asset_id, revision, display_size_px=None, position=None, text="Sample text"
):
    """Show a retained image at game size over the scene reference, plus 32/64/128px and UI views.

    position is the normalized top-left. Uses contained proportions and true alpha. The UI view
    stretches nine-slice panels, outlines the text safe area and checks declared state variants.
    No image generation or engine import; adopt with scene_preview_action after reviewing.
    """
    from . import art_samples, asset_requirements, scene_profiles

    manifest, folder = image_assets.read_revision(project, asset_id, revision)
    scene = scene_context.brief(project)
    reference_image = (scene or {}).get("reference")
    if not reference_image:
        raise ValueError("Capture a scene reference before previewing in context")
    config = manifest["settings"]
    display = display_size_px or scene["settings"]["display_size_px"] or [64, 64]
    scene_context.numbers(display, 2, 1, 2048, "display_size_px")
    if any(int(n) != n for n in display):
        raise ValueError("Display dimensions use whole pixels")
    display = list(map(int, display))
    position = [0.5, 0.5] if position is None else position
    scene_context.numbers(position, 2, 0, 1, "position")
    text = game_art.text(text, "text", 120)
    source = image_assets.decode((folder / "image.png").read_bytes())
    reference = image_assets.decode(Path(reference_image["path"]).read_bytes())
    usage = asset_requirements.save(project, asset_id)
    plan_id = uuid.uuid4().hex
    output = game_art.root(project) / "scene-image-previews" / plan_id
    sample = reference.copy()
    resample = Image.Resampling.NEAREST if config["pixel_art"] else Image.Resampling.LANCZOS
    sized = ImageOps.contain(source, tuple(display), resample)
    xy = (round(position[0] * reference.width), round(position[1] * reference.height))
    if xy[0] + display[0] > reference.width or xy[1] + display[1] > reference.height:
        raise ValueError(
            "Display rectangle extends beyond the captured frame; reduce it or move it"
        )
    output.mkdir(parents=True)
    sample.alpha_composite(
        sized, (xy[0] + (display[0] - sized.width) // 2, xy[1] + (display[1] - sized.height) // 2)
    )
    sample.save(output / "scene.png")
    theme = art_samples.theme(project)
    sizes = Image.new("RGBA", (544, 212), theme["background"])
    draw = ImageDraw.Draw(sizes)
    for x, n in zip((24, 172, 336), (32, 64, 128)):
        draw.rounded_rectangle((x - 6, 38, x + n + 6, 38 + n + 12), radius=6, fill=theme["surface"])
        sizes.alpha_composite(ImageOps.contain(source, (n, n), resample), (x, 44))
        draw.text((x, 18), str(n) + " px", fill=theme["text"])
    sizes.save(output / "sizes.png")
    ui_width = max(576, config["border"][0] + config["border"][2] + 1)
    ui_height = max(240, config["border"][1] + config["border"][3] + 1)
    ui = Image.new("RGBA", (ui_width + 64, ui_height + 80), theme["background"])
    if config["kind"] in {"panel", "button"}:
        panel = nine_slice(source, (ui_width, ui_height), config["border"], resample)
        ui.alpha_composite(panel, (32, 40))
    else:
        panel = ImageOps.contain(source, (128, 128), resample)
        ui.alpha_composite(panel, (48, 80))
    safe = usage["settings"]["safe_area"]
    box = [
        round(32 + safe[0] * ui_width),
        round(40 + safe[1] * ui_height),
        round(32 + (safe[0] + safe[2]) * ui_width),
        round(40 + (safe[1] + safe[3]) * ui_height),
    ]
    draw = ImageDraw.Draw(ui)
    draw.rectangle(box, outline=theme["accent"], width=1)
    # The preview font is diagnostic; final localized text is owned by the game UI.
    try:
        draw.text((box[0] + 6, box[1] + 6), text, fill=theme["text"])
    except UnicodeEncodeError:
        draw.text((box[0] + 6, box[1] + 6), "Sample text", fill=theme["text"])
    ui.save(output / "ui.png")
    current = core.read_optional_json(
        game_art.root(project) / "image-receipts" / (asset_id + ".json")
    )
    required = usage["settings"]["states"]
    states = {
        s: bool(
            core.read_optional_json(
                game_art.root(project)
                / "image-receipts"
                / ((asset_id if s == "normal" else asset_id + "_" + s) + ".json")
            )
        )
        for s in required
    }
    states["normal"] = True
    result = dict(
        plan_id=plan_id,
        kind="image",
        asset_id=asset_id,
        image_revision=revision,
        previous_revision=(current or {}).get("revision"),
        display_size_px=display,
        position=position,
        requirements=usage,
        scene_profile=scene_profiles.brief(project),
        created_utc=workflow.now(),
        brief_revision=scene["revision"],
        report={
            "fit": scene_context.check_image(source, {**manifest["plan"], "scene_context": scene}),
            "states": states,
            "safe_area": safe,
            "text": "Preview font only; inspect actual localized game text",
        },
    )
    return write(project, result)


def nine_slice(source, size, border, resample):
    left, t, r, b = border
    if left + r >= size[0] or t + b >= size[1]:
        raise ValueError("Preview too small for nine-slice borders")
    result = Image.new("RGBA", size)
    sx, sy = [0, left, source.width - r, source.width], [0, t, source.height - b, source.height]
    dx, dy = [0, left, size[0] - r, size[0]], [0, t, size[1] - b, size[1]]
    for i in range(3):
        for j in range(3):
            if sx[i + 1] > sx[i] and sy[j + 1] > sy[j]:
                tile = source.crop((sx[i], sy[j], sx[i + 1], sy[j + 1]))
                result.paste(
                    tile.resize((dx[i + 1] - dx[i], dy[j + 1] - dy[j]), resample), (dx[i], dy[j])
                )
    return result


def pad_image(project, asset_id, revision, margin=None):
    """Prepare a corrected icon/portrait revision with transparent padding; does not publish.

    Preserves proportions, the retained design and prior revision. Pixel art is never blurred.
    Use preview_scene_image for the resulting revision, then adopt or discard.
    """
    manifest, folder = image_assets.read_revision(project, asset_id, revision)
    config = manifest["settings"]
    if not config["transparent"] or config["kind"] not in {"icon", "portrait"}:
        raise ValueError("Padding repair supports transparent icons and portraits")
    scene = manifest["plan"].get("scene_context") or scene_context.brief(project)
    margin = (
        scene["settings"]["image_margin"]
        if margin is None and scene
        else 0.08
        if margin is None
        else margin
    )
    scene_context.numbers([margin], 1, 0, 0.4, "margin")
    source = image_assets.decode((folder / "image.png").read_bytes())
    box = source.getchannel("A").getbbox()
    if not box:
        raise ValueError("Image is empty")
    crop = source.crop(box)
    available = (
        max(1, int(source.width * (1 - 2 * margin))),
        max(1, int(source.height * (1 - 2 * margin))),
    )
    factor = min(1, available[0] / crop.width, available[1] / crop.height)
    if config["pixel_art"] and factor < 1:
        raise ValueError(
            "Padding needs to shrink pixel art; increase the canvas explicitly instead"
        )
    crop = crop.resize(
        (max(1, int(crop.width * factor)), max(1, int(crop.height * factor))),
        Image.Resampling.LANCZOS,
    )
    output = Image.new("RGBA", source.size)
    output.paste(crop, ((source.width - crop.width) // 2, (source.height - crop.height) // 2))
    design = deepcopy(manifest["plan"])
    design.pop("region_edit", None)
    design["plan_id"] = uuid.uuid4().hex
    design["padding_repair"] = {"source_revision": revision, "margin": margin}
    if scene:
        design["scene_context"] = deepcopy(scene)
        design["scene_context"]["settings"]["image_margin"] = margin
    directory = game_art.root(project) / "image-plans" / design["plan_id"]
    core.atomic_json(directory / "plan.json", design)
    output.save(directory / "padded.png")
    return image_assets.import_image(
        project, asset_id, str(directory / "padded.png"), design["plan_id"], preview_only=True
    )


def remember(project, plan_id, notes, verdict="accepted"):
    """Save the viewed result as this region's accepted/avoid example, with a concrete reason."""
    from . import art_samples, scene_profiles

    row = read(project, plan_id)
    profile = (row.get("scene_profile") or {}).get("profile_id")
    if profile != scene_profiles.active(project).get("profile_id"):
        raise ValueError("Scene art profile changed; switch back before saving this example")
    images = evidence(project, plan_id)["images"]
    if row["kind"] == "image":
        manifest, folder = image_assets.read_revision(
            project, row["asset_id"], row["image_revision"]
        )
        path = str(folder / "image.png")
        category = "icon" if manifest["settings"]["kind"] == "icon" else "ui"
    else:
        if (
            workflow.inspect_asset(project, row["asset_id"])["current"].get("request_id")
            != row["model_revision"]
        ):
            raise ValueError("Model changed; prepare a new preview")
        path = images[-1]["path"]
        category = "model"
    sample_id = (
        "scene_"
        + image_assets.digest((str(profile) + ":" + category + ":" + row["asset_id"]).encode())[:16]
    )
    return art_samples.save(project, row["asset_id"], category, path, notes, verdict, sample_id)


def repair_part(project, plan_id, part, changes):
    """Change one unlocked part of the exact previewed model; inspect pixels before choosing.

    Only color/roughness and local scale/offset are supported here. Existing part locks are
    enforced by the authoring pipeline. The result is a retained revision; restore_asset can
    restore its predecessor. Capture and preview the new revision before accepting it.
    """
    from . import authoring, parts, scene_profiles

    row = read(project, plan_id)
    if row["kind"] != "model":
        raise ValueError("Choose a model preview")
    evidence(project, plan_id)
    info = workflow.inspect_asset(project, row["asset_id"])
    if info["current"].get("request_id") != row["model_revision"]:
        raise ValueError("Model changed; preview its current revision")
    if row.get("scene_profile") != scene_profiles.brief(project):
        raise ValueError("Scene art profile changed; prepare another preview")
    if (
        not isinstance(changes, dict)
        or not changes
        or changes.keys() - {"color", "roughness", "scale", "offset"}
    ):
        raise ValueError("Change color, roughness, local scale or local offset")
    profile = scene_profiles.brief(project) or {}
    locks = profile.get("locks", {})
    if ("color" in changes and locks.get("palette")) or (
        "roughness" in changes and locks.get("materials")
    ):
        raise ValueError("This scene profile locks the material appearance; edit that rule first")
    if {"scale", "offset"} & changes.keys() and (
        locks.get("proportions") or locks.get("silhouette")
    ):
        raise ValueError("This scene profile locks the shape; edit that rule first")
    metadata = info.get("metadata") or {}
    if part == "all":
        raise ValueError("Choose one named part")
    task = (authoring.edit_part if metadata.get("recipe") else parts.edit)(
        project, row["asset_id"], part, changes
    )
    row["part_repair"] = task
    write(project, row)
    return task


def restore_part(project, plan_id):
    """Restore the version before this preview's part repair; refuses unrelated later edits."""
    row = read(project, plan_id)
    current = workflow.inspect_asset(project, row["asset_id"])["current"]
    if not row.get("part_repair") or current.get("request_id") != row["part_repair"]["request_id"]:
        raise ValueError(
            "Model changed outside this repair; choose the intended version from history"
        )
    return workflow.restore(project, row["asset_id"], row["model_revision"])
