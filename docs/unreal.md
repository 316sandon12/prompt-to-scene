# Unreal Editor adapter

For v0.4, the [setup app](QUICKSTART.zh-CN.md) installs and enables this bridge automatically. The steps below remain available for manual installation. The current release also supports art direction, baked PBR, semantic parts, contextual arrangement, draft selection, preview and source restore; see the [tool contract](architecture.md).

The adapter targets Unreal Editor 5.7. It is a content-only Python plugin with no compiled module or third-party Python dependencies. Ordinary static assets remain usable without automation. v0.7 interactive child Blueprints depend on the shipped `/PromptToScene/Templates/BP_PTSInteraction` parent, so retain the plugin content when using them. Python automation is editor-only; template runtime behavior uses ordinary engine Blueprint nodes.

## Install and use

1. Copy `unreal/PromptToScene` to `<Project>/Plugins/PromptToScene`.
2. Enable **Prompt-to-Scene** in Edit → Plugins and restart. Its descriptor enables the Python Editor Script Plugin and Editor Scripting Utilities dependencies.
3. Open your destination level and leave Play In Editor.
4. Configure the MCP server with `PTS_PROJECT=/absolute/path/MyProject.uproject`, `PTS_ENGINE=unreal`, and `PTS_BLENDER`.
5. Ask the AI to inspect the target, create a prop, and verify the exact request ID with `get_asset_status(..., wait_seconds=30)`.

The editor checks the local inbox every two seconds. Its heartbeat starts once the server creates `.prompt-to-scene/`. An old heartbeat is not evidence that an editor is still running. No Python remote execution setting is needed.

```bash
uv run prompt-to-scene --project /path/MyProject.uproject build crate --script examples/crate.py --position 2 3 0 --wait 30
```

Positions are **Unreal XYZ in meters**, so this becomes `[200, 300, 0]` in the editor. Blender authors in meters with Z up. The FBX importer performs scene-axis conversion with front-X enabled. See verification for measured bounds.

## Generated assets

```text
/Game/PromptToScene/<asset_id>/
  SM_<asset_id>       # combined static mesh
  M_<name_hash>      # one material per Blender material
  T_<texture_hash>   # optional normalized images
```

The adapter explicitly selects Unreal's FBX factory, keeping the import options stable without changing global Interchange settings. Exported material slots use deterministic ASCII IDs; original names remain in the manifest and material metadata.

Base color stays scene-linear. Metallic and roughness are scalar Default Lit inputs. Base-color textures use sRGB. Normal maps disable sRGB, use normal-map compression and flip the green channel for Blender's OpenGL-to-Unreal's DirectX convention. A generated normal graph applies the supplied strength. These graphs belong to the bridge.

All meshes in `Export` are combined into one Static Mesh. Preparation supports native LODs and box/convex/no collision. Interactive templates use separate base and moving meshes, with complex-as-simple collision and one reusable child Blueprint. This does not generate arbitrary Blueprint graphs, skeletal meshes or Nanite settings.

## Updates and identity

v0.7 creates editable door/chest/pickup child Blueprints. Call `TryInteract(WorldPosition)` in native centimeters, or use the optional aim-and-E demo input; hook project behavior through `OnInteracted`. The inherited component templates keep moving meshes available when placing a new Blueprint instance from Content Browser. Reconfiguration preserves explicitly protected materials and regeneration keeps interaction parameters. See [the development guide](DEVELOPMENT.zh-CN.md).

The shipped `.uasset` was saved with UE 5.7.2. Older engine asset compatibility and shipping builds are unverified. The maintainer-only generator in `tools/blueprint_templates` is excluded from the installed plugin and is unnecessary for end users.

The same asset ID keeps the same asset paths. Existing StaticMeshActors in the current level are located by the `PTS.Asset:<id>` tag and reused. Their GUID, transform, label and non-bridge tags are retained; manually duplicated instances are retained too. A `PTS.Revision:<request_id>` tag records the applied revision. Keep these identity tags for updates.

The lookup covers loaded Actors in the current level. Identity across unloaded World Partition cells or other unloaded levels is outside this version's scope. Run one consuming editor per target project.

Mesh geometry, generated material graphs and simple collision are managed content. Actor properties outside that content remain yours. Existing component material overrides are retained and may intentionally hide a generated material update. Assets are saved after import; the level stays dirty for you to save normally. There is no full rollback for partial native import failures.

Receipts contain native asset/material paths, Actor GUIDs, triangle counts, collision count, active level and bounds in meters. These fields come from the editor after placement.

## Troubleshooting

- **Still queued:** check the `.uproject`, enabled plugin, startup completion, Play In Editor state and heartbeat. In the Output Log's Python mode, `import prompt_to_scene_unreal; prompt_to_scene_unreal.import_pending()` explicitly processes pending work.
- **Unsupported material:** follow the Blender asset contract; bake procedural nodes externally first.
- **Updating:** the plugin is copied into your project. Update that copy and restart the editor too.
- **Automation:** scene placement needs the full editor with a working graphics device. `-run=pythonscript` commandlets and `-NullRHI` are rejected. Tests use `-ExecutePythonScript` with `-RenderOffscreen`.
- **Development:** `prompt_to_scene_unreal.stop()` unregisters polling. Restart after changing plugin files. `-PromptToSceneNoWatch` disables automatic polling for explicit integration tests.

Startup follows Epic's [Python editor scripting documentation](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python?application_version=5.7). API details are in the [Unreal 5.7 Python reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/?application_version=5.7).
