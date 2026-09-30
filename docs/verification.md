# Verification

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

## Recorded run: 2026-09-30

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
