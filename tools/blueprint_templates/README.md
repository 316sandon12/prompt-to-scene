# Maintainer-only Blueprint template builder

Users install `unreal/PromptToScene`, including its existing `.uasset`. They do **not** need this C++ plugin or a compiler. The generated parent uses only engine Blueprint nodes and derives from `StaticMeshActor`; the builder module is not a runtime dependency.

To rebuild with UE 5.7.2 and its supported compiler:

1. Create a disposable editor project. Copy this directory into `Plugins/PTSTemplateBuilder` and the repository's `unreal/PromptToScene` into `Plugins/PromptToScene`. Enable both plugins.
2. Build the project editor target using Unreal Build Tool. Keep all generated build files in the disposable project, outside this source directory.
3. Run `UnrealEditor-Cmd` with the **absolute** `.uproject` path, `-unattended -nullrhi -nosound -run=pythonscript` and `-script=/absolute/path/to/generate.py`. The script rescans, deletes and replaces only the designated generated template in that disposable project's PromptToScene content.
4. Require process exit code zero and `PTS TEMPLATE BUILT` in the log. Copy `Content/Templates/BP_PTSInteraction.uasset` back to the repository.
5. Run `tools/development_smoke.py` in a **different disposable project containing only the normal PromptToScene plugin**. It verifies that all runtime behaviors work without this C++ module.

The C++ source constructs typed native K2 nodes, validates connections and compiles the Blueprint before saving. Keep the built template and generator source together in a change. Saving with a newer engine can prevent older engines from loading the asset; report the tested version explicitly.

## Native asset workshop (v0.9)

The same builder produces `EUW_PTSWorkshop.uasset`, an Editor Utility Widget with ordinary UMG controls and typed `OnClicked` events calling the engine's Python Script Library. It has no dependency on this builder at installation or runtime.

Follow steps 1–3 above using `generate_workshop.py` instead of `generate.py`. A Blueprint-only host uses the `UnrealEditor` target with `-Project=/absolute/path/to/HostProject.uproject`. Require commandlet exit code zero and `Python script executed successfully`; copy `Content/Templates/EUW_PTSWorkshop.uasset` back to the repository. Open the normal plugin in a separate UE 5.7.2 project and check the Tools/Content Browser entry, selection operations and retained before/after images. `tools/unreal_pipeline_driver.py` plus `tools/pipeline_smoke.py` exercise native operations without installing the C++ builder in that project.

## Native game UI and linked item templates (v0.13)

Run `generate_game_ui.py` after building the module to produce `BP_PTSGameItem`,
`BP_PTSItemPickup`, and inventory/HUD/pause Widget Blueprints plus their UI hosts.
Copy all eight generated `.uasset` files into the normal plugin. These reference only
stock engine classes and the existing interaction template. Validate with
`tools/creations_smoke.py --engine unreal --editor <UnrealEditor>` in a separate
normal-plugin fixture. It checks actual PIE events, native references and manual
layout/data retention, including a real icon rendered from retained Blender source.

## Gameplay rules and dynamic screens (v0.14)

Build the current module in the disposable project, then run these scripts in order:

1. `generate_gameplay.py`: rule DataAsset, SaveGame, project adapter interface and game session.
2. `generate.py`: the interaction parent, now with rule guards and completed-state restoration.
3. `generate_game_ui.py`: item/pickup assets, dynamic inventory/HUD/pause widgets and hosts.
4. `generate_adapter_example.py`: the editable project adapter actor in `Content/Examples`.

Copy the generated `.uasset` files from `Content/Templates` and `Content/Examples` back
to the normal plugin. All runtime graphs use engine nodes; the normal project must
contain only the installable PromptToScene plugin during validation.

`tools/unreal_gameplay_driver.py` loads or creates `/Game/GameplayFixture`, writes
`.prompt-to-scene/gameplay-ready`, and processes `gameplay-command.json` containing
`{"operation":"play"}` or `{"operation":"stop"}`. Launch it with
`-ExecutePythonScript=/absolute/path/to/tools/unreal_gameplay_driver.py`; connect the
fixture and create the default `apothecary` art kit before requesting Play. The kit
must finish before the command is written. Require `gameplay-play-passed`,
`gameplay-command-done`, and no `gameplay-error.txt`. It checks actual PIE transactions,
UI events, save restoration/protection, pagination, HUD, pause and adapter rejection.
Use `PTS_SCREEN_PREFIX` only when deliberately testing fresh screens in a reused fixture.

The Unity counterpart is `tools/UnityGameplay.cs`, installed in a disposable project's
`Assets/Editor`, with `tools/FixtureProjectAdapter.cs` under `Assets`. Launch Unity with
`-executeMethod UnityGameplay.Run`; connect the project, create the same default art
kit, and use the same marker commands. Keep both fixtures under `.local/` and remove
them after preserving the verification summary and final visual evidence.

Existing project Widget Blueprints contain copied graphs. Updating the plugin does
not replace those graphs or discard hand-authored UI; use new screen IDs to exercise
the new templates. The committed assets were saved with UE 5.7.2.
