# Architecture and tool contract

```text
Setup app ── installs Codex plugin / Harness bundle + engine bridge
     │
     └── shared local connection registry
              │
AI client ── stdio MCP ── persistent worker job ── background Blender
              │                                     │
              │                              FBX + PBR + .blend
              │                                     │
              └── scene action queue ── target editor adapter
                                             │
                                   exact-request receipts + PNG
```

The setup page binds an ephemeral **127.0.0.1** port. It uses a random per-run token, exact Host/Origin checks and no CORS access. It is only a setup/dashboard surface; the AI clients use stdio. The portable core contains Python, the MCP server, export driver, both engine bridges and the shared skill. Installation copies the core to a versioned user directory so moving the downloaded app does not break registered plugins.

## Two adapters, one workflow

`clients.py` generates the native host metadata with concrete paths during installation:

- Codex: `.codex-plugin/plugin.json`, `.mcp.json`, shared skill and a local `.agents/plugins/marketplace.json`. The Codex CLI performs registration. This is a local plugin, not an official marketplace listing.
- Harness: an npm-compatible package with `dsh.bundle.patch` and a Cordis insertion for the official `@deepseek-ai/dsh-mcp-client`. It is installed into the chosen profile. Core agent instructions also travel in MCP initialization because Harness does not consume Codex skills directly.

`PTS_HOME` defaults to the user's `.prompt-to-scene` directory. It contains `connections.json`, generated plugins and versioned runtimes. Both hosts use that same registry. Model parameters, Blender source, task status and edit snapshots live with the project, so another host can continue work without chat-history transfer.

Explicit `PTS_PROJECT` / legacy `PTS_UNITY_PROJECT` settings override the active connection. `PTS_ENGINE` applies to that explicit configuration. `PTS_BLENDER` overrides the remembered executable. The normal setup path needs none of these variables.

## MCP tools

| Tools | Purpose |
| --- | --- |
| `list_projects`, `connect_project`, `inspect_target` | Discover, connect/install, and diagnose the chosen editor. |
| `create_prop`, `revise_prop`, `inspect_asset` | Build/revise supported recipes and read retained source/parameters/history. |
| `build_asset`, `publish_blend` | Run trusted custom bpy or publish a compatible saved source. |
| `get_asset_status`, `get_task_status`, `cancel_task` | Track exact requests, bounded waits and cooperative cancellation. |
| `inspect_scene`, `edit_scene`, `undo_scene_edit` | Read selection; transform/tint/focus native instances; restore a prior edit snapshot. |
| `restore_asset`, `get_preview` | Reimport a successful source revision or return an engine PNG. |

Asset builds return `building` immediately. A detached worker runs Blender, then publishes a schema 2 import envelope atomically. The editor owns import and native scene changes; it writes a receipt before removing the inbox request. Status progresses `building → queued → imported` or ends in `error`/`cancelled`. Always match `request_id`; an old success is not confirmation of a new build. `wait_seconds` is capped at 30 per MCP call and never cancels a task.

The separate schema 1 action queue supports selection, transforms, tint, focus, preview and undo. Action completion uses `completed`, not `imported`. Long previews may remain queued and must be queried using their original ID. Do not enqueue the same relative transform again merely because a wait timed out.

## Asset and instance identity

Import envelopes include hashes, a stable asset ID and an engine-specific coordinate contract. Coordinates are target-engine XYZ **meters**: Unity Y-up, UE Z-up. UE converts to centimeters. When position is omitted, the editor places near its scene camera and traces downward onto collision geometry, falling back to its zero-height plane. Existing instance transforms remain unchanged on regeneration.

Unity maps FBX to Standard/URP materials and updates a persistent prefab. The generated `Visual` subtree is replaced; root components survive. Native tool tints create instance material overrides and reapply them by original material identity after regeneration.

UE combines meshes into a persistent Static Mesh and uses tagged StaticMeshActors. Its material graph exposes `PTS_Color` so selected-instance edits can use MaterialInstanceConstants. UE 5.7 may switch import pipelines on repeated imports in a single session: the bridge temporarily disables the FBX Interchange switch around its synchronous import and restores the previous value in `finally`. This prevents unit/axis drift across repeated revisions. Material parameter edits are verified by reading the stored value because UE 5.7's vector-parameter setter returns false even after changing it.

Neither engine saves the user's scene/level automatically. Asset-scope edits cover managed instances in the current loaded scene/level, not unloaded content. General hand-made overrides inside the generated hierarchy are not preserved.

## History, cancellation and repair

Successful source versions live in `.prompt-to-scene/work/<asset>/<revision>/`. Receipts are archived under `history/`; restores publish a new revision from a previous immutable `.blend` while retaining its recipe/collider metadata. A restore is an ordinary import and can itself fail; it is not transaction rollback.

`edits/` stores transform and material snapshots with scene and object identity. Undo requires the original scene and objects. It restores the saved snapshot, so using an old undo ID after unrelated changes can overwrite those newer properties. Deleted sources/objects and changed topology limit restoration.

Per-asset submission/build locks reject concurrent replacement and pending imports. Cancellation stops Blender or causes the editor to skip a queued request. An executing native import may finish; check its final receipt. An offline editor confirms queued cancellation when it next processes the queue. An MCP/client wait timeout does not stop the worker.

The shared agent instructions request at most two repairs for actionable script/material errors. This is an orchestration policy for the host AI, not an additional autonomous model inside the server. Offline/Play/compilation/version problems should be resolved without regenerating the asset.

## Previews and boundaries

Unity renders the current managed objects through a temporary camera/light into a PNG and removes those temporary objects. UE captures its actual focused editor viewport asynchronously. These images show native engine assets, with that engine's lighting/color handling; they are not generated images or pixel-matched Blender renders. Working graphics and an editor viewport are required.

Supported materials and geometry are described in the [asset contract](asset-contract.md). Python is trusted local code, not a sandbox. Import errors can leave partially updated engine assets; backups, source history and edit snapshots do not provide whole-project rollback. Native operations stay on the editor thread.
