# Maintainer-only Blueprint template builder

Users install `unreal/PromptToScene`, including its existing `.uasset`. They do **not** need this C++ plugin or a compiler. The generated parent uses only engine Blueprint nodes and derives from `StaticMeshActor`; the builder module is not a runtime dependency.

To rebuild with UE 5.7.2 and its supported compiler:

1. Create a disposable editor project. Copy this directory into `Plugins/PTSTemplateBuilder` and the repository's `unreal/PromptToScene` into `Plugins/PromptToScene`. Enable both plugins.
2. Build the project editor target using Unreal Build Tool. Keep all generated build files in the disposable project, outside this source directory.
3. Run `UnrealEditor-Cmd` with the **absolute** `.uproject` path, `-unattended -nullrhi -nosound -run=pythonscript` and `-script=/absolute/path/to/generate.py`. The script rescans, deletes and replaces only the designated generated template in that disposable project's PromptToScene content.
4. Require process exit code zero and `PTS TEMPLATE BUILT` in the log. Copy `Content/Templates/BP_PTSInteraction.uasset` back to the repository.
5. Run `tools/development_smoke.py` in a **different disposable project containing only the normal PromptToScene plugin**. It verifies that all runtime behaviors work without this C++ module.

The C++ source constructs typed native K2 nodes, validates connections and compiles the Blueprint before saving. Keep the built template and generator source together in a change. Saving with a newer engine can prevent older engines from loading the asset; report the tested version explicitly.
