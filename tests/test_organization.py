import hashlib
import json

import pytest

from prompt_to_scene import core, organization, workbench, workflow


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "Project"
    (root / "Assets").mkdir(parents=True)
    (root / "ProjectSettings").mkdir()
    monkeypatch.setenv("PTS_PROJECT", str(root))
    monkeypatch.setenv("PTS_HOME", str(tmp_path / "home"))
    return root


def entry(path, kind="material", **values):
    filename = path.rsplit("/", 1)[-1]
    extension = (
        "." + filename.rsplit(".", 1)[-1] if path.startswith("Assets/") and "." in filename else ""
    )
    return dict(
        path=path,
        name=filename.removesuffix(extension),
        extension=extension,
        kind=kind,
        id=hashlib.sha256(path.encode()).hexdigest()[:32],
        fingerprint="test",
        **values,
    )


def scan(entries, engine="unity", occupied=()):
    return dict(
        scan_id="a" * 32,
        engine=engine,
        scope="Assets" if engine == "unity" else "/Game",
        entries=entries,
        occupied=list(occupied),
        truncated=False,
    )


def test_classifies_texture_roles_and_preserves_original_subject():
    rows = [
        entry("Assets/Pack/old oak albedo.png", "texture"),
        entry("Assets/Pack/old oak detail.png", "texture", texture_role="Normal"),
        entry("Assets/Pack/wood chair.fbx", "model"),
        entry("Assets/Pack/door.prefab", "prefab"),
    ]
    plan = organization.make_plan(scan(rows), {})
    assert [r["destination"] for r in plan["entries"]] == [
        "Assets/GameAssets/Prefabs/PF_Door.prefab",
        "Assets/GameAssets/Textures/T_OldOak_BaseColor.png",
        "Assets/GameAssets/Textures/T_OldOakDetail_Normal.png",
        "Assets/GameAssets/Models/SM_WoodChair.fbx",
    ]
    assert plan["summary"]["move"] == 4


@pytest.mark.parametrize("engine", ["unity", "unreal"])
def test_deterministic_collision_handling_and_second_run_is_noop(engine):
    base, ext = ("Assets", ".mat") if engine == "unity" else ("/Game", "")
    rows = [entry(base + "/pack_b/wood" + ext), entry(base + "/pack_a/wood" + ext)]
    occupied = [base + "/GameAssets/Materials/M_Wood" + ext]
    first = organization.make_plan(scan(rows, engine, occupied), {})
    assert first["summary"]["collisions_resolved"] == 2
    assert first["entries"][0]["destination"].endswith("M_Wood_02" + ext)
    assert first == organization.make_plan(scan(list(reversed(rows)), engine, occupied), {})
    renamed = [entry(r["destination"]) for r in first["entries"]]
    second = organization.make_plan(scan(renamed, engine, occupied), {})
    assert second["summary"]["move"] == 0


def test_all_assets_are_visible_but_special_paths_and_unsupported_types_stay_put():
    rows = [
        entry("Assets/Resources/load.mat"),
        entry("Assets/PromptToScene/door/model.fbx", "model"),
        entry("Assets/MyCode.cs", "script"),
        entry("Assets/Level.unity", "scene"),
        entry("Assets/GameConfig.asset", "data"),
        entry("Assets/ThirdParty/ref.mat"),
        entry("Assets/Addressed.mat", reason="Addressable address stays stable"),
    ]
    plan = organization.make_plan(scan(rows), {}, pinned=["Assets/ThirdParty/ref.mat"])
    assert plan["summary"]["scanned"] == 7 and plan["summary"]["skip"] == 7
    assert all(r["reason"] and r["destination"] == r["source"] for r in plan["entries"])


def test_rules_overrides_exclusions_and_source_groups_are_stable():
    rows = [entry("Assets/Castle/door mat.mat"), entry("Assets/Space/keep.mat")]
    settings = dict(
        group_by="source",
        exclude=["Assets/Space"],
        overrides={"Assets/Castle/door mat.mat": "城堡木门"},
        rules={"material": {"folder": "Surfaces", "prefix": "MAT_"}},
    )
    first = organization.make_plan(scan(rows), settings)
    assert (
        first["entries"][0]["destination"] == "Assets/GameAssets/Castle/Surfaces/MAT_城堡木门.mat"
    )
    assert first["summary"]["skip"] == 1
    renamed = [entry(first["entries"][0]["destination"])]
    second = organization.make_plan(
        scan(renamed), {k: v for k, v in settings.items() if k != "overrides"}
    )
    assert second["summary"]["move"] == 0


@pytest.mark.parametrize(
    "settings",
    [
        {"destination": "Packages/Project"},
        {"destination": "Assets/../Outside"},
        {"destination": "Assets/Resources/Unsafe"},
        {"rules": {"material": {"folder": "../Elsewhere"}}},
        {"rules": {"material": {"prefix": "bad/"}}},
        {"rename": "yes"},
        {"exclude": "Assets/x"},
        {"overrides": {"Assets/missing.mat": "X"}},
        {"group_by": "invented"},
    ],
)
def test_invalid_rules_fail_without_queuing_native_mutations(settings):
    with pytest.raises(ValueError):
        organization.make_plan(scan([entry("Assets/a.mat")]), settings)


def test_partial_scan_is_not_claimed_as_complete():
    value = scan([entry("Assets/a.mat")])
    value["truncated"] = True
    with pytest.raises(ValueError, match="smaller folder"):
        organization.make_plan(value, {})


def test_api_retains_exact_plan_hash_pagination_and_history(project):
    root = core.state_root(project)
    native = scan([entry("Assets/b.mat"), entry("Assets/a.mat")])
    core.atomic_json(root / "organization/scans" / (native["scan_id"] + ".json"), native)
    task = workbench.dispatch("organize", {"mode": "scan", "scope": "Assets"})
    queued = json.loads((root / "actions" / (task["request_id"] + ".json")).read_text())
    assert json.loads(queued["development_json"])["scope_path"] == "Assets"
    plan = organization.organize(None, "plan", scan_id=native["scan_id"], limit=1)
    assert plan["has_more"] and plan["total"] == 2
    second = organization.organize(None, "inspect", plan_id=plan["plan_id"], offset=1, limit=1)
    assert second["entries"][0]["source"] == "Assets/b.mat"
    task = organization.organize(None, "apply", plan_id=plan["plan_id"])
    queued = json.loads((root / "actions" / (task["request_id"] + ".json")).read_text())
    command = json.loads(queued["development_json"])
    raw = (root / "organization/plans" / (plan["plan_id"] + ".json")).read_bytes()
    assert command["plan_sha256"] == hashlib.sha256(raw).hexdigest()
    assert organization.organize(None, "history")["plans"][0]["plan_id"] == plan["plan_id"]


def test_annotations_follow_native_move_undo_once_without_renaming_later_unrelated_assets(project):
    root = core.state_root(project)
    original = "Assets/wood.mat"
    moved = "Assets/GameAssets/Materials/M_Wood.mat"
    annotation = dict(tags=["wood"], license="CC0", source="source-page", notes="artist credit")
    core.atomic_json(root / "project-library.json", {original: annotation})
    file = root / "organization/journals" / ("a" * 32 + ".json")
    record = dict(engine="unity", events=[dict(source=original, destination=moved)])
    core.atomic_json(file, record)
    organization.sync_annotations(root)
    assert core.read_optional_json(root / "project-library.json") == {moved: annotation}
    core.atomic_json(
        root / "project-library.json",
        {moved: annotation, original: {"notes": "different new asset"}},
    )
    organization.sync_annotations(root)
    assert (
        core.read_optional_json(root / "project-library.json")[original]["notes"]
        == "different new asset"
    )
    core.atomic_json(root / "project-library.json", {moved: annotation})
    record["events"].append(dict(source=moved, destination=original))
    core.atomic_json(file, record)
    organization.sync_annotations(root)
    organization.sync_annotations(root)
    assert core.read_optional_json(root / "project-library.json") == {original: annotation}


def test_unreal_object_path_annotations_follow_package_renames(project):
    root = core.state_root(project)
    core.atomic_json(root / "project-library.json", {"/Game/wood.wood": {"tags": ["wood"]}})
    core.atomic_json(
        root / "organization/journals" / ("b" * 32 + ".json"),
        dict(engine="unreal", events=[dict(source="/Game/wood", destination="/Game/Art/M_Wood")]),
    )
    organization.sync_annotations(root)
    assert core.read_optional_json(root / "project-library.json") == {
        "/Game/Art/M_Wood.M_Wood": {"tags": ["wood"]}
    }


def test_pins_material_reuse_paths_from_style_and_retained_source(project):
    root = core.state_root(project)
    core.atomic_json(root / "art-direction.json", dict(material_bindings={"wood": "Assets/a.mat"}))
    core.atomic_json(
        root / "work/test" / ("a" * 32) / "asset.json",
        dict(materials=[dict(reuse_path="Assets/b.mat")]),
    )
    assert organization.pinned_paths(root) == {"Assets/a.mat", "Assets/b.mat"}


def test_symlink_record_is_rejected(project, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    root = core.state_root(project)
    file = root / "organization/scans" / ("a" * 32 + ".json")
    file.parent.mkdir(parents=True)
    file.symlink_to(outside)
    with pytest.raises(ValueError, match="record"):
        organization.organize(None, "plan", scan_id="a" * 32)


def test_get_task_status_preserves_errors_while_synchronizing_metadata(project):
    root = core.state_root(project)
    revision = "a" * 32
    core.atomic_json(
        root / "action-receipts" / (revision + ".json"),
        dict(
            status="error",
            error="Destination is occupied",
            request_id=revision,
            development=dict(command="organize"),
        ),
    )
    result = workflow.job_status(None, revision)
    assert result["status"] == "error" and "occupied" in result["error"]


def test_repeat_apply_allows_metadata_already_moved_by_the_same_plan(project):
    root = core.state_root(project)
    value = scan([entry("Assets/oak.mat")])
    core.atomic_json(root / "organization/scans" / (value["scan_id"] + ".json"), value)
    plan = organization.organize(None, "plan", scan_id=value["scan_id"])
    destination = plan["entries"][0]["destination"]
    core.atomic_json(root / "project-library.json", {destination: {"notes": "moved credit"}})
    with pytest.raises(ValueError, match="Annotations changed"):
        organization.organize(None, "apply", plan_id=plan["plan_id"])
    core.atomic_json(
        root / "organization/journals" / (plan["plan_id"] + ".json"),
        {"status": "applied", "entries": [], "events": []},
    )
    assert organization.organize(None, "apply", plan_id=plan["plan_id"])["status"] == "queued"
