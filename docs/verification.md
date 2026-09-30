# Verification

## v0.5 — recorded on 2026-09-30

Environment: macOS 15.8 / Apple M3 Pro, Blender 4.2.0, Unity 2022.3.62f3c1 Built-in and URP 14.0.11, Unreal Editor 5.7.2. These are real Blender/editor runs; no LLM was asked to simulate results.

| Check | Result |
| --- | --- |
| Python/MCP/protocol | 100 tests passed, lint and formatting passed; includes external source checksums, dependency paths/redirects, catalog fallback, LOD manifests, comparison identity and partial kit submissions. |
| External formats | Actual GLB, FBX and Blender fixture files imported, baked and exported. Live Poly Haven search/download and glTF with external textures passed. |
| Measured simplification | Textured 14,976-triangle fixture reduced to 3,358, with 1,678/838-triangle LODs. Worst sampled base-mesh error was 0.2871% of that object's diagonal. A strict rejected budget retained the original geometry and published no inbox request. |
| Unity Built-in / URP / UE | Real MCP external preview → publication, native LOD counts/triangle counts, PBR textures and color spaces, dimensions, collision, and revision identity passed. Unity cooked colliders were also raycast-tested. |
| Repreparation | Increasing the budget recovered detail from the retained 14,976-triangle original, producing 7,678 triangles; removing LODs/collision produced one native LOD and zero collisions. Existing object identity and position survived. |
| Native comparisons | Before/after PNGs returned through MCP with an unchanged saved camera frame, in all three engine paths. Project lighting differs between engines. |
| Kits and selection | Reading-corner kit imported in all three paths; selecting its chair and editing the backrest preserved every other part's geometry hash. |
| Structural alternatives | All 27 drafts (nine kinds × three variants) rendered three source views and remained outside engine imports. |
| Hosts and portable app | Real isolated Codex app-server discovered 34 tools; Harness ToolRuntime invocation passed. Local frozen macOS app served MCP/setup/JS and completed detached recipe and external-model jobs after the MCP parent exited. |
| Windows/macOS portable CI | Both OS builds, 100 tests per OS and frozen app/setup checks passed in [release workflow 36726686142](https://github.com/316sandon12/prompt-to-scene/actions/runs/36726686142); both download archives published. |
| Public downloads | Both ZIP SHA-256 values matched. The downloaded macOS app passed signature verification, 34-tool stdio/setup checks and real detached Blender recipe/external-intake jobs. Windows executable was tested in CI. |
| Browser workshop | Actual Poly Haven search → isolated source preview → comparison → publication to Unity passed; real source views and native review gallery loaded with zero observed console warnings/errors. |

Actual images: [original fixture](images/prepared-model-before.png), [prepared fixture](images/prepared-model.png), [Poly Haven model](images/polyhaven-prepared.png), [Unity before](images/prepared-unity-before.png) / [after](images/prepared-unity-after.png), [UE before](images/prepared-unreal-before.png) / [after](images/prepared-unreal-after.png). The Poly Haven example is [Ceramic Vase 03 by James Ray Cock](https://polyhaven.com/a/ceramic_vase_03), CC0; Powered by Poly Haven. The native fixture uses sparse project lighting, not a final art presentation.

| Chair structure 1 | Chair structure 2 | Chair structure 3 |
| --- | --- | --- |
| ![Slatted chair](images/chair_0.png) | ![Cross-back chair](images/chair_1.png) | ![Armchair](images/chair_2.png) |

The sampled geometry check is not a formal maximum-distance or aesthetic guarantee. Colliders approximate shape. The external tests cover static opaque PBR, not arbitrary shaders, rigs or animation. The 27-draft run checks default parameters, not every possible dimension/style combination. Windows native Unity/UE remains untested; portable CI evidence is recorded separately in [the machine-readable results](verification-v0.5.json).

### Reproduce v0.5

Use the disposable `.local/*smoke-*` projects described below. The native driver starts a new test scene.

```bash
uv run pytest -q
/path/to/blender --background --factory-startup --python tools/external_fixture.py -- .local/v05-fixtures
uv run python tools/variants_smoke.py
uv run python tools/authoring_smoke.py --project /repo/.local/unity-smoke-EXAMPLE --editor /path/to/Unity --preparation
uv run python tools/authoring_smoke.py --project /repo/.local/unreal-smoke-EXAMPLE --editor /path/to/UnrealEditor --preparation
uv run python tools/codex_plugin_smoke.py
uv run python tools/harness_plugin_smoke.py --dsh /path/to/dsh
uv run --group build python tools/package_app.py
uv run python tools/packaged_smoke.py dist/bin/prompt-to-scene-core --blender /path/to/blender
```

The new editor scenario invokes import/publication/repreparation/review/kit/selection tools through real MCP. Native editor assertions independently read actual LOD geometry and collision counts. Omit `--preparation` to run the existing material reuse, tint, arrangement and undo regression; add `--variants` for candidate selection.

## v0.4 — recorded on 2026-09-30

Environment: macOS 15.8 / Apple M3 Pro, Blender 4.2.0, Unity 2022.3.62f3c1 (China build), URP 14.0.11, Unreal Editor 5.7.2. Native host versions: Codex CLI 0.159.0 and DeepSeek Harness 0.2.0-rc.1.

| Check | Result |
| --- | --- |
| Python, protocol and setup | 71 tests passed; lint/format passed. Includes geometry/material lock independence, project style isolation, layout collisions, setup without reverse DNS and non-destructive process probes. |
| Actual Blender library | All nine recipes exported, baked PBR maps and three source views checked; no draft inbox entries. Native vertex hashes verify frozen parts and material-only geometry invariance. |
| Unity Built-in, URP and UE | Real MCP creation of matching table/chair/stool; native baked-map and data-texture color-space checks; backrest-only revision preserves asset identity, other parts and instance tint. |
| Layout in all three paths | Four chairs around a selected table; undo removes three copies and restores the original; rearrangement and fitting a stool underneath succeed. Native PNG returned. |
| Existing material reuse | Unity Built-in and UE reuse an existing material reference; its asset file hash is unchanged. |
| Draft selection | Two real cabinet drafts leave Unity scene instance count unchanged; source image returns through MCP; choosing a draft bakes and imports a final cabinet. |
| Codex and Harness | Isolated real host registration and tool invocation passed. Codex discovered all 26 tools. No paid LLM calls needed. |
| Local portable macOS app | Frozen stdio tools, embedded bridge, local setup HTML/API and detached Blender baking pass after MCP exits. |
| Windows/macOS portable CI | Both builds, 71 tests per OS and actual frozen stdio/setup checks passed in [release workflow 36715117293](https://github.com/316sandon12/prompt-to-scene/actions/runs/36715117293). |
| Public release download | Both archive SHA-256 values matched. The downloaded macOS app passed signature verification, 26-tool stdio, a detached Blender PBR/preview job and setup HTML/API checks. |
| Workshop UI | Saved style and submitted three real barrel drafts through the browser; semantic parts, completed candidate cards, selected-candidate status and multi-view images checked. No browser warnings/errors observed. |

[Sanitized results](verification-v0.4.json). Actual renders: [Blender chair](images/authoring-chair.png), [cabinet](images/authoring-cabinet.png), [barrel](images/authoring-barrel.png), [Unity scene](images/authoring-unity.png), [UE scene](images/authoring-unreal.png). The native scenes use sparse fixture lighting; they verify engine geometry/material state, not production lighting or visual equivalence. Blender views use consistent studio lighting. These are actual model renders, not generated concept images.

These checks exercise deterministic recipes and real tools, not arbitrary LLM modeling quality. Baking was exercised at the mobile tier; higher tiers increase resolution/detail but are not a performance guarantee. Layout uses conservative world-axis bounds and keeps instance orientation. Windows portable CI is separate from native Windows editor validation; Windows Unity/UE has not been tested. Full logs remain local because they can contain personal paths and editor licensing details.

### Reproduce v0.4

Use disposable `.local/*smoke-*` projects created by the engine smoke scripts below. The authoring driver creates a new fixture scene, not a user's working scene.

```bash
uv run pytest -q
uv run python tools/art_smoke.py
uv run python tools/authoring_smoke.py --project /repo/.local/unity-smoke-EXAMPLE --editor /absolute/path/to/Unity --variants
uv run python tools/authoring_smoke.py --project /repo/.local/unreal-smoke-EXAMPLE --editor /absolute/path/to/UnrealEditor-Cmd
uv run python tools/codex_plugin_smoke.py
uv run python tools/harness_plugin_smoke.py --dsh /absolute/path/to/dsh
uv run --group build python tools/package_app.py
uv run python tools/packaged_smoke.py dist/bin/prompt-to-scene-core --blender /absolute/path/to/blender
```

`art_smoke.py` verifies one style per recipe across the three styles; it does not test every parameter combination. Native authoring checks install the current bridge into disposable projects. Use `--variants` for the additional source-study/publish workflow. The package test starts the actual frozen app, exits its MCP parent while a detached worker runs, checks baked output, then checks setup startup. Windows binary names end in `.exe`; omit `--blender` on machines without Blender.

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
| Codex native plugin | Isolated registration and version upgrade; 16 tools; app-server invoked `list_projects` successfully |
| Harness native bundle | Isolated profile installation/config composition; real ToolRuntime invoked the registered MCP tool |
| Setup interface | Local browser layout inspected; token/origin rejection and connected-project state tested |
| macOS portable app | Built locally; actual frozen stdio server, bridge extraction, setup HTML/API checked |
| Windows/macOS portable builds | Both OS builds, pytest and frozen MCP/setup checks passed in GitHub Actions; see the [release workflow](https://github.com/316sandon12/prompt-to-scene/actions/workflows/package.yml) |

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
