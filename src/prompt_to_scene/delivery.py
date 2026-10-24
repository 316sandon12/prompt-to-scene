"""Native player builds, retained delivery receipts and narrowly owned staging cleanup."""

import json
import shutil
import subprocess
import sys
import time

from . import background, core, creations, development, game_art, registry, workflow


def inspect_project(project):
    """Inspect actual engine version, current scene/maps and installed build support."""
    return development.request(project, "delivery", mode="inspect", content_json="{}")


def build(project, scenes=None, development_build=True):
    """Build a native player for this computer's platform, preserving the user's build settings.

    scenes: saved Unity Assets/*.unity paths or Unreal /Game/... maps. Empty uses enabled Unity
    build scenes/current UE map. Requires the engine's platform SDK/toolchain. The saved result
    distinguishes a successful build from a game that has actually been launched and played.
    """
    if type(development_build) is not bool:
        raise ValueError("development_build must be a boolean")
    if scenes is not None and (
        not isinstance(scenes, list)
        or not 1 <= len(scenes) <= 32
        or any(not isinstance(s, str) or len(s) > 500 for s in scenes)
    ):
        raise ValueError("Select 1–32 saved scenes/maps")
    return background.submit(
        project, "game_delivery", dict(scenes=scenes or [], development_build=development_build)
    )


def catalog(project):
    """Read native build evidence and output paths; no inferred compatibility or play success."""
    return {
        "deliveries": [
            core.read_optional_json(p)
            for p in sorted((game_art.root(project) / "deliveries").glob("*.json"))
        ]
    }


def launch(project, request_id):
    """Launch a completed native player; UE opens the first explicitly packaged map.

    This starts the requested game, not a verification verdict. Close its normal window when
    finished. Runtime logs remain in this delivery's owned folder.
    """
    import plistlib
    from pathlib import Path

    request_id = workflow.identifier(request_id)
    row = core.read_optional_json(game_art.root(project) / "deliveries" / (request_id + ".json"))
    root = registry.resolve(project).root / ".local" / "pts-deliveries" / request_id
    owner = core.read_optional_json(root / "owner.json")
    if not row or not row.get("built") or not owner or owner.get("request_id") != request_id:
        raise ValueError("Choose a completed player build")
    path = Path(row.get("entrypoint") or row["output"])
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("The built player is missing or outside this task's output")
    if path.suffix == ".app":
        with (path / "Contents/Info.plist").open("rb") as stream:
            name = plistlib.load(stream)["CFBundleExecutable"]
        path = path / "Contents/MacOS" / name
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("The built player is missing or outside this task's output")
    log = root / "runtime.log"
    args = [str(path)]
    if row["engine"] == "unreal":
        args += [row["scenes"][0], "-abslog=" + str(log)]
    else:
        args += ["-logFile", str(log)]
    with (root / "launch.log").open("w") as stream:
        process = subprocess.Popen(
            args,
            cwd=str(path.parent),
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=sys.platform != "win32",
        )
    core.atomic_json(
        root / "launch.json",
        dict(pid=process.pid, executable=str(path), started_utc=workflow.now()),
    )
    return dict(
        status="launched",
        pid=process.pid,
        output=str(path),
        log=str(root / "launch.log"),
        runtime_verified=False,
    )


def run(job, scenes, development_build):
    target = registry.resolve(job.project)
    output = target.root / ".local" / "pts-deliveries" / job.id
    output.mkdir(parents=True, exist_ok=True)
    core.atomic_json(
        output / "owner.json",
        dict(
            request_id=job.id, project=str(target.root), purpose="Prompt-to-Scene player delivery"
        ),
    )
    payload = dict(
        request_id=job.id, scenes=scenes, development_build=development_build, output=str(output)
    )
    job.update(stage="Preparing native player build", output=str(output))
    if target.engine == "unity":
        result = creations.step(
            job,
            "native_build",
            lambda: development.request(
                job.project, "delivery", mode="build", content_json=json.dumps(payload)
            ),
        )
        receipt = json.loads(result["development"]["plan_json"])
    else:
        prepared = creations.step(
            job,
            "prepare_build",
            lambda: development.request(
                job.project, "delivery", mode="prepare", content_json=json.dumps(payload)
            ),
        )
        receipt = json.loads(prepared["development"]["plan_json"])
        platform = (
            "Mac" if sys.platform == "darwin" else "Win64" if sys.platform == "win32" else "Linux"
        )
        from pathlib import Path

        engine = Path(receipt["engine_root"])
        uat = (
            engine
            / "Build"
            / "BatchFiles"
            / ("RunUAT.bat" if sys.platform == "win32" else "RunUAT.sh")
        )
        if not uat.is_file():
            raise ValueError("Unreal Automation Tool is unavailable for this engine installation")
        command = [
            str(uat),
            "BuildCookRun",
            "-project=" + str(target.project_file),
            "-nop4",
            "-unattended",
            "-utf8output",
            "-platform=" + platform,
            "-clientconfig=" + ("Development" if development_build else "Shipping"),
            "-build",
            "-cook",
            "-stage",
            "-pak",
            "-nocompileeditor",
            "-stagingdirectory=" + str(output / "staging"),
            "-map=" + "+".join(receipt["scenes"]),
        ]
        job.update(stage="Cooking and packaging Unreal player")
        log_path = output / "build.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            job.update(build_pid=process.pid)
            try:
                while process.poll() is None:
                    job.check()
                    time.sleep(0.3)
                if process.returncode:
                    raise RuntimeError("Native player build failed; inspect " + str(log_path))
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        staging = output / "staging"
        project_name = target.project_file.stem.casefold()
        if platform == "Mac":
            executables = [
                p
                for p in staging.glob("**/*.app/Contents/MacOS/*")
                if p.is_file() and p.name.casefold().startswith(project_name)
            ]
        elif platform == "Win64":
            executables = [
                p for p in staging.rglob("*.exe") if p.name.casefold().startswith(project_name)
            ]
        else:
            executables = [
                p
                for p in staging.rglob("*")
                if p.is_file()
                and p.name.startswith(target.project_file.stem)
                and p.stat().st_mode & 0o111
            ]
        executables = sorted(executables, key=lambda p: (len(p.parts), str(p)))
        if not executables:
            raise RuntimeError("Unreal did not stage a player executable; inspect " + str(log_path))
        # UE 5.7 can report archive success with only empty directories for a Blueprint project.
        # Deliver the actual staged app and its adjacent data, rather than trusting that message.
        player = output / "player"
        shutil.copytree(staging, player, dirs_exist_ok=True, symlinks=True)
        entry = player / executables[0].relative_to(staging)
        if not entry.is_file() or entry.stat().st_size == 0:
            raise RuntimeError("Player executable missing after delivery copy")
        receipt.update(platform=platform, output=str(player), entrypoint=str(entry), built=True)
        shutil.rmtree(staging)  # This task owns staging; retain only the verified copied player.
    receipt.update(
        request_id=job.id,
        runtime_verified=False,
        built_utc=workflow.now(),
        bytes=sum(
            p.stat().st_size for p in output.rglob("*") if p.is_file() and not p.is_symlink()
        ),
    )
    core.atomic_json(job.root / "deliveries" / (job.id + ".json"), receipt)
    return dict(stage="Native player build ready · launch to verify gameplay", delivery=receipt)


def cleanup(project, request_id):
    """Remove only delivery-owned logs/staging; retain the player, receipts and project assets."""
    root = (
        registry.resolve(project).root
        / ".local"
        / "pts-deliveries"
        / workflow.identifier(request_id)
    )
    owner = core.read_optional_json(root / "owner.json")
    state = workflow.job_status(project, request_id)
    if (
        not owner
        or owner.get("request_id") != request_id
        or state["status"] not in workflow.TERMINAL
    ):
        raise ValueError("Wait for this owned delivery task to stop before cleanup")
    removed = 0
    for path in (root / "build.log", root / "staging"):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unexpected delivery path")
        if path.is_file():
            removed += path.stat().st_size
            path.unlink()
        elif path.is_dir():
            removed += sum(
                p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink()
            )
            shutil.rmtree(path)
    return dict(removed_bytes=removed, player_retained=True)
