"""Region edits with retained evidence and exact preservation outside the selection."""

import math

from PIL import Image

from . import core, image_assets, workflow


def plan(project, asset_id, revision, rectangle, prompt):
    """Plan a local image edit. rectangle is normalized [x,y,width,height], top-left origin.

    The host edits source_path with mask_path, or calls generate_image with this plan_id.
    Finish through import_image(plan_id=...) to preserve every pixel outside the rectangle.
    """
    old, _ = image_assets.read_revision(project, asset_id, revision)
    if (
        not isinstance(rectangle, list)
        or len(rectangle) != 4
        or any(type(v) not in {int, float} or not math.isfinite(v) for v in rectangle)
    ):
        raise ValueError("Select a finite normalized rectangle")
    x, y, w, h = rectangle
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.000001 or y + h > 1.000001:
        raise ValueError("The selection must be inside the image")
    source = image_assets.owned(
        image_assets.root(project), "images", asset_id, revision, "image.png"
    )
    im = image_assets.decode(source.read_bytes()).convert("RGBA")
    box = [
        int(x * im.width),
        int(y * im.height),
        min(im.width, math.ceil((x + w) * im.width)),
        min(im.height, math.ceil((y + h) * im.height)),
    ]
    if box[0] == box[2] or box[1] == box[3]:
        raise ValueError("Select at least one pixel")
    assets = image_assets.catalog(project, asset_id)["assets"]
    if not assets or assets[0]["revisions"][0]["revision"] != revision:
        raise ValueError("Select the latest image version before planning a region edit")
    design = image_assets.plan(
        project, asset_id, prompt, **old["settings"], reference_paths=[str(source)]
    )
    directory = image_assets.owned(image_assets.root(project), "image-plans", design["plan_id"])
    mask = Image.new("RGBA", im.size, (255, 255, 255, 255))
    mask.paste((255, 255, 255, 0), tuple(box))
    mask.save(directory / "mask.png")
    im.crop(tuple(box)).save(directory / "crop.png")
    design["region_edit"] = {
        "base_revision": revision,
        "base_sha256": old["sha256"],
        "box": box,
        "source_path": str(source),
        "mask_path": str(directory / "mask.png"),
        "mask_sha256": image_assets.digest((directory / "mask.png").read_bytes()),
        "crop_path": str(directory / "crop.png"),
    }
    design["effective_prompt"] += (
        "\nEdit only the transparent mask region. Preserve composition and other objects. "
        "Return a full-size image with the exact original dimensions, or the selected crop "
        "at its exact size. The plugin preserves pixels outside the rectangle."
    )
    core.atomic_json(directory / "plan.json", design)
    return design


def composite(project, design, data):
    edit = design["region_edit"]
    old, _ = image_assets.read_revision(project, design["asset_id"], edit["base_revision"])
    assets = image_assets.catalog(project, design["asset_id"])["assets"]
    if not assets or assets[0]["revisions"][0]["revision"] != edit["base_revision"]:
        raise ValueError("Image changed since this region was selected; select the current version")
    source = image_assets.owned(
        image_assets.root(project),
        "images",
        design["asset_id"],
        workflow.identifier(edit["base_revision"]),
        "image.png",
    )
    if (
        image_assets.digest(source.read_bytes()) != edit["base_sha256"]
        or old["sha256"] != edit["base_sha256"]
    ):
        raise ValueError("Region edit source changed")
    base = image_assets.decode(source.read_bytes()).convert("RGBA")
    changed = image_assets.decode(data).convert("RGBA")
    left, top, right, bottom = edit["box"]
    if changed.size == base.size:
        changed = changed.crop((left, top, right, bottom))
    elif changed.size != (right - left, bottom - top):
        raise ValueError("Edited image must match the full source or exact selected crop size")
    base.paste(changed, (left, top))
    alpha = base.getchannel("A").getextrema()
    if alpha[1] == 0:
        raise ValueError("The edited image is entirely transparent")
    if design["settings"]["transparent"] and alpha[0] == 255:
        raise ValueError("The edited image lost its required transparent background")
    return base


def provider_frame(design, requested_size):
    """Letterbox source and mask together to an API canvas, retaining exact inverse mapping."""
    import io
    from pathlib import Path

    edit = design["region_edit"]
    source = image_assets.decode(Path(edit["source_path"]).read_bytes()).convert("RGBA")
    mask_data = Path(edit["mask_path"]).read_bytes()
    if image_assets.digest(mask_data) != edit["mask_sha256"]:
        raise ValueError("Edit mask changed; select the region again")
    mask = image_assets.decode(mask_data).convert("RGBA")
    if mask.size != source.size:
        raise ValueError("Mask and image dimensions must match")
    if requested_size == "auto":
        ratio = source.width / source.height
        requested_size = (
            "1536x1024" if ratio > 1.2 else "1024x1536" if ratio < 0.83 else "1024x1024"
        )
    width, height = map(int, requested_size.split("x"))
    factor = min(width / source.width, height / source.height)
    scaled = (max(1, round(source.width * factor)), max(1, round(source.height * factor)))
    left, top = (width - scaled[0]) // 2, (height - scaled[1]) // 2

    def framed(image, background, resample):
        canvas = Image.new("RGBA", (width, height), background)
        canvas.paste(image.resize(scaled, resample), (left, top))
        output = io.BytesIO()
        canvas.save(output, format="PNG")
        return output.getvalue()

    return {
        "size": requested_size,
        "image": framed(source, (0, 0, 0, 0), Image.Resampling.LANCZOS),
        "mask": framed(mask, (255, 255, 255, 255), Image.Resampling.NEAREST),
        "box": (left, top, left + scaled[0], top + scaled[1]),
        "original_size": source.size,
    }


def provider_result(data, frame):
    """Invert the API frame only; composite() still restores every outside-selection pixel."""
    import io

    image = image_assets.decode(data).convert("RGBA")
    expected = tuple(map(int, frame["size"].split("x")))
    if image.size != expected:
        raise ValueError(
            "Image provider returned a different canvas size; recover the output manually"
        )
    image = image.crop(frame["box"]).resize(frame["original_size"], Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
