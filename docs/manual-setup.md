# Manual setup and CLI

For contributors and other MCP clients. Most users should use the [setup app](../README.md#install). These explicit environment settings override the shared setup connection.

### 1. Get the server

```bash
git clone https://github.com/316sandon12/prompt-to-scene.git
cd prompt-to-scene
uv sync --locked
```

### 2a. Unity: install the package

In Unity: **Window → Package Manager → + → Add package from disk**. Select:

```text
unity/Packages/com.prompttoscene.bridge/package.json
```

Keep the cloned repository in place. Open a scene in the target project, leave Play Mode, and wait for compilation to finish. Both applications operate on your local machine; Blender is started as a separate background process by the server. You do not need a Blender MCP addon for this path.

### 2b. Unreal: install the plugin

Copy `unreal/PromptToScene` into `<YourUnrealProject>/Plugins/PromptToScene`. In Unreal, enable **Edit → Plugins → Prompt-to-Scene** and restart the editor. The plugin declares its Python Editor Script Plugin and Editor Scripting Utilities dependencies. Open a level and leave Play In Editor.

The [v0.2.0 release](https://github.com/316sandon12/prompt-to-scene/releases/tag/v0.2.0) also includes a standalone Unreal plugin ZIP. Extract its `PromptToScene` folder into the project's `Plugins` folder.

The plugin automatically watches the project inbox. No remote-execution setting, network listener or C++ build is required. Use the full editor with graphics enabled; commandlets and `-NullRHI` do not support this scene-placement workflow. See the [Unreal guide](unreal.md).

### 3. Register the MCP server

Use your client's MCP server settings with this configuration. Replace every example path with your own **absolute** path:

```json
{
  "mcpServers": {
    "prompt-to-scene": {
      "command": "/absolute/path/to/uv",
      "args": ["--directory", "/absolute/path/to/prompt-to-scene", "run", "--locked", "prompt-to-scene-mcp"],
      "env": {
        "PTS_PROJECT": "/absolute/path/to/MyUnityProject",
        "PTS_ENGINE": "unity",
        "PTS_BLENDER": "/absolute/path/to/blender"
      }
    }
  }
}
```

On macOS the usual Blender executable is `/Applications/Blender.app/Contents/MacOS/Blender`. On Windows use the full path to `blender.exe`; backslashes in JSON must be escaped. The project path selects the destination explicitly, even if several Unity editors are open.

For Unreal, set `PTS_PROJECT` to `/absolute/path/to/MyProject/MyProject.uproject` and `PTS_ENGINE` to `unreal`. Omit `PTS_ENGINE` for automatic detection. The legacy `PTS_UNITY_PROJECT` setting still works for Unity. Register two separately named MCP servers if you want both engines available to the AI at once.

Try the interaction above. Ask the AI to inspect the target, follow the [asset contract](asset-contract.md), and verify the returned request ID. Editors poll for work every two seconds while idle. `queued` means the engine has not confirmed an import yet. Positions always use **target-engine XYZ in meters**: Unity is Y-up; Unreal is Z-up and converts these values to centimeters.

### CLI smoke test

With the chosen editor open and the adapter installed:

```bash
uv run prompt-to-scene --project /path/to/MyUnityProject build crate --script examples/crate.py --position 2 0 3 --wait 30
uv run prompt-to-scene --project /path/to/MyUnityProject status crate

# Unreal: ground-level placement, coordinates in meters
uv run prompt-to-scene --project /path/to/MyProject.uproject build crate --script examples/crate.py --position 2 3 0 --wait 30
```

Results appear under `Assets/PromptToScene/crate/` in Unity or `/Game/PromptToScene/crate/` in Unreal. Save your scene/level normally; the bridge does **not** silently save existing scenes. Add `.prompt-to-scene/` to your project's `.gitignore` to exclude the local queue, logs and source revisions. CLI exit code 2 means an engine error, a superseded request or a wait timeout; the JSON describes which. A timeout does not cancel the pending import.

To publish a model created through another Blender AI tool, save it with its asset meshes inside a collection named `Export`, then call `publish_blend`. The original file is opened with auto-execution disabled and is not overwritten.

For a self-contained textured example, use `--script examples/textured_cube.py` with a different asset ID. It creates its own UVs, checker texture and normal map, without downloads.

