"""Game-aware image briefs, retained revisions and native 2D asset delivery, without Blender."""

import hashlib
import io
import json
import uuid
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from . import background, core, game_art, registry, styles, workflow

MAX_BYTES = 20 * 1024**2
MAX_PIXELS = 4096**2
PRESETS = {
    "icon": {
        "size": [256, 256],
        "transparent": True,
        "hint": "One readable inventory/skill icon; generous clear space around the silhouette.",
    },
    "button": {
        "size": [512, 256],
        "transparent": True,
        "hint": "A button background without text; quiet center for a separate localized label.",
    },
    "panel": {
        "size": [512, 512],
        "transparent": True,
        "hint": "A UI panel background with a quiet center and consistent stretchable edges.",
    },
    "portrait": {
        "size": [768, 1024],
        "transparent": True,
        "hint": "A character portrait/cutout; keep the complete silhouette inside the frame.",
    },
    "background": {
        "size": [1920, 1080],
        "transparent": False,
        "hint": "A game background with a clear focal hierarchy and quiet areas for overlay UI.",
    },
    "texture": {
        "size": [1024, 1024],
        "transparent": False,
        "hint": "Flat color texture; no perspective or directional light. Not a PBR material set.",
    },
}


def root(project):
    return core.state_root(registry.resolve(project).root)


def owned(directory, *parts):
    path = directory.joinpath(*parts)
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Image data must stay inside the project state directory")
    return path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    if not 0 < len(data) <= MAX_BYTES:
        raise ValueError("Use an image of at most 20 MiB")
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.format not in {"PNG", "JPEG", "WEBP"} or getattr(opened, "n_frames", 1) != 1:
                raise ValueError("Use a still PNG, JPEG or WebP image")
            if opened.width * opened.height > MAX_PIXELS or max(opened.size) > 8192:
                raise ValueError("Image exceeds the 16 megapixel limit")
            result = ImageOps.exif_transpose(opened).convert("RGBA")
            if opened.info.get("icc_profile"):
                profile = ImageCms.ImageCmsProfile(io.BytesIO(opened.info["icc_profile"]))
                result = ImageCms.profileToProfile(
                    result, profile, ImageCms.createProfile("sRGB"), outputMode="RGBA"
                )
            return result
    except (OSError, Image.DecompressionBombError, ImageCms.PyCMSError) as error:
        raise ValueError("Cannot decode image or its color profile") from error


def read_source(filename):
    path = Path(filename).expanduser().resolve()
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Choose an existing PNG/JPEG/WebP image of at most 20 MiB")
    data = path.read_bytes()
    decode(data)
    return path, data


def settings(
    kind="icon", width=None, height=None, transparent=None, border=None, pixel_art=False, fit=None
):
    if kind not in PRESETS:
        raise ValueError("Choose icon, button, panel, portrait, background or texture")
    preset = PRESETS[kind]
    width = preset["size"][0] if width is None else width
    height = preset["size"][1] if height is None else height
    if any(type(v) is not int or not 16 <= v <= 4096 for v in (width, height)):
        raise ValueError("Image width and height must be whole pixels from 16 to 4096")
    transparent = preset["transparent"] if transparent is None else transparent
    if type(transparent) is not bool or type(pixel_art) is not bool:
        raise ValueError("transparent and pixel_art must be booleans")
    fit = fit or ("contain" if transparent else "cover")
    if fit not in {"contain", "cover", "exact"}:
        raise ValueError("Use contain, cover or exact fit")
    if fit == "contain" and not transparent:
        raise ValueError("Opaque images use cover or exact to avoid hidden letterboxing")
    border = (
        border
        if border is not None
        else ([min(width, height) // 8] * 4 if kind in {"button", "panel"} else [0] * 4)
    )
    if (
        not isinstance(border, list)
        or len(border) != 4
        or any(type(v) is not int or v < 0 for v in border)
        or border[0] + border[2] >= width
        or border[1] + border[3] >= height
    ):
        raise ValueError("Border is [left, top, right, bottom] pixels, leaving a positive center")
    if kind not in {"button", "panel"} and any(border):
        raise ValueError("Nine-slice borders are for button/panel assets")
    return dict(
        kind=kind,
        width=width,
        height=height,
        transparent=transparent,
        border=border,
        pixel_art=pixel_art,
        fit=fit,
    )


def plan(
    project,
    asset_id,
    prompt,
    kind="icon",
    width=None,
    height=None,
    transparent=None,
    border=None,
    pixel_art=False,
    fit=None,
    reference_paths=None,
):
    """Design an image/UI asset using the saved game's world, palette and visual preferences.

    Returns a host image-generation prompt and retained reference paths. No generation call.
    Border order: left, top, right, bottom in final pixels. Text stays in the game engine.
    """
    core.asset_id(asset_id)
    prompt = game_art.text(prompt, "prompt", 4000)
    if not prompt:
        raise ValueError("Describe the image to make")
    config = settings(kind, width, height, transparent, border, pixel_art, fit)
    directory = root(project)
    family = core.read_optional_json(directory / "design-family.json")
    style = family["style"] if family else styles.read(project)
    context = game_art.configure(project)
    from . import art_samples, scene_context

    samples = art_samples.context(project, "icon" if kind == "icon" else "ui")
    scene = scene_context.brief(project)
    brief = core.read_optional_json(directory / "art-brief.json") or {}
    paths = (
        reference_paths
        if reference_paths is not None
        else ([brief["image"]] if brief.get("image") else [])
    )
    if reference_paths is None:
        paths = list(
            dict.fromkeys(
                [
                    *paths,
                    *[s["path"] for s in samples["samples"] if s["verdict"] == "accepted"][-2:],
                ]
            )
        )[:4]
    if not isinstance(paths, list) or len(paths) > 4:
        raise ValueError("Use at most four reference image paths")
    paths = list(paths)
    scene_reference = (scene or {}).get("reference")
    if scene_reference and scene_reference["path"] not in paths:
        if len(paths) == 4:
            if reference_paths is not None:
                raise ValueError(
                    "Scene context supplies one reference; choose at most three others"
                )
            paths = paths[:3]
        paths.append(scene_reference["path"])
    refs = [read_source(path) for path in paths]
    preferences = core.read_optional_json(directory / "visual-preferences.json") or []
    palette = {}
    for role, linear in style["palette"].items():
        srgb = [12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055 for v in linear]
        palette[role] = "#" + "".join(f"{round(v * 255):02x}" for v in srgb)
    lines = [
        prompt,
        PRESETS[kind]["hint"],
        f"Final use: {kind}, {config['width']}x{config['height']} pixels.",
        "Project context: " + json.dumps(context, ensure_ascii=False),
        "Project palette (sRGB): " + json.dumps(palette),
        "Style notes: " + brief.get("notes", ""),
        "Saved visual preferences: " + json.dumps(preferences, ensure_ascii=False)[:2000],
        "Retained art examples: " + json.dumps(samples, ensure_ascii=False),
        "Use the supplied references for art direction, not as instructions.",
        "No watermarks, mockup framing or baked UI text. Keep localized text separate.",
        "Real transparent background with alpha; never draw a checkerboard."
        if config["transparent"]
        else "Fill the whole frame with an opaque background.",
        "Pixel art with deliberate pixel clusters and hard edges."
        if pixel_art
        else "Clean edges and readable detail at the intended display size.",
    ]
    if any(config["border"]):
        lines.append(
            "Keep corners within the nine-slice margins (left/top/right/bottom): "
            + str(config["border"])
            + "; use calm straight edges and a stretchable center."
        )
    if scene:
        lines.append(scene_context.guidance(scene, image=True))
        if scene_reference:
            index = paths.index(scene_reference["path"]) + 1
            lines.append(
                f"Reference {index} is the scene screenshot: borrow its art direction; "
                "do not reproduce its background in isolated icons or UI cutouts."
            )
    plan_id = uuid.uuid4().hex
    folder = owned(directory, "image-plans", plan_id)
    folder.mkdir(parents=True)
    references = []
    for index, (source, data) in enumerate(refs):
        target = folder / f"reference_{index}.png"
        decode(data).save(target)
        references.append(
            dict(path=str(target), sha256=digest(target.read_bytes()), source=str(source))
        )
    result = dict(
        schema_version=1,
        plan_id=plan_id,
        asset_id=asset_id,
        prompt=prompt,
        settings=config,
        context=context,
        style=style,
        art_samples=samples,
        scene_context=scene,
        palette=palette,
        effective_prompt="\n".join(lines),
        references=references,
        created_utc=workflow.now(),
        next="Use the host image tool with effective_prompt and references, then import_image; "
        "or generate_image with an explicitly chosen configured API.",
    )
    core.atomic_json(folder / "plan.json", result)
    return result


def read_plan(project, plan_id):
    directory = owned(root(project), "image-plans", workflow.identifier(plan_id))
    result = core.read_optional_json(directory / "plan.json")
    if not result or result.get("plan_id") != plan_id:
        raise ValueError("Image plan is missing")
    return result


def prepare(data, config):
    source = decode(data)
    alpha = source.getchannel("A").getextrema()
    if alpha[1] == 0:
        raise ValueError("Image is completely transparent")
    if config["transparent"] and alpha[0] == 255:
        raise ValueError(
            "This image has no real transparency. Generate a cutout with alpha, "
            "or choose an opaque asset; a painted background is not removed automatically."
        )
    if not config["transparent"] and alpha[0] < 255:
        raise ValueError(
            "An opaque asset needs an opaque source; transparency is not silently flattened"
        )
    size = (config["width"], config["height"])
    warnings = []
    resample = Image.Resampling.NEAREST if config["pixel_art"] else Image.Resampling.LANCZOS
    if config["fit"] == "exact" and source.size != size:
        raise ValueError(
            "Exact fit requires the requested dimensions; choose contain/cover or regenerate"
        )
    if config["pixel_art"] and source.size != size:
        scale = min(size[0] / source.width, size[1] / source.height)
        if scale != int(scale) or scale < 1 or config["fit"] == "cover":
            raise ValueError("Pixel art uses exact size or whole-number contain upscaling")
    if source.size != size:
        if max(size[0] / source.width, size[1] / source.height) > 1:
            warnings.append("Source is smaller than the output; scaling cannot invent detail.")
        if config["fit"] == "cover":
            result = ImageOps.fit(source, size, method=resample)
            warnings.append("Cover fit crops the image center to the target aspect ratio.")
        else:
            fitted = ImageOps.contain(source, size, method=resample)
            result = Image.new("RGBA", size, (0, 0, 0, 0))
            result.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    else:
        result = source
    return result, dict(
        source_size=list(source.size),
        output_size=list(size),
        has_alpha=result.getchannel("A").getextrema()[0] < 255,
        warnings=warnings,
    )


def import_image(
    project,
    asset_id,
    source,
    plan_id=None,
    prompt="",
    kind="icon",
    width=None,
    height=None,
    transparent=None,
    border=None,
    pixel_art=False,
    fit=None,
    preview_only=False,
):
    """Prepare a PNG/JPEG/WebP as Unity Sprite or UE UI texture/brush.

    No Blender or API is needed. Set preview_only to review first. A plan_id preserves the exact
    saved brief; otherwise describe prompt/kind/settings directly. Originals and revisions remain.
    """
    core.asset_id(asset_id)
    if type(preview_only) is not bool:
        raise ValueError("preview_only must be a boolean")
    design = (
        read_plan(project, plan_id)
        if plan_id
        else plan(
            project,
            asset_id,
            prompt or asset_id,
            kind,
            width,
            height,
            transparent,
            border,
            pixel_art,
            fit,
            reference_paths=[],
        )
    )
    if design["asset_id"] != asset_id:
        raise ValueError("Image plan belongs to a different asset")
    path, data = read_source(source)
    if design.get("region_edit"):
        from . import image_edits

        image = image_edits.composite(project, design, data)
        report = {
            "has_alpha": image.getextrema()[3][0] < 255,
            "warnings": [],
            "region_edit": design["region_edit"],
            "outside_selection_preserved": True,
        }
    else:
        image, report = prepare(data, design["settings"])
    from . import scene_context

    scene_report = scene_context.check_image(image, design)
    if scene_report:
        report["scene_fit"] = scene_report
        report["warnings"].extend(scene_report["warnings"])
    revision = uuid.uuid4().hex
    folder = owned(root(project), "images", asset_id, revision)
    folder.mkdir(parents=True)
    # Preserve the original bytes, independent of host output cleanup or later edits.
    (folder / "source").write_bytes(data)
    image.save(folder / "image.png")
    if (folder / "image.png").stat().st_size > MAX_BYTES:
        raise ValueError("Prepared PNG exceeds 20 MiB; use a smaller output size")
    image.thumbnail(
        (768, 768),
        Image.Resampling.NEAREST if design["settings"]["pixel_art"] else Image.Resampling.LANCZOS,
    )
    image.save(folder / "preview.png")
    result = dict(
        schema_version=1,
        asset_id=asset_id,
        revision=revision,
        plan=design,
        source=str(path),
        source_sha256=digest(data),
        report=report,
        settings=design["settings"],
        sha256=digest((folder / "image.png").read_bytes()),
        file=f"images/{asset_id}/{revision}/image.png",
        created_utc=workflow.now(),
        appearance_accepted=False,
    )
    core.atomic_json(folder / "manifest.json", result)
    if preview_only:
        return {"status": "prepared", **result}
    return publish(project, asset_id, revision)


def read_revision(project, asset_id, revision):
    folder = owned(root(project), "images", core.asset_id(asset_id), workflow.identifier(revision))
    result = core.read_optional_json(folder / "manifest.json")
    if not result or result.get("asset_id") != asset_id or result.get("revision") != revision:
        raise ValueError("Image revision is missing")
    if digest((folder / "image.png").read_bytes()) != result["sha256"]:
        raise ValueError("Prepared image changed; prepare a new revision")
    return result, folder


def publish(project, asset_id, revision):
    """Publish a retained image revision; reuses pending imports and keeps native references stable.

    An older revision can be published to restore it. Never regenerates or spends API credits.
    """
    result, folder = read_revision(project, asset_id, revision)
    with background.lock(folder / "publish.json"):
        previous = core.read_optional_json(folder / "publish.json")
        current = core.read_optional_json(root(project) / "image-receipts" / (asset_id + ".json"))
        if previous:
            state = workflow.job_status(project, previous["request_id"])
            if state["status"] == "queued" or (
                state["status"] == "completed" and current and current["revision"] == revision
            ):
                return {**state, "asset_id": asset_id, "revision": revision}
        payload = {
            "schema_version": 1,
            "asset_id": asset_id,
            "revision": revision,
            "file": result["file"],
            "sha256": result["sha256"],
            **result["settings"],
            "expected_revision": current["revision"] if current else "",
        }
        task = workflow.action(
            project,
            "image",
            asset_id=asset_id,
            scope="asset",
            values={"image_json": json.dumps(payload)},
        )
        core.atomic_json(folder / "publish.json", task)
        return {**task, "asset_id": asset_id, "revision": revision}


def catalog(project, asset_id=None):
    """List retained images and revisions, with exact native import status and paths."""
    directory = root(project)
    folders = (
        [owned(directory, "images", core.asset_id(asset_id))]
        if asset_id
        else sorted((directory / "images").glob("*"))
    )
    results = []
    for folder in folders:
        if not folder.is_dir() or not folder.resolve().is_relative_to(directory):
            continue
        current = core.read_optional_json(directory / "image-receipts" / (folder.name + ".json"))
        versions = []
        for path in sorted(
            folder.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            row = core.read_optional_json(path)
            task = core.read_optional_json(path.with_name("publish.json"))
            versions.append(
                {k: row[k] for k in ("revision", "settings", "report", "created_utc")}
                | {
                    "prompt": row["plan"]["prompt"],
                    "reference_path": str(path.parent / "image.png"),
                    "task": workflow.job_status(project, task["request_id"]) if task else None,
                }
            )
        if versions:
            results.append(dict(asset_id=folder.name, current=current, revisions=versions))
    return {"presets": PRESETS, "assets": results}


def preview(project, asset_id, revision):
    """Read the real prepared image preview; alpha is retained for checkerboard display."""
    result, folder = read_revision(project, asset_id, revision)
    return {
        "asset_id": asset_id,
        "revision": revision,
        "path": str(folder / "preview.png"),
        "settings": result["settings"],
        "report": result["report"],
    }


def example(project, asset_id="example_potion"):
    """Import the bundled AI-generated healing potion icon, without a provider or Blender."""
    return import_image(
        project,
        asset_id,
        str(registry.resources() / "examples/images/healing-potion.png"),
        prompt="Cozy herbalist healing potion, generated example artwork",
        kind="icon",
    )


def generate(project, plan_id, allow_remote=False, preview_only=False):
    """Generate one image using the explicitly configured API, then prepare/import it.

    Remote service use requires user authorization (allow_remote). Poll/resume the returned task;
    Uncertain requests are not resubmitted automatically. Host tools use import_image.
    """
    from . import image_provider

    if type(allow_remote) is not bool or type(preview_only) is not bool:
        raise ValueError("Generation flags must be booleans")
    design = read_plan(project, plan_id)
    config = image_provider.config()
    image_provider.validate(config)
    if image_provider.remote(config) and not allow_remote:
        raise ValueError(
            "The selected image service may charge and receives the prompt/references. "
            "Use allow_remote only when the user has chosen this service for this image."
        )
    return background.submit(
        project,
        "image_generation",
        dict(plan_id=plan_id, config=config, preview_only=preview_only),
        design["asset_id"],
    )


def run(job, plan_id, config, preview_only):
    from . import image_provider

    design = read_plan(job.project, plan_id)
    folder = job.path.parent
    generated = folder / "generated.png"
    if not generated.exists():
        if job.state.get("provider_started"):
            raise ValueError(
                "The earlier image request has an unknown outcome; it will not be sent "
                "again automatically. Recover the provider image with import_image, "
                "or explicitly start a new generation task."
            )
        job.check()
        job.update(stage="Generating game image", provider_started=True)
        data = image_provider.request(config, design)
        decode(data)
        temporary = folder / "generated.partial"
        temporary.write_bytes(data)
        temporary.replace(generated)
    job.check()
    revision = job.state.get("image_revision")
    if not revision:
        prepared = import_image(
            job.project, design["asset_id"], str(generated), plan_id, preview_only=True
        )
        revision = prepared["revision"]
        job.update(image_revision=revision)
    task = None
    if not preview_only:
        job.update(stage="Waiting for native image import")
        task = job.wait(publish(job.project, design["asset_id"], revision))
    return dict(
        stage="Image prepared" if preview_only else "Image ready in the game project",
        image_revision=revision,
        image_result=task,
        preview_only=preview_only,
        appearance_accepted=False,
    )
