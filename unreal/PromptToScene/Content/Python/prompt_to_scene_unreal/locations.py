"""Persistent managed paths; new conventions never silently relocate existing assets."""

import json
import re
from pathlib import Path

import unreal


def validate(value):
    folder = value.get("folder", "")
    if (
        not re.fullmatch(r"/Game/[A-Za-z0-9_/ -]+", folder)
        or "/PromptToScene/" not in folder
        or "//" in folder
    ):
        raise ValueError("Invalid managed asset folder")
    for key in (
        "model",
        "prefab",
        "blueprint",
        "materials",
        "textures",
        "material_prefix",
        "texture_prefix",
    ):
        part = value.get(key)
        if (
            not isinstance(part, str)
            or not re.fullmatch(r"[A-Za-z0-9_/]*", part)
            or "//" in part
            or part.startswith("/")
        ):
            raise ValueError("Invalid managed asset convention")
    return value


def get(name):
    path = Path(unreal.Paths.project_dir()) / ".prompt-to-scene/locations" / (name + ".json")
    return validate(
        json.loads(path.read_text())
        if path.is_file()
        else dict(
            folder="/Game/PromptToScene/" + name,
            model="SM_" + name,
            prefab=name,
            blueprint="BP_" + name,
            materials="",
            textures="",
            material_prefix="M_",
            texture_prefix="T_",
        )
    )


def asset(name, kind="model"):
    value = get(name)
    return value["folder"] + "/" + value[kind]
