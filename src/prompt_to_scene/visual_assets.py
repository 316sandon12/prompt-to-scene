"""Actual Blender source geometry for orbit/part picking and transparent item icons."""

import subprocess
import time
from pathlib import Path

from . import background, core, game_art, image_assets, registry, workflow


def submit(project, asset_id, mode="view", icon_id=None):
    """Prepare an interactive source view or render a transparent icon from the actual model."""
    if mode not in {"view", "icon"}:
        raise ValueError("Choose view or icon")
    info = workflow.inspect_asset(project, core.asset_id(asset_id))
    if info["current"].get("status") != "imported":
        raise ValueError("Import the model before preparing its visual assets")
    if not Path(info["source_blend"]).is_file():
        raise ValueError("Retained Blender source is unavailable")
    return background.submit(
        project,
        "visual_asset",
        dict(
            asset_id=asset_id,
            revision=info["current"]["request_id"],
            mode=mode,
            icon_id=core.asset_id(icon_id or (asset_id if mode == "view" else asset_id + "_icon")),
        ),
        asset_id,
    )


def read(project, asset_id, revision):
    directory = image_assets.owned(
        game_art.root(project),
        "model-views",
        core.asset_id(asset_id),
        workflow.identifier(revision),
    )
    path = directory / "view.json"
    if path.exists() and path.stat().st_size > 32 * 1024**2:
        raise ValueError("Model view exceeds 32 MiB; simplify the source before viewing")
    result = core.read_optional_json(path)
    if not result:
        raise ValueError("Prepare the model view first")
    return result


def run(job, asset_id, revision, mode, icon_id):
    info = workflow.inspect_asset(job.project, asset_id)
    if info["current"].get("request_id") != revision:
        raise ValueError("Model changed; prepare its current revision")
    directory = image_assets.owned(job.root, "model-views", asset_id, revision)
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / (mode + "-config.json")
    target = directory / ("view.json" if mode == "view" else "icon.png")
    if not target.exists():
        core.atomic_json(
            config, dict(asset_id=asset_id, revision=revision, mode=mode, output=str(target))
        )
        blender = registry.find_blender()
        if not blender:
            raise ValueError("Locate Blender in connection settings")
        command = [
            str(blender),
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--threads",
            "4",
            info["source_blend"],
            "--python",
            str(Path(__file__).with_name("blender_visual.py")),
            "--",
            str(config),
        ]
        job.update(stage="Rendering model icon" if mode == "icon" else "Preparing model view")
        with (directory / (mode + ".log")).open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 300
                while process.poll() is None:
                    job.check()
                    if time.monotonic() > deadline:
                        raise TimeoutError("Blender visual preparation timed out")
                    time.sleep(0.2)
                if process.returncode or not target.is_file():
                    raise RuntimeError(
                        "Blender visual preparation failed; inspect " + str(directory)
                    )
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    if workflow.inspect_asset(job.project, asset_id)["current"].get("request_id") != revision:
        raise ValueError("Model changed during rendering; keep the newer model and render again")
    result = dict(
        stage="Model view ready" if mode == "view" else "Matching icon ready",
        model_asset_id=asset_id,
        model_revision=revision,
        visual_mode=mode,
    )
    if mode == "icon":
        if not job.state.get("image_revision"):
            prepared = image_assets.import_image(
                job.project,
                icon_id,
                str(target),
                prompt="Transparent icon rendered from " + asset_id,
                kind="icon",
                width=256,
                height=256,
                transparent=True,
                preview_only=True,
            )
            job.update(image_revision=prepared["revision"])
        native = job.wait(image_assets.publish(job.project, icon_id, job.state["image_revision"]))
        result.update(
            image_revision=job.state["image_revision"], icon_asset_id=icon_id, image_result=native
        )
    else:
        result["model_view"] = {"asset_id": asset_id, "revision": revision}
    return result
