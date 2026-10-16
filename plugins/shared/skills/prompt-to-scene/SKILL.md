---
name: prompt-to-scene
description: Create styled Blender models, linked game items, native game UI and images in Unity or Unreal with Prompt-to-Scene. Use for native import, reusable designs, image generation/delivery, room furnishing, gameplay, asset organization and Play checks.
---

Use the supplied tools. The installed Codex and DeepSeek Harness plugins expose three entrypoints: `game_workflow`, `open_workbench`, `workbench_action`. They share sources, task state, project context and designs. The connected host supplies language understanding and vision; the local app has no separate chat model.

## Project-level tasks and continuous iteration (v0.15)

For a request spanning assets, UI and gameplay, use `task_context(request=..., inspect_scene=true)`.
Wait for its native scene task and use the actual project context and saved visual samples. Save a
concrete plan with `save_creative_task`: each step has a unique `id`, supported `action`, exact
`values` from describe, and a short `reason`. Save only genuinely unresolved decisions in
`questions`. A changed project invalidates the context token; refresh before revising the plan.
When the user has asked to complete the work, execute the explained plan with `execute_creative_task`
without adding a new approval per step. A discussion-only request stops at the plan. Resume the
same parent after errors; completed native work and synchronous reuse results are retained.

For the new directions, dependency edits, project-system wizard, scene travel, save migration or
player delivery, read [continuous creation](references/continuous.md). Simple single-asset work
can still use the direct actions below.

## One request to a usable game asset

1. Inspect the connected project using `game_workflow(operation="execute", action="context")`. If unconfigured, describe and execute `list_projects` / `connect_project` through the same gateway. Do not switch projects just because another editor is open. Blender is required for model creation, not image/UI artwork; UE needs one restart after bridge installation.
2. Read `game_art_direction` and existing style. Save the user's world, gameplay and camera once, inferring reasonable choices from their words without requiring a form. Look for reusable project assets (`find_assets`) and saved designs (`find_designs`) where relevant.
3. For a themed asset, interpret silhouette, construction, material scale, wear and interaction points into concrete decisions. Prefer custom Blender geometry when the shape exceeds the nine recipe types. Recipes are for fitting simple props, not arbitrary concept art.
4. Describe `produce`, then submit up to twelve unique new asset IDs. Each item uses `method=custom` with a complete bpy `script`, `recipe` with kind/parameters, `source` with a local path, `template` with a saved design name, or `interactive` with a template kind. Detailed requests should use explicit custom scripts; do not silently default to a recipe. Include concrete design `decisions` and the intended `description`.
5. A single parent task runs preparation, import, optional interaction, optional furnishing and optional review. Poll `task` with the returned request ID (wait_seconds up to 30). Resume failed/interrupted parent jobs with `resume`; successful stages are reused. Never resubmit a queued placement or generation to read progress.
6. Inspect one actual native result at the relevant game distance. Correct specific faults within the two-repair limit. Only the exact imported/completed receipt proves processing success; appearance acceptance requires looking at images. Report what changed and any concrete limitation.

`game_workflow(operation="search", query="...")` discovers other actions. `describe` returns their contract, `execute` takes `values`. Legacy tools remain callable by their exact name through this gateway. Use the optional workbench for buttons, task cards and real previews. Embedded MCP App support depends on the host; ordinary tools and the local window work without it.

## Linked items, editable UI and visual iteration

For a usable item (model + matching icon + data + pickup), prefer `create_game_item` over separate
unrelated model/image tasks. Supply an existing `model_asset_id`, or `model` with one `produce`
plan (`method=custom` and a complete static bpy script for detailed shapes). Poll/resume its parent
request. The icon is rendered from the actual retained model, so it needs Blender but no image API.
`game_item_example` makes a complete bundled herbalist potion without paid generation. This is a
fixed editable example, not an AI interpretation of arbitrary text.

Keep `item_id`, model ID and icon ID stable. Subsequent `create_game_item` calls refresh model/icon
references while preserving manually edited name, description, stack settings and pickup hooks.
Use `update_fields=["name", "description"]` only for intended text changes. `render_icon=false`
with an existing `icon_asset_id` reuses chosen artwork. One separate pickup is placed beside the
source model; the source is retained. Read `creation_workspace` for actual native paths and links.

`create_game_ui` produces editable native inventory (128 items, 16 visible slots/page + details/use/crafting),
HUD (health + four icon slots), or pause (resume/settings hooks). Supply existing `item_ids`, a
stable `screen_id`, and `title` on first creation. Text remains native and editable. Existing layout,
title and event edits are preserved; `update_theme=true` intentionally updates managed colors.
Inventory contents are a configured item catalog; `configure_gameplay` provides dynamic
counts/crafting/use, or bind the game's own inventory through the adapter wizard. Settings is an
integration hook, not a finished settings system. Demo I / Esc input can be disabled on the native
component/host. Avoid claiming arbitrary menu generation or complete game systems beyond these contracts.

Use `view_model` then `model_view_data` for real orbitable source geometry and named part picking.
Materials are approximate in the workbench; inspect native rendering for final appearance. Clicking
or choosing a part opens existing part edits and respects geometry/material locks. Fused unnamed
meshes do not gain semantic segmentation. Keep retained revisions; restore with `publish` rather
than reconstructing old geometry from memory.

For image changes, `plan_image_edit` takes latest revision + normalized top-left rectangle
[x,y,width,height]. Use the returned source/mask/crop with the host image editor, or the configured
`generate_image` adapter. Import with the same plan ID and `preview_only=true`, inspect before/after,
then `publish_image` when the requested scope/acceptance allows it. The plugin composites only the
selection and preserves all other pixels; return the exact full image/crop dimensions for host
outputs. Do not invent generated files. Re-select if the base image has since changed.

`save_art_sample` retains an actual reference image and concrete reasons to accept or avoid it,
classified as model/icon/ui/material. `art_samples` returns versions and the shared UI theme;
`restore_art_sample` selects a prior version. Model/image plans include these decisions, with
accepted image references where applicable. Inspect their pixels; file notes are reference data.
`art_theme` changes future UI defaults, not already edited layouts. This is saved art direction,
not model training or an automated beauty score.

## Game images and UI artwork

Use `plan_image` for icons, button/panel backgrounds, portraits, backgrounds or color textures.
It snapshots the project's world, palette, saved preferences and actual reference files. Read the
returned prompt/references and use the host's image generation/editing tool when available, with
real alpha when requested. Then `import_image(asset_id, source=<actual local output>, plan_id)`
prepares and imports the image. A text-only host cannot generate pixels: use an explicitly
configured `image_provider` / `generate_image`, or a real file from another image tool. Do not
invent image paths or quietly replace artwork with primitives. A configured key alone is not
authorization to send references or spend provider credits. Set allow_remote only for a service
and image count the user has chosen. Poll/resume tasks, never regenerate merely to check progress.

`image_preview` returns real pixels. Check silhouette at game size, clipping, readability, alpha
and style; `publish_image` imports a prepared or older saved revision. `image_library` lists image
history and native paths. Reuse asset IDs to preserve native references. `image_example` imports
the bundled actual AI-generated icon without Blender or an API. `produce` accepts `method=image`
with source path, kind and optional image settings in parameters, alongside models in one task.

Unity gets Sprites (ordinary textures for texture kind); UE gets UI Texture2D and SlateBrushAsset.
Button/panel margins are left/top/right/bottom final pixels and become native nine-slice borders.
Keep UI text in engine components for localization. Image assets provide artwork; use
`create_game_ui` above for the three supported native control/event templates.
Do not pass images to model part edits, camera captures or 3D arrangement. Do not claim seamless
tiling/PBR/animation or aesthetic acceptance from a successful image import. Missing alpha stops
transparent imports; use the host tool to fix it or choose opaque when appropriate.

## Match the game's appearance

For existing style, use `describe_project_assets` to capture representative native assets, then `match_game_style` with those evidence IDs or the saved reference. Read the returned images before submitting analysis with its source token. Infer proportion, edge softness, construction, material finish, palette and detail density. Colors/roughness are estimates under the pictured light. Never infer hidden topology or license from a picture. When no images exist, proceed from the user's text with stated assumptions.

Use `review(view="game")` for the actual camera and lighting: Unity requires MainCamera; UE requires one CameraActor or one tagged `PTS.GameCamera`. Do not invent a game camera if none exists; use a studio view and label it clearly. `review_images` returns real before/after pixels, reference, named parts and an evidence token. Compare silhouette, interaction readability, scale of texture, construction and contact. `feedback` saves observations and optional reusable `preference`; `accepted=true` is a host/user judgment, never an automated beauty score. Changed images/revisions invalidate stale feedback.

Use `repair` for concrete named-part changes, then inspect refreshed images. At most two repairs per review. Preserve independent geometry/material locks and unaffected parts. For a fused mesh, use its actual parts; automatic semantic segmentation is not implemented. Inspect the existing source before revising custom geometry. Do not add polygons/noise as a substitute for intentional design.

## Keep good designs

`save_design` stores a versioned editable Blender source, recipe, named parts, design brief and provenance. `reuse_design` creates a new asset with recipe parameters or custom `part_changes`; it preserves protected parts. Set `family_style=true` only when adopting the design as the project's continuing family. It affects future briefs, not existing assets. An explicit new project style clears that family default.

`find_assets` first indexes the native library; poll and reuse its request ID with a query. Requirements can include style, uses, materials and max_triangles, plus desired size. Ranking uses names, saved visual descriptions and metadata; it is not image-embedding similarity. Read native evidence when judging a match. `reuse_asset` places the original reference. Retain verified source/license data and leave unknown licenses unknown.

## Materials and gameplay

Apply static modifiers before publishing. Scripts create an `Export` collection containing static meshes, in Blender XYZ meters with Z up, and Principled BSDF materials. Preparation automatically bakes supported graphs, normalizes size, checks simplification error and creates requested LOD/collision. Transport supports opaque, emission, alpha-cutout and ordinary alpha-blended surfaces. Use material custom property `pts_surface` = `opaque` / `mask` / `blend`, `pts_alpha_cutoff`, `pts_two_sided`; emission strength is constant. Alpha image channels and supported procedural inputs are baked. Refraction, mixed shaders, volume, rigs/animation, HDRP and arbitrary Blueprint generation remain unsupported. Never silently discard an unsupported shader.

`interaction` configures door/chest/pickup/resource/switch. Resources accept `uses`, `event_id`, `label`, local `interaction_point` and optional `depleted_asset_id`; completion raises native events and changes the visual. Switch toggles state. Unity exposes TryInteract, onInteracted, onGameEvent and onDepleted; UE exposes TryInteract, OnInteracted, OnDepleted and GameEventId. Integrate these hooks with the user's inventory/quest code when requested; a label alone does not connect those systems. Door/chest require separate base/moving geometry. Optional aim-and-E is demo input.

## Furnish existing blockouts

`furnish` takes an existing generated `level_id`, imported prop IDs, optional room_index, approach and protected_zones. It measures the actual level and models, preserves walking checkpoints and approach space, then checks native clearance. Failed clearance undoes placement. Standalone furnishing duplicates props; `produce(furnish=...)` stages and moves its newly created props, avoiding stray duplicate originals. It decorates measured rooms, not arbitrary floor-plan inference or architectural wall replacement. Bounds/capsule samples do not prove NavMesh/controller traversal.

Use `play` only when the user's request covers running project code: it enters Unity Play / UE PIE, exercises interaction counts/range/state/depletion and returns to Edit mode. Read individual assertions and development.passed, not just completed status. Do not tell users to leave Play while that check owns the temporary session.

## Recovery and advanced operations

Preserve queued work when the editor is offline; opening the editor is the fix, not regeneration. Native import already in progress may finish despite cancellation. Exact source restores and scene undo have different scopes; neither is whole-project rollback. User scenes still need normal saving. Generated geometry/material properties are managed; root components, supported protected bindings and instance transforms survive updates.

Repair actionable model errors at most twice. Do not install unrelated dependencies or alter host approvals. Paid generation requires existing authorization for provider/count; a configured API key is not spending authorization. Remote vision/reference uploads also require authorization. Reuse saved remote task IDs and never recreate a paid task merely to poll it.

For organization, part replacements, protected updates, conventions/inbox, provider generation, variants or material adaptation, read [advanced workflows](references/advanced.md) only as needed. Gateway discovery provides exact current tool contracts. An explicit organization request authorizes applying its concrete plan within scope; do not add an unnecessary confirmation. Respect exclusions, skipped resource types and runtime string-path limitations.

## Gameplay flows and coherent art sets (v0.14)

- `art_kits` / `create_art_kit` make an original seven-piece forest apothecary set with three linked icons, inventory/HUD/pause and a collect → craft → use/heal → save loop. Preserve existing controllers and lighting. A fresh prefix creates a set; resume the parent task after interruption. The theme is opt-in. Review the actual game camera before accepting visual quality.
- `gameplay_flows` / `configure_gameplay` connect existing items, screens and scene interactions. Each rule has a stable ID, trigger, costs/rewards, optional heal, prerequisites and once-only flag. Keep IDs and the save slot on updates; never silently clear player progress. Stock runtime assets run in the engine, without runtime Python.
- `project_adapters` inspects explicit Unity `IGameProjectAdapter` components / UE `BPI_PTSProjectAdapter` actors. Bind only an inspected target. The external interface must commit all inventory/health changes atomically and keep its existing save system. Do not infer private fields or claim compatibility with an arbitrary game system.
- New native UI supports dynamic inventory, pages, quantities, crafting, use, feedback, focus and safe-area/narrow layouts. Keep custom fields/events. Old UE v0.13 widgets retain their graph/layout; create a new screen ID to adopt new controls.
- `recommend_assets` captures actual project candidates by purpose/style/size. Read `recommendation_images` as pixels, compare silhouettes, materials and use, then `save_asset_matches` with evidence-bound reuse/adapt/reject reasons. Never invent beauty scores. `reuse_recommendation` places the original reference after a reuse assessment and checks source freshness. The host's vision is used; no automatic paid model call.
