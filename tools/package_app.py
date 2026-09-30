"""Build a portable app on its target OS: uv run --group build python tools/package_app.py."""

import hashlib
import importlib.metadata
import platform
import plistlib
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

from prompt_to_scene import __version__

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "dist"


def freeze(name, entry, extra=()):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            name,
            "--distpath",
            str(DIST / "bin"),
            "--workpath",
            str(REPO / "build" / name),
            "--specpath",
            str(REPO / "build"),
            *extra,
            str(REPO / "tools" / entry),
        ],
        check=True,
        cwd=REPO,
    )


def main():
    data = []
    for source, target in (
        (
            "unity/Packages/com.prompttoscene.bridge",
            "resources/unity/Packages/com.prompttoscene.bridge",
        ),
        ("unreal/PromptToScene", "resources/unreal/PromptToScene"),
        ("plugins/shared", "resources/plugins/shared"),
        ("src/prompt_to_scene/blender_export.py", "prompt_to_scene"),
        ("src/prompt_to_scene/blender_recipe.py", "prompt_to_scene"),
        ("src/prompt_to_scene/blender_surfaces.py", "prompt_to_scene"),
        ("src/prompt_to_scene/blender_preview.py", "prompt_to_scene"),
        ("src/prompt_to_scene/setup.html", "prompt_to_scene"),
    ):
        data += ["--add-data", str(REPO / source) + ":" + target]
    freeze("prompt-to-scene-core", "app_entry.py", data)
    system = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}[platform.system()]
    architecture = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"
    name = "Prompt-to-Scene-" + system + "-" + architecture
    stage = DIST / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    if system == "macos":
        app = stage / "Prompt-to-Scene.app"
        binary = app / "Contents/MacOS/prompt-to-scene-core"
        binary.parent.mkdir(parents=True)
        shutil.copy2(DIST / "bin/prompt-to-scene-core", binary)
        (app / "Contents/Info.plist").write_bytes(
            plistlib.dumps(
                {
                    "CFBundleName": "Prompt-to-Scene",
                    "CFBundleDisplayName": "Prompt-to-Scene",
                    "CFBundleIdentifier": "com.prompttoscene.setup",
                    "CFBundleExecutable": binary.name,
                    "CFBundlePackageType": "APPL",
                    "CFBundleVersion": __version__,
                    "CFBundleShortVersionString": __version__,
                    "LSUIElement": True,
                    "NSHighResolutionCapable": True,
                }
            )
        )
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    elif system == "windows":
        freeze("Prompt-to-Scene", "windows_launcher.py", ["--windowed"])
        for binary in ("Prompt-to-Scene.exe", "prompt-to-scene-core.exe"):
            shutil.copy2(DIST / "bin" / binary, stage / binary)
    else:
        shutil.copy2(DIST / "bin/prompt-to-scene-core", stage / "Prompt-to-Scene")
    shutil.copy2(REPO / "LICENSE", stage / "LICENSE.txt")
    notices = [
        "Third-party components in the build environment\n"
        "The app contains CPython and dependencies collected by PyInstaller.\n"
    ]
    python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    if python_license.is_file():
        notices.append("CPython\n" + python_license.read_text(encoding="utf-8"))
    for distribution in sorted(
        importlib.metadata.distributions(), key=lambda d: d.metadata.get("Name", "")
    ):
        licenses = [
            file
            for file in (distribution.files or [])
            if ".dist-info/" in str(file)
            and ("license" in file.name.lower() or "copying" in file.name.lower())
        ]
        if licenses:
            notices.append("\n" + distribution.metadata["Name"] + " " + distribution.version)
            for file in licenses:
                path = Path(distribution.locate_file(file))
                if path.is_file():
                    notices.append(path.read_text(encoding="utf-8", errors="replace"))
    (stage / "THIRD_PARTY_LICENSES.txt").write_text("\n\n".join(notices), encoding="utf-8")
    (stage / "START_HERE.txt").write_text(
        "Prompt-to-Scene " + __version__ + "\n\n"
        "Open Prompt-to-Scene to select your engine project and install the AI client plugin.\n"
        "Blender and Unity/Unreal must already be installed. Python is bundled.\n"
        "macOS: this community build is ad-hoc signed, not notarized. If blocked, use\n"
        "System Settings > Privacy & Security > Open Anyway after verifying the download.\n"
        "Windows: keep both EXE files together. This community build is unsigned.\n"
        "Guide: https://github.com/316sandon12/prompt-to-scene/blob/main/docs/QUICKSTART.zh-CN.md\n",
        encoding="utf-8",
    )
    archive = DIST / (name + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(DIST))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(digest + "  " + archive.name + "\n")
    print("Built " + str(archive), flush=True)


if __name__ == "__main__":
    main()
