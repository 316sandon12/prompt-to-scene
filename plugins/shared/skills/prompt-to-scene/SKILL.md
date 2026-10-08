---
name: prompt-to-scene
description: Create and refine styled Blender assets inside Unity or Unreal with Prompt-to-Scene. Use for game-aware modeling, native material import, reusable designs, room furnishing, gameplay hooks, asset organization and Play checks.
---

Use the supplied tools. The installed Codex and DeepSeek Harness plugins expose three entrypoints: `game_workflow`, `open_workbench`, `workbench_action`. They share sources, task state, project context and designs. The connected host supplies language understanding and vision; the local app has no separate chat model.

## One request to a usable game asset

1. Inspect the connected project using `game_workflow(operation="execute", action="context")`. If unconfigured, describe and execute `list_projects` / `connect_project` through the same gateway. Do not switch projects just because another editor is open. Blender must be installed; UE needs one restart after bridge installation.
2. Read `game_art_direction` and existing style. Save the user's world, gameplay and camera once, inferring reasonable choices from their words without requiring a form. Look for reusable project assets (`find_assets`) and saved designs (`find_designs`) where relevant.
3. For a themed asset, interpret silhouette, construction, material scale, wear and interaction points into concrete decisions. Prefer custom Blender geometry when the shape exceeds the nine recipe types. Recipes are for fitting simple props, not arbitrary concept art.
4. Describe `produce`, then submit up to twelve unique new asset IDs. Each item uses `method=custom` with a complete bpy `script`, `recipe` with kind/parameters, `source` with a local path, `template` with a saved design name, or `interactive` with a template kind. Detailed requests should use explicit custom scripts; do not silently default to a recipe. Include concrete design `decisions` and the intended `description`.
5. A single parent task runs preparation, import, optional interaction, optional furnishing and optional review. Poll `task` with the returned request ID (wait_seconds up to 30). Resume failed/interrupted parent jobs with `resume`; successful stages are reused. Never resubmit a queued placement or generation to read progress.
6. Inspect one actual native result at the relevant game distance. Correct specific faults within the two-repair limit. Only the exact imported/completed receipt proves processing success; appearance acceptance requires looking at images. Report what changed and any concrete limitation.

`game_workflow(operation="search", query="...")` discovers other actions. `describe` returns their contract, `execute` takes `values`. Legacy tools remain callable by their exact name through this gateway. Use the optional workbench for buttons, task cards and real previews. Embedded MCP App support depends on the host; ordinary tools and the local window work without it.

## Match the game's appearance

For existing style, use `describe_project_assets` to capture representative native assets, then `match_game_style` with those evidence IDs or the saved reference. Read the returned images before submitting analysis with its source token. Infer proportion, edge softness, construction, material finish, palette and detail density. Colors/roughness are estimates under the pictured light. Never infer hidden topology or license from a picture. When no images exist, proceed from the user's text with stated assumptions.

Use `review(view="game")` for the actual camera and lighting: Unity requires MainCamera; UE requires one CameraActor or one tagged `PTS.GameCamera`. Do not invent a game camera if none exists; use a studio view and label it clearly. `review_images` returns real before/after pixels, reference, named parts and an evidence token. Compare silhouette, interaction readability, scale of texture, construction and contact. `feedback` saves observations and optional reusable `preference`; `accepted=true` is a host/user judgment, never an automated beauty score. Changed images/revisions invalidate stale feedback.

Use `repair` for concrete named-part changes, then inspect refreshed images. At most two repairs per review. Preserve independent geometry/material locks and unaffected parts. For a fused mesh, use its actual parts; automatic semantic segmentation is not implemented. Inspect the existing source before revising custom geometry. Do not add polygons/noise as a substitute for intentional design.

## Keep good designs

`save_design` stores a versioned editable Blender source, recipe, named parts, design brief and provenance. `reuse_design` creates a new asset with recipe parameters or custom `part_changes`; it preserves protected parts. Set `family_style=true` only when adopting the design as the project's continuing family. It affects future briefs, not existing assets. An explicit new project style clears that family default.

`find_assets` first indexes the native library; poll and reuse its request ID with a query. Requirements can include style, uses, materials and max_triangles, plus desired size. Ranking uses names, saved visual descriptions and metadata; it is not image-embedding similarity. Read native evidence when judging a match. `reuse_asset` places the original reference. Retain verified source/license data and leave unknown licenses unknown.

## Materials and gameplay

Scripts create an `Export` collection containing static meshes, in Blender XYZ meters with Z up, and Principled BSDF materials. Preparation automatically bakes supported graphs, normalizes size, checks simplification error and creates requested LOD/collision. Transport supports opaque, emission, alpha-cutout and ordinary alpha-blended surfaces. Use material custom property `pts_surface` = `opaque` / `mask` / `blend`, `pts_alpha_cutoff`, `pts_two_sided`; emission strength is constant. Alpha image channels and supported procedural inputs are baked. Refraction, mixed shaders, volume, rigs/animation, HDRP and arbitrary Blueprint generation remain unsupported. Never silently discard an unsupported shader.

`interaction` configures door/chest/pickup/resource/switch. Resources accept `uses`, `event_id`, `label`, local `interaction_point` and optional `depleted_asset_id`; completion raises native events and changes the visual. Switch toggles state. Unity exposes TryInteract, onInteracted, onGameEvent and onDepleted; UE exposes TryInteract, OnInteracted, OnDepleted and GameEventId. Integrate these hooks with the user's inventory/quest code when requested; a label alone does not connect those systems. Door/chest require separate base/moving geometry. Optional aim-and-E is demo input.

## Furnish existing blockouts

`furnish` takes an existing generated `level_id`, imported prop IDs, optional room_index, approach and protected_zones. It measures the actual level and models, preserves walking checkpoints and approach space, then checks native clearance. Failed clearance undoes placement. Standalone furnishing duplicates props; `produce(furnish=...)` stages and moves its newly created props, avoiding stray duplicate originals. It decorates measured rooms, not arbitrary floor-plan inference or architectural wall replacement. Bounds/capsule samples do not prove NavMesh/controller traversal.

Use `play` only when the user's request covers running project code: it enters Unity Play / UE PIE, exercises interaction counts/range/state/depletion and returns to Edit mode. Read individual assertions and development.passed, not just completed status. Do not tell users to leave Play while that check owns the temporary session.

## Recovery and advanced operations

Preserve queued work when the editor is offline; opening the editor is the fix, not regeneration. Native import already in progress may finish despite cancellation. Exact source restores and scene undo have different scopes; neither is whole-project rollback. User scenes still need normal saving. Generated geometry/material properties are managed; root components, supported protected bindings and instance transforms survive updates.

Repair actionable model errors at most twice. Do not install unrelated dependencies or alter host approvals. Paid generation requires existing authorization for provider/count; a configured API key is not spending authorization. Remote vision/reference uploads also require authorization. Reuse saved remote task IDs and never recreate a paid task merely to poll it.

For organization, part replacements, protected updates, conventions/inbox, provider generation, variants or material adaptation, read [advanced workflows](references/advanced.md) only as needed. Gateway discovery provides exact current tool contracts. An explicit organization request authorizes applying its concrete plan within scope; do not add an unnecessary confirmation. Respect exclusions, skipped resource types and runtime string-path limitations.
