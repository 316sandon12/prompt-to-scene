"""Install native host plugins around the same local executable; never change host permissions."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, registry, workflow
from .core import atomic_json


def executable(name):
    found = shutil.which(name)
    if found:
        return found
    for folder in (
        Path.home() / ".local/bin",
        Path.home() / ".dsh/bin",
        Path.home() / ".npm-global/bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ):
        for suffix in ("", ".exe", ".cmd"):
            candidate = folder / (name + suffix)
            if candidate.is_file():
                return str(candidate)
    if name == "codex" and sys.platform == "darwin":
        for path in (
            "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
            "/Applications/Codex.app/Contents/Resources/codex",
        ):
            if Path(path).is_file():
                return path
    return None


def inventory():
    dsh_home = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))
    profiles = [p.name for p in (dsh_home / "profiles").glob("*") if (p / "package.json").is_file()]
    return {
        "codex": executable("codex"),
        "harness": executable("dsh"),
        "harness_profiles": profiles or ["web"],
    }


def runtime():
    if not getattr(sys, "frozen", False):
        return workflow.launch_command("--mcp")
    source = Path(sys.executable)
    target = registry.home() / "runtime" / __version__ / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    same_content = (
        target.is_file()
        and source.stat().st_size == target.stat().st_size
        and hashlib.sha256(source.read_bytes()).digest()
        == hashlib.sha256(target.read_bytes()).digest()
    )
    if source.resolve() != target.resolve() and not same_content:
        staging = target.with_suffix(target.suffix + ".new")
        shutil.copy2(source, staging)
        staging.replace(target)
    return [str(target), "--mcp"]


def create_bundles():
    marketplace = registry.home() / "plugins"
    root = marketplace / __version__
    root.mkdir(parents=True, exist_ok=True)
    command = runtime()
    environment = {"PTS_HOME": str(registry.home())}
    skill = registry.resources() / "plugins/shared/skills/prompt-to-scene"
    codex = root / "codex"
    codex.mkdir(exist_ok=True)
    shutil.copytree(skill, codex / "skills/prompt-to-scene", dirs_exist_ok=True)
    atomic_json(
        codex / ".codex-plugin/plugin.json",
        {
            "name": "prompt-to-scene",
            "version": __version__,
            "description": "Create and revise Blender props in Unity and Unreal.",
            "skills": "./skills/",
            "mcpServers": "./.mcp.json",
        },
    )
    atomic_json(
        codex / ".mcp.json",
        {
            "mcpServers": {
                "prompt_to_scene": {"command": command[0], "args": command[1:], "env": environment}
            }
        },
    )
    market = marketplace / ".agents/plugins/marketplace.json"
    atomic_json(
        market,
        {
            "name": "prompt-to-scene-local",
            "interface": {"displayName": "Prompt-to-Scene"},
            "plugins": [
                {
                    "name": "prompt-to-scene",
                    "source": {"source": "local", "path": "./" + __version__ + "/codex"},
                    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                }
            ],
        },
    )
    harness = root / "harness"
    harness.mkdir(exist_ok=True)
    atomic_json(
        harness / "package.json",
        {
            "name": "prompt-to-scene-dsh",
            "version": __version__,
            "description": "Prompt-to-Scene for DeepSeek Harness",
            "license": "MIT",
            "files": ["cordis.patch.yml"],
            "dsh": {"bundle": {"patch": "./cordis.patch.yml"}},
        },
    )
    # JSON is valid YAML, so paths/quotes remain data on every platform.
    patch = [
        {
            "insert": [
                {
                    "id": "prompt-to-scene",
                    "name": "@deepseek-ai/dsh-mcp-client",
                    "config": {
                        "serverName": "prompt_to_scene",
                        "transport": "stdio",
                        "command": command[0],
                        "args": command[1:],
                        "env": environment,
                        "toolCallTimeoutMs": 60000,
                    },
                }
            ]
        }
    ]
    (harness / "cordis.patch.yml").write_text(json.dumps(patch, indent=2), encoding="utf-8")
    return {"codex": codex, "harness": harness, "marketplace": marketplace, "command": command}


def run(command):
    binary = Path(command[0])
    environment = dict(os.environ)
    node = executable("node")
    extra_paths = [str(binary.parent)]
    if node:
        extra_paths.append(str(Path(node).parent))
    environment["PATH"] = os.pathsep.join(extra_paths + [environment.get("PATH", "")])
    if binary.suffix.lower() == ".cmd":
        # Bypass npm's batch shim so project/profile paths remain literal arguments.
        package = (
            "@deepseek-ai/dsh/lib/bin.js" if binary.stem == "dsh" else "@openai/codex/bin/codex.js"
        )
        scripts = (binary.parent / "node_modules" / package, binary.parent.parent / package)
        script = next((p for p in scripts if p.is_file()), None)
        if not node or not script:
            raise ValueError(
                "Cannot locate this client's Node entry point; select its native executable."
            )
        command = [node, str(script), *command[1:]]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-4000:])
    return result.stdout[-4000:]


def install(client, profile="web", command=None):
    if client not in {"codex", "harness"}:
        raise ValueError("Choose Codex or DeepSeek Harness")
    binary = command or executable("codex" if client == "codex" else "dsh")
    if not binary or not Path(binary).is_file():
        raise ValueError("Client executable was not found. Select its executable in setup.")
    if not profile or not all(c.isalnum() or c in "_-" for c in profile):
        raise ValueError("Invalid Harness profile name")
    bundles = create_bundles()
    if client == "codex":
        run([binary, "plugin", "marketplace", "add", str(bundles["marketplace"]), "--json"])
        output = run([binary, "plugin", "add", "prompt-to-scene@prompt-to-scene-local", "--json"])
    else:
        output = run(
            [binary, "plugin", "--profile", profile, "add", "file:" + str(bundles["harness"])]
        )
    return {
        "client": client,
        "installed": True,
        "version": __version__,
        "message": "Restart the client and start a new chat to load the plugin.",
        "details": output,
    }
