import hashlib
import importlib.util
from pathlib import Path

import pytest

path = (
    Path(__file__).resolve().parents[1]
    / "unreal/PromptToScene/Content/Python/prompt_to_scene_unreal/protocol.py"
)
spec = importlib.util.spec_from_file_location("unreal_protocol_under_test", path)
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


@pytest.fixture
def request_and_root(tmp_path):
    root = protocol.state_root(tmp_path)
    work = "work/crate/" + "a" * 32
    source = root / work
    source.mkdir(parents=True)
    (source / "model.fbx").write_bytes(b"fixture bytes, not an engine import")
    name = "漆面 / Paint"
    request = {
        "schema_version": 2,
        "target_engine": "unreal",
        "position_unit": "meters",
        "asset_id": "crate",
        "request_id": "a" * 32,
        "work_dir": work,
        "position": [0, 0, 0],
        "collider": True,
        "files": [
            {
                "name": "model.fbx",
                "sha256": hashlib.sha256((source / "model.fbx").read_bytes()).hexdigest(),
            }
        ],
        "materials": [
            {
                "name": name,
                "fbx_name": "PTS_" + protocol.digest(name),
                "color": [1, 0, 0, 1],
                "metallic": 0,
                "roughness": 0.5,
                "normal_strength": 1,
                "base_color_texture": "",
                "normal_texture": "",
            }
        ],
    }
    return request, root


def test_accepts_intact_engine_specific_manifest(request_and_root):
    request, root = request_and_root
    assert protocol.validate(request, "crate", root) == root / request["work_dir"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_engine", "unity"),
        ("position_unit", "centimeters"),
        ("work_dir", "../outside"),
        ("position", [0, float("nan"), 0]),
        ("schema_version", 1),
        ("asset_id", "../escape"),
        ("collider", "false"),
    ],
)
def test_rejects_invalid_request_before_engine_writes(request_and_root, field, value):
    request, root = request_and_root
    request[field] = value
    with pytest.raises(ValueError):
        protocol.validate(request, "crate", root)


def test_rejects_modified_transfer(request_and_root):
    request, root = request_and_root
    (root / request["work_dir"] / "model.fbx").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        protocol.validate(request, "crate", root)


def test_rejects_missing_texture(request_and_root):
    request, root = request_and_root
    request["materials"][0]["normal_texture"] = "tex_" + "b" * 16 + ".png"
    with pytest.raises(ValueError, match="Texture absent"):
        protocol.validate(request, "crate", root)


def test_rejects_symlink_transfer(request_and_root, tmp_path):
    request, root = request_and_root
    file = root / request["work_dir"] / "model.fbx"
    outside = tmp_path / "outside.fbx"
    outside.write_bytes(file.read_bytes())
    file.unlink()
    file.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        protocol.validate(request, "crate", root)


def test_lod_files_are_hashed_and_screen_sizes_must_decrease(request_and_root):
    request, root = request_and_root
    work = root / request["work_dir"]
    for i, size in enumerate((0.5, 0.2), 1):
        name = f"lod_{i}.fbx"
        (work / name).write_bytes(bytes([i]))
        request["files"].append({"name": name, "sha256": hashlib.sha256(bytes([i])).hexdigest()})
        request.setdefault("lods", []).append(
            {"file": name, "screen_height": size, "triangles": 100 // i}
        )
    request["collision_mode"] = "convex"
    assert protocol.validate(request, "crate", root) == work
    request["lods"][1]["screen_height"] = 0.8
    with pytest.raises(ValueError):
        protocol.validate(request, "crate", root)
    request["lods"][1]["screen_height"] = 0.2
    (work / "lod_1.fbx").write_bytes(b"modified")
    with pytest.raises(ValueError, match="hash mismatch"):
        protocol.validate(request, "crate", root)
