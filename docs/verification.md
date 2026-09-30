# Verification

## v0.3 — recorded on 2026-09-30

Environment: macOS 15.8 / Apple M3 Pro, Python 3.11.16, Blender 4.2.0, Unity 2022.3.62f3c1 (China build), URP 14.0.11, Unreal Editor 5.7.2. Native client checks used Codex CLI 0.159.0 and DeepSeek Harness `@deepseek-ai/dsh` 0.2.0-rc.1.

| Check | Result |
| --- | --- |
| Python/protocol/setup tests | 48 passed; lint and formatting passed |
| Blender recipes | Crate 1,404, table 540, chair 864, sign 216 triangles; actual background export |
| Unity Built-in and URP | Initial/revised import, textures and saved `.blend` publishing passed |
| UE native regression | Geometry, PBR, collision, Unicode material mapping, identity and textures passed |
| All three engine paths, real MCP | Recipe creation → grounded placement → selection → duplicate-instance isolation → transform → undo → tint → structural revision → source restore → edit undo → PNG → worker cancellation |
| Repeated in-session revisions | Original asset/object identity and collider=false preserved; selected-instance tint retained through shared geometry updates |
| Codex native plugin | Isolated marketplace registration; 16 tools discovered; app-server invoked `list_projects` successfully |
| Harness native bundle | Isolated profile installation/config composition; real ToolRuntime invoked the registered MCP tool |
| Setup interface | Local browser layout inspected; token/origin rejection and connected-project state tested |
| macOS portable app | Built locally; actual frozen stdio server, bridge extraction, setup HTML/API checked |
| Windows/macOS release builds | See the [Portable apps workflow](https://github.com/316sandon12/prompt-to-scene/actions/workflows/package.yml) for the build attached to the release |

Native host verification invokes tools through each host's actual plugin runtime without asking an LLM to model an asset. The engine workflow uses an MCP client and deterministic recipes; it does not measure arbitrary natural-language modeling quality. Mac binary tests include a real detached Blender job after its MCP parent exits. Windows package tests do not establish Windows Unity/UE compatibility.

The fixture makes a floor at one meter, verifies automatic placement on it, then creates two instances. Tests assert that selected edits affect only one instance and shared model changes retain both identities. Unity runs the real editor in graphics-enabled batch mode with a test driver pumping its importer; UE uses the normal live watcher in a full graphics-enabled editor. Preview PNGs were visually inspected; lighting differs between pipelines. The fixture scenes are not saved after interactive edits.

Sanitized machine-readable summary: [verification-v0.3.json](verification-v0.3.json). [Unity preview](images/workflow-unity.png) and [Unreal preview](images/workflow-unreal.png) are actual tool results. Full logs remain local because they can contain personal paths or editor licensing information.

### Reproduce v0.3

First run the relevant engine smoke test below. Then use the disposable project it prints:

```bash
uv run python tools/workflow_smoke.py --project /repo/.local/unity-smoke-EXAMPLE --editor /absolute/path/to/Unity
uv run python tools/workflow_smoke.py --project /repo/.local/unreal-smoke-EXAMPLE/Smoke.uproject --editor /absolute/path/to/UnrealEditor-Cmd
uv run python tools/codex_plugin_smoke.py
uv run python tools/harness_plugin_smoke.py --dsh /absolute/path/to/dsh
uv run --group build python tools/package_app.py
uv run python tools/packaged_smoke.py dist/bin/prompt-to-scene-core --blender /absolute/path/to/blender
```

On Windows the core executable ends in `.exe`; omit `--blender` to verify only the self-contained package without a Blender installation. The two client tests create disposable host configuration directories, use no LLM/API key and do not alter the user's real client profiles. Harness's existing Node/pnpm environment must be available.

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
