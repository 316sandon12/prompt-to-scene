# Prompt-to-Scene

**Ask your AI to build a prop in Blender, place it in Unity, and revise the same asset.**

[简体中文](README.zh-CN.md) · [Quickstart](#quickstart) · [Asset contract](docs/asset-contract.md) · [Architecture](docs/architecture.md)

An open-source MCP server and Unity package for a complete **build → import → verify → revise** workflow. Your existing AI client writes Blender Python; this project runs Blender, transfers a validated asset, creates Unity materials and a prefab, places it in the active scene, and returns an import receipt.

> **v0.1 experimental:** static opaque props; Unity Built-in/URP. Unreal support is planned, not implemented. This project does not include an LLM or an image-to-3D model. Natural-language interpretation comes from your MCP-compatible AI client.

![Two material variations of the included crate, rendered in Unity](docs/images/unity-preview.png)

*Actual Unity render of the included Blender recipe, staged with two material variations. See the [real-engine checks](docs/verification.md).*

## The interaction

> “Create a one-meter wooden crate with iron straps in Blender. Put it at [2, 0, 3] in Unity and add a collider.”
>
> “Make the wood darker and the straps thinner. Update the same crate.”

The AI calls `build_asset`, then `get_asset_status`. Reusing the asset ID updates the existing prefab. Existing instance transforms and prefab-root components are preserved. A queued export is never reported as a successful Unity import.

## What works

- Four MCP tools: `inspect_target`, `build_asset`, `publish_blend`, `get_asset_status`.
- Real background Blender execution; editable `.blend` source retained per revision.
- Native FBX import into Unity; no additional Unity import package required.
- Principled BSDF base color, metallic and roughness; optional direct base-color and tangent normal textures.
- Materials adapted to Built-in Standard or URP Lit.
- Stable asset/material/prefab paths, automatic scene placement and box collider.
- Import receipts with request ID, prefab GUID, mesh/triangle counts and bounds.
- A CLI and a reproducible crate recipe, usable without an AI subscription.

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- Blender 4.2+ (first verification target: 4.2).
- Unity 2022.3+ with an activated editor; Built-in or URP.
- An MCP-compatible client for natural-language use. CLI use does not require one.

Versions outside the recorded verification matrix are not a compatibility guarantee. See [verification](docs/verification.md).

## Quickstart

### 1. Get the server

```bash
git clone https://github.com/316sandon12/prompt-to-scene.git
cd prompt-to-scene
uv sync --locked
```

### 2. Install the Unity package

In Unity: **Window → Package Manager → + → Add package from disk**. Select:

```text
unity/Packages/com.prompttoscene.bridge/package.json
```

Keep the cloned repository in place. Open a scene in the target project, leave Play Mode, and wait for compilation to finish. Both applications operate on your local machine; Blender is started as a separate background process by the server. You do not need a Blender MCP addon for this path.

### 3. Register the MCP server

Use your client's MCP server settings with this configuration. Replace every example path with your own **absolute** path:

```json
{
  "mcpServers": {
    "prompt-to-scene": {
      "command": "/absolute/path/to/uv",
      "args": ["--directory", "/absolute/path/to/prompt-to-scene", "run", "--locked", "prompt-to-scene-mcp"],
      "env": {
        "PTS_UNITY_PROJECT": "/absolute/path/to/MyUnityProject",
        "PTS_BLENDER": "/absolute/path/to/blender"
      }
    }
  }
}
```

On macOS the usual Blender executable is `/Applications/Blender.app/Contents/MacOS/Blender`. On Windows use the full path to `blender.exe`; backslashes in JSON must be escaped. The project path selects the destination explicitly, even if several Unity editors are open.

Try the interaction above. Ask the AI to inspect the target, follow the [asset contract](docs/asset-contract.md), and verify the returned request ID. Unity polls for work every two seconds while idle. If you receive `queued`, the engine has not confirmed an import yet.

### CLI smoke test

With Unity open and the package installed:

```bash
uv run prompt-to-scene --project /path/to/MyUnityProject build crate --script examples/crate.py --position 2 0 3
uv run prompt-to-scene --project /path/to/MyUnityProject status crate
```

The result appears under `Assets/PromptToScene/crate/`. Save your scene normally; the bridge marks it dirty but does **not** silently save existing scenes. Add `.prompt-to-scene/` to your Unity project's `.gitignore` to exclude the local queue, logs and source revisions.

To publish a model created through another Blender AI tool, save it with its asset meshes inside a collection named `Export`, then call `publish_blend`. The original file is opened with auto-execution disabled and is not overwritten.

For a self-contained textured example, use `--script examples/textured_cube.py` with a different asset ID. It creates its own UVs, checker texture and normal map, without downloads.

## Revision behavior

Use the same `asset_id` to regenerate the same asset. Each `build_asset` script describes the entire asset from scratch; there is no persistent interactive Blender session. To edit an existing file, use another Blender tool and `publish_blend`.

- Source revisions remain in `<UnityProject>/.prompt-to-scene/work/`.
- Imported `.meta` files and prefab/material GUIDs remain stable.
- Existing scene instance positions/rotations/scales and prefab-root components remain intact.
- The prefab's `Visual` subtree, root box collider and managed material properties are owned by the bridge. Put custom scripts on the prefab root; do not put manual overrides inside `Visual`.
- Renaming a Blender material creates a new material identity. Removed material/texture files are retained rather than automatically deleted.
- A pending import must finish before rebuilding that asset. Different asset IDs have independent requests.

## Boundaries

This version deliberately rejects unsupported material nodes instead of silently exporting a different appearance. No automatic procedural texture baking, roughness/metallic textures, transparency, rigs, animation, LOD generation or UE adapter yet. Materials can differ under different engine lighting/color management; there is no pixel-identical rendering guarantee.

Blender scripts execute as your local user and are **not sandboxed**. Use trusted scripts and your AI client's tool permissions. Generated `.blend` files are local artifacts; no model or project is uploaded by this bridge. Import failures are reported, but there is no full AssetDatabase rollback after a mid-import engine error. Keep projects under version control.

## Development

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

For real Blender/Unity integration verification, see [verification](docs/verification.md). CI exercises Python and the MCP protocol; Unity requires a licensed editor and is tested separately.

## Roadmap

- [x] AI-authored Blender Python → Unity scene with import receipts
- [x] Stable asset identity and revisions
- [ ] Texture baking and broader PBR input coverage
- [ ] Engine-side preview screenshots returned to the AI
- [ ] Unreal Engine adapter using the same task/receipt contract
- [ ] Interactive Blender-session adapter and richer scene placement

## Related projects

[MCP for Blender](https://github.com/ahujasid/mcp-for-blender), [MCP for Unity](https://github.com/CoplayDev/unity-mcp), and [Blender Tools](https://github.com/EpicGames/BlenderTools) are useful adjacent projects. This repository is an independent implementation and does not vendor their code. It can receive a saved `.blend` produced by another tool through `publish_blend`.

## License

MIT. See [LICENSE](LICENSE). Blender, Unity and your AI client have their own licenses. Example geometry is generated by the included original Python recipe.
