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

The setup page binds an ephemeral **127.0.0.1** port. It uses a random per-run token, exact Host/Origin checks and no CORS access. It provides setup and a local creation workshop; the AI clients use stdio. The portable core contains Python, the MCP server, retained Blender drivers, both engine bridges and the shared skill. Installation copies the core to a versioned user directory so moving the downloaded app does not break registered plugins.

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
| `inspect_library`, `get_project_style`, `set_project_style` | List nine recipes, concrete style/quality defaults, reference-style adoption and existing-material bindings. |
| `create_prop`, `create_prop_set`, `revise_prop`, `inspect_asset` | Build/revise recipes or matching sets; read retained source, parameters, reports and history. |
| `edit_prop_part` | Edit semantic geometry/material properties and independent locks. |
| `create_variants`, `get_variants`, `choose_variant`, `get_studio_preview` | Isolated 3D drafts, exact state, selected-candidate publication and Blender studio/front/back PNGs. |
| `build_asset`, `publish_blend` | Run trusted custom bpy or publish a compatible saved source. |
| `get_asset_status`, `get_task_status`, `cancel_task` | Track exact requests, bounded waits and cooperative cancellation. |
| `inspect_scene`, `edit_scene`, `arrange_props`, `undo_scene_edit` | Read selection and static context; transform/tint/focus or arrange native instances; restore a prior edit/layout snapshot. |
| `restore_asset`, `get_preview` | Reimport a successful source revision or return an engine PNG. |
| `search_assets`, `import_asset`, `publish_prepared`, `prepare_asset` | Credited Poly Haven search, common model intake, preview publication and reprocessing from retained originals. |
| `create_style_kit`, `edit_selected_prop` | Curated matching sets and selection-driven recipe edits. |
| `capture_review`, `get_review` | Persisted native before/after image pairs sharing one camera frame. |
| `open_workbench`, `workbench_action` | Optional MCP App and the shared local/embedded UI action routes. |
| `compose_scene`, `resume_workflow` | Furnished sets, saved layouts, and resuming durable multi-step jobs. |
| `edit_imported_part` | Group, lock, edit and replace existing mesh parts in imported models. |
| `set_art_brief`, `get_art_reference`, `review_quality`, `repair_quality` | Persistent art references, native diagnostics and bounded same-camera repair loops. |
| `inspect_performance`, `apply_usage_preset` | Real geometry/material/LOD measurements and explicit use-case preparation. |
| `list_generation_providers`, `generate_model` | Optional Meshy/self-hosted candidates through the normal preparation pipeline. |

There are 47 tools. Asset builds return `building` immediately. A detached worker runs Blender, then publishes a schema 2 import envelope atomically. The editor owns import and native scene changes; it writes a receipt before removing the inbox request. Status progresses `building → queued → imported` or ends in `error`/`cancelled`. Always match `request_id`; an old success is not confirmation of a new build. `wait_seconds` is capped at 30 per MCP call and never cancels a task.

The separate schema 1 action queue supports selection, transforms, tint, focus, contextual arrangement, preview and undo. Action completion uses `completed`, not `imported`. Long previews may remain queued and must be queried using their original ID. Do not enqueue the same relative transform again merely because a wait timed out.

## Art direction, materials and retained recipes

`art-direction.json` stores concrete defaults per project. New recipe assets inherit a snapshot; existing assets change only through an explicit revision. `styles.py` owns three curated palettes and four quality budgets. `design.py` produces deterministic semantic primitive plans for nine prop kinds, separate from their Blender realization. Recipe version 2 retains dimensions, part edits and frozen lock inputs. Geometry/material locks are independent; large neighboring changes can leave gaps. Revising older recipes adopts current structural designs; saved `.blend` revisions remain available.

`blender_recipe.py` creates the planned geometry. `blender_surfaces.py` prepares a common UV atlas and uses Cycles CPU baking for curated wood, metal, paint and stone: base color, roughness, metallic and tangent normal. Export validates direct image links, color spaces and manifest references. Unity packs metallic into R and smoothness into A; UE uses separate linear data maps and its normal convention. Existing material bindings are read-only references inside `Assets/` or `/Game/`. The external import path additionally bakes common opaque Principled PBR graphs; mixed shaders and unsupported lobes remain rejected.

Each work revision retains its Blender helper scripts alongside `model.py`, preserving the exact build implementation and avoiding references to a portable app's temporary extraction directory after its parent exits. Per-project slots cap Blender concurrency at two processes. A quality report includes geometry/material/UV/budget checks, per-part bounds and actual vertex geometry hashes. It does not score aesthetic quality.

## Draft studies and contextual layout

`studies/<id>.json` groups two or three drafts. Each uses a unique asset/request identity and `preview_only`: the worker exports source and views but never writes an engine inbox request. The chosen candidate is rebuilt with final project quality and published under the intended asset ID. Repeating the same successful choice returns the original task. Drafts are deterministic structural variants, not image-to-3D or unconstrained concept synthesis.

`inspect_scene` adds bounds for static context: Unity renderer objects and UE StaticMeshActors in the active scene/level. `layout.py` plans around/along/under/right/front positions in target-engine meters. It reuses eligible instances, clones extras, optionally faces the anchor and can uniformly shrink objects to fit below an anchor. Upright anchors can have arbitrary yaw. Native oriented bounds and projected SAT checks reject potential overlaps; known table/stool recipes supply clearance, with a conservative fallback for other objects.

Native adapters recheck the scene, source poses, anchor bounds and obstacles before mutation. Layout snapshots include original poses and newly created IDs; undo restores originals and removes those copies. If the initial scene read is queued, resume `arrange_props` with `inspection_request_id`. Once the layout itself is queued, poll that request ID; resubmitting can create another layout. Undo requires the original loaded scene and surviving objects.

## External source preparation

`sources.py` accepts local GLB/glTF/FBX/Blender files or a Poly Haven catalog ID. Catalog requests use a unique User-Agent, visible attribution and an hourly local cache. Worker downloads check HTTPS hosts (including redirects), dependency paths, sizes and provider checksums, then retain SHA-256 provenance. No paid generation provider is called. Local source hashes detect changes between submission and execution; the original file is never modified.

`blender_ingest.py` evaluates static meshes, applies transforms and splits material regions. `blender_prepare.py` retains a packed original before normalization, optionally sets the longest dimension and origin, and welds coincident seam vertices before decimation. Each reduction is checked with bidirectional vertex/face-centroid samples and newly introduced boundary edges. Thresholds are relative to each object's diagonal; this is not a formal Hausdorff guarantee. Rejected reductions restore the original geometry. A remaining budget failure publishes no engine envelope.

External opaque PBR channels are baked with retained UVs (UVs are generated only if absent). Paired high-to-low normal projection transfers source shading to the reduced surface. Simplified FBX levels use the same stable material identities. Levels without safe reduction are omitted with warnings. Unity creates an LODGroup; UE imports the levels into the existing Static Mesh and explicitly sets screen sizes. Changing to an empty LOD list removes the old chain. Collision can be none/box/convex. Unity cooks per-mesh convex colliders; UE attempts convex decomposition, uses a reported native 26-DOP fallback when necessary, and separately counts primitive shapes and convex hulls.

`prepare_asset` merges explicit settings with the last preparation and starts from `original.blend`, so increasing the budget can recover original detail. `publish_prepared` and source restore carry this original and provenance forward. Explicit preparation is allowed to reduce geometry independently of recipe locks. Source studio before/after views share framing and light; reports are geometry/compatibility checks, not automatic art judgments.

`reviews/<id>.json` retains native capture request IDs. The first capture saves an engine-owned frame in `preview-frames/`; the second validates scene/asset/view and reuses it. Retries query an existing completed stage rather than silently taking another screenshot. UE serializes asynchronous viewport captures and restores the previous viewport camera.

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

Blender creates studio/front/back views from the actual exported source with consistent lighting, stored beside each revision. These views support draft comparison and do not show the engine.

Unity renders the current managed objects through a temporary camera/light into a PNG and removes those temporary objects. UE captures its actual focused editor viewport asynchronously. These images show native engine assets, with that engine's lighting/color handling; they are not generated images or pixel-matched Blender renders. Working graphics and an editor viewport are required.

Supported materials and geometry are described in the [asset contract](asset-contract.md). Python is trusted local code, not a sandbox. Import errors can leave partially updated engine assets; backups, source history and edit snapshots do not provide whole-project rollback. Native operations stay on the editor thread.


## v0.6 workflows and optional UI

`open_workbench` attaches `ui://prompt-to-scene/workbench.html` with MCP Apps metadata and the `text/html;profile=mcp-app` MIME type. `workbench_action` routes buttons through the same validated functions as the normal tools. The HTML/JS is shared with the loopback `/workbench` page; the embedded page uses JSON-RPC postMessage and does not fetch the local HTTP server. It handles initialization, tool calls, selected-object model context and explicit user messages. No external script or image CDN is needed. Host UI support is optional.

New normal tools: `compose_scene`, `edit_imported_part`, `set_art_brief`, `get_art_reference`, `review_quality`, `repair_quality`, `inspect_performance`, `apply_usage_preset`, `list_generation_providers`, `generate_model`, `resume_workflow`.

`background.py` persists composition, quality and generation specifications and child IDs under the ordinary jobs directory. Resume uses saved stages. Composition waits for actual engine imports before a checked layout; templates reference current-project assets. Quality retains the original camera frame, limits repairs to two, rejects outside revisions and recaptures after each part repair. Native diagnostics return counts and measured support gaps, with possible overlaps explicitly marked for visual inspection.

Imported part edits retain the high-detail source. Unchanged objects keep their previous per-object reduction ratio; remaining budget is assigned to edited/replaced geometry. `cache/bakes` keys include Blender version, mesh geometry/normals/UVs, normal-source geometry, material graph input/output defaults and current image pixels. A conservative node allowlist excludes implicit object/view/attribute/animated dependencies and cross-material projection from cache reuse; these still bake normally. SHA-256 checks protect reuse; cache writes publish whole directories. Repeated geometry signatures also let both engine adapters skip FBX/LOD/collision recreation. Collision enablement, material slot/binding names and LOD parameters participate in that signature. Unchanged texture files avoid native reimport.

The art brief and copied references live in `art-brief.json` and `references/`. Source layout templates live in `layouts/`. Provider endpoints are user configuration, while keys are in OS credential stores or environment overrides. API credentials are never passed to model downloads. Remote job IDs are persisted before polling; an ambiguous POST outcome stops automatic retry. See [provider contract](PROVIDERS.md) and [usage](WORKBENCH.zh-CN.md).
