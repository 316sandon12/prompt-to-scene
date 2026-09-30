"""Standard-library validation, shared by the Unreal adapter and its engine-free tests."""

import hashlib
import json
import math
import os
import re
import uuid
from pathlib import Path


def state_root(project):
    root = Path(project).resolve() / ".prompt-to-scene"
    if root.is_symlink():
        raise ValueError("Project state directory cannot be a symlink")
    return root


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def digest(name):
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def finite(value, low=None, high=None):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and (low is None or value >= low)
        and (high is None or value <= high)
    )


def validate(request, filename, root):
    if not isinstance(request, dict) or request.get("schema_version") != 2:
        raise ValueError("Unreal requires schema_version 2; update the Python server")
    if request.get("target_engine") != "unreal" or request.get("position_unit") != "meters":
        raise ValueError("Request must target Unreal with position_unit=meters")
    asset = request.get("asset_id")
    revision = request.get("request_id")
    if not isinstance(asset, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", asset):
        raise ValueError("Invalid asset_id")
    if filename != asset:
        raise ValueError("Asset ID does not match inbox filename")
    if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{32}", revision):
        raise ValueError("Invalid request_id")
    work = f"work/{asset}/{revision}"
    if request.get("work_dir") != work:
        raise ValueError("Work directory does not match request identity")
    source = root / work
    if source.resolve() != source or not source.is_dir():
        raise ValueError("Work directory is missing or traverses a symlink")
    position = request.get("position")
    if not isinstance(position, list) or len(position) != 3 or not all(map(finite, position)):
        raise ValueError("Position must contain three finite numbers")
    if not isinstance(request.get("collider"), bool):
        raise ValueError("collider must be a boolean")
    files = request.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 128:
        raise ValueError("Invalid file manifest")
    names = set()
    for entry in files:
        name = entry.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"model\.fbx|tex_[a-f0-9]{16}\.png", name):
            raise ValueError("Invalid transfer filename")
        if name in names:
            raise ValueError("Duplicate transfer filename")
        names.add(name)
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Transfer file missing or a symlink: " + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            raise ValueError("Transfer hash mismatch: " + name)
    if "model.fbx" not in names:
        raise ValueError("Missing model.fbx")
    materials = request.get("materials")
    if not isinstance(materials, list) or not 1 <= len(materials) <= 128:
        raise ValueError("Invalid materials")
    seen = set()
    for material in materials:
        name = material.get("name")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("Missing or duplicate material name")
        seen.add(name)
        if material.get("fbx_name") != "PTS_" + digest(name):
            raise ValueError("Invalid FBX material identity")
        color = material.get("color")
        if (
            not isinstance(color, list)
            or len(color) != 4
            or not all(finite(v, 0, 1) for v in color)
        ):
            raise ValueError("Invalid material color")
        if not all(finite(material.get(k), 0, 1) for k in ("metallic", "roughness")):
            raise ValueError("Invalid metallic/roughness")
        if not finite(material.get("normal_strength"), 0):
            raise ValueError("Invalid normal strength")
        for key in (
            "base_color_texture",
            "normal_texture",
            "roughness_texture",
            "metallic_texture",
            "mask_texture",
        ):
            texture = material.get(key, "")
            if not isinstance(texture, str) or (
                texture and (texture not in names or not texture.endswith(".png"))
            ):
                raise ValueError("Texture absent from transfer manifest")
    return source
