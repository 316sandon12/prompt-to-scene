# Verification

## v0.2 — recorded on 2026-09-30

Environment: macOS 15.8 on Apple M3 Pro, Python 3.11.16, Blender 4.2.0, Unity 2022.3.62f3c1 (China build), URP 14.0.11, Unreal Editor 5.7.2 (CL 49658320).

| Check | Result |
| --- | --- |
| Python/MCP/Unreal request validation | 37 tests passed |
| Unity Built-in and URP regression | First import, revision, textures and saved-source publishing passed |
| v0.1 → v0.2 Unity upgrade | Existing prefab GUID, scene position and custom root component survived the new FBX material IDs |
| Python packaging | Wheel and source archive built; Unreal plugin included in source archive |
| Unreal native import | One combined mesh, 1,404 triangles, native materials and box collision |
| Unreal revision | Height changed from 1.00 m to 1.25 m; green material revision applied |
| Unreal identity and user properties | Asset path and Actor GUID unchanged; position, yaw, scale, label, custom tag and shadow setting preserved |
| Unreal textures | Unicode material name, sRGB base color, non-sRGB normal, normal compression/green-channel flip, metallic and roughness verified |
| Saved `.blend` | Republished with packed textures; original file hash unchanged |
| Live MCP → Blender → automatic Unreal polling | Real stdio tool call and exact-request wait returned imported; editor asserted one Actor at the requested position |

The initial UE crate bounds measured approximately **1.005 × 0.992 × 1.000 meters**, confirming horizontal axis conversion and meter scale. The revision was **1.005 × 0.992 × 1.250 meters**. The imported Actor at input `[2, 0, 3]` was at `[200, 0, 300]` editor centimeters. The separate live workflow used `[1.5, -2, 0]` meters and checked the resulting Actor at `[150, -200, 0]` centimeters.

Sanitized receipts: [verification-v0.2.json](verification-v0.2.json). These checks validate supported geometry, material wiring and scene state, not pixel-equivalent rendering or arbitrary AI modeling quality. Unreal emits unrelated startup/FBX warnings on this installation; successful test markers and explicit scene assertions are required in addition to a zero exit code. Windows/Linux and other engine versions are not yet verified.

### Reproduce Unreal tests

```bash
uv run python tools/unreal_smoke_test.py --unreal /absolute/path/to/UnrealEditor-Cmd

# Use the disposable project path printed by the previous command:
uv run python tools/unreal_live_smoke.py --unreal /absolute/path/to/UnrealEditor-Cmd --project /repo/.local/unreal-smoke-EXAMPLE/Smoke.uproject
```

On Windows use `UnrealEditor-Cmd.exe`. The tests start the **full editor** with `-ExecutePythonScript` and `-RenderOffscreen`, not a Python commandlet. A functioning graphics device is required: UE 5.7 cannot place Actors through this API with `-NullRHI`. The test projects are disposable and isolated under `.local/`. The live test intentionally leaves automatic polling enabled and sends build/status requests through a real MCP client; its driver never calls `import_pending`.

## Python and Unity commands

Run the fast checks:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The real-engine smoke test creates an isolated disposable project under `.local/`, invokes Blender, opens Unity in batch mode, imports a crate, revises it, then checks prefab identity and scene state. It also verifies base-color/normal textures, republishes a saved `.blend`, and rejects an unsupported procedural shader. It never opens an existing user project.

```bash
uv run python tools/smoke_test.py --unity /absolute/path/to/Unity
uv run python tools/smoke_test.py --unity /absolute/path/to/Unity --urp
```

Set `PTS_BLENDER` if Blender is not on PATH or in the standard macOS app location. Unity must be installed and licensed. A missing editor/license is a failure or limitation, not a passing engine test.

`--urp` installs URP 14.0.11 in the disposable Unity 2022.3 project. Successful runs print `PASS` and leave receipts, logs and `evidence.json` in that test project. Logs may contain local paths and licensing details; inspect them before sharing.

## Historical v0.1 run: 2026-09-30

Environment: macOS 15.8, Apple Silicon; Python 3.11.16; Blender 4.2.0; licensed Unity 2022.3.62f3c1. The editor build is the Unity China variant. Other editor versions, Windows and Linux have not been verified.

| Check | Result |
| --- | --- |
| Python/MCP tests | 14 passed |
| Ruff lint and format | Passed |
| Python wheel and source package build | Passed; Blender export driver included |
| Built-in: first import + material revision | Passed |
| URP 14.0.11: first import + material revision | Passed |
| Both pipelines: base-color + tangent normal texture import | Passed |
| Both pipelines: publish saved `.blend`, original file hash unchanged | Passed |
| Unsupported procedural texture | Rejected before publishing a request |

Each crate import produced **13 meshes and 1,404 triangles**, with bounds approximately **0.992 × 1.000 × 1.005 meters**. Both pipelines preserved the prefab GUID, the scene instance at `[2, 0, 3]`, and a custom Rigidbody component with mass 7 through a material revision. Rebuilding requested a different initial position to verify that an existing instance was not moved or duplicated.

The textured fixture verified native texture import settings (sRGB base color, Non-Color normal), shader assignment, normal-map keyword/strength, metallic, roughness-to-smoothness conversion, and `collider=false`. Saved sources retained packed images. These checks verify data transfer and material wiring, not pixel equivalence across Blender and Unity.

The sanitized engine receipts are in [verification-results.json](verification-results.json). `tools/UnitySmoke.cs` contains the engine assertions. The Python tests include a real MCP stdio subprocess for discovery, status and error reporting; licensed engine tests call the same core build implementation directly and explicitly invoke the Unity importer. The idle editor polling loop is not exercised by the batch test.

## Preview reproduction

The README image is a Unity render of the included crate. It stages two color variants with a camera and lights; it is not a capture of a natural-language chat session. After a successful **Built-in** smoke test, copy `tools/UnityPreview.cs` into that disposable project's `Assets/Editor/`, then run:

```bash
/absolute/path/to/Unity -batchmode -projectPath /path/to/disposable/project -executeMethod UnityPreview.Run -logFile /path/to/preview.log
```

Omit `-nographics` for this command. It writes `preview.png` in the project root and exits without saving the staged scene. A working graphics device is required.

CI runs Python and MCP protocol checks only; a green CI badge does not imply licensed Unity verification. No UE adapter or UE verification is included in v0.1.
