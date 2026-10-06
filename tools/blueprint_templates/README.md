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
