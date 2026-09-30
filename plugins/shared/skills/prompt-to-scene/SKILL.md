---
name: prompt-to-scene
description: Create styled Blender props or prepare external models for Unity and Unreal with Prompt-to-Scene. Use the workbench, optional generation providers, native quality/performance checks, external part edits, and furnished scene layouts.
---

Use the supplied Prompt-to-Scene tools. Codex and DeepSeek Harness share project records, recipes, source history and art direction; another client's chat history is not needed.

## Workbench and connection

`open_workbench` exposes an optional MCP App with task cards, selection and real previews. Hosts without MCP Apps still use every normal tool or the local app. Do not promise that Codex/Harness necessarily renders an embedded UI just because its tools work. The local app contains no separate chat model. Use the current client's understanding and vision.

## Connect and inherit the project's design

Inspect the target. If unconfigured, list projects and connect the user's chosen one. UE needs one editor restart after bridge installation. Missing Blender is a setup problem: offer the setup app. Do not switch projects merely because another editor is open.

Read `inspect_library` and `get_project_style`. Prefer the project's existing style. `set_project_style` changes defaults for future props; changing existing props requires `revise_prop(apply_project_style=true)`. Styles are concrete palettes, shape parameters, surface wear and quality budgets. A reference recipe can supply art direction. If the client can see a reference image, interpret its palette/proportions into explicit supported parameters; do not claim automatic image reconstruction. Reuse an existing engine material only through an appropriate explicit material binding; the bridge does not edit that shared material.

## Create, compare and publish

Prefer the nine parameterized recipes listed by `inspect_library`. They retain semantic parts and automatically prepare UVs and bake the curated opaque PBR surfaces. Choose and remember an asset ID; the user need not invent one. `create_prop_set` submits matching designs, while repeated instances belong to `arrange_props`. Partial batch results list already-submitted work: resume missing designs rather than resubmitting the whole batch.

`compose_scene` builds a curated reading corner, village market or workshop and arranges the actual imported assets, with surface placement and undo. A selected upright context object can supply position and horizontal yaw; explicit positions use engine axes. `mode="save"` stores a selected group as a named layout; `mode="place"` duplicates a saved layout inside this same project. Poll its single workflow ID. Legacy `create_style_kit` only builds a spaced row and remains available when no layout is wanted.

Use `create_variants` when the user wants alternatives or visual exploration. Two or three inexpensive drafts remain in the source workspace. Wait with `get_variants`; use `get_studio_preview` for actual studio/front/back views. The user's preferred candidate is published through `choose_variant`, which builds final textures. Routine requests can go directly through `create_prop`; do not add mandatory selection steps.

For other static shapes, author a complete Blender Python script with an `Export` mesh collection or publish a compatible saved `.blend`. Each custom build starts a fresh Blender process. Inspect saved source before revising it and retain the existing design.

## Bring in existing or externally generated models

Use `import_asset` with a local GLB/glTF, FBX or Blender path when another AI tool has produced a model. `search_assets` searches English Poly Haven tags; import a returned catalog ID and retain its CC0 attribution. Search and import do not call or bill an AI generation provider. Choose sources based on the user's requested look; downloading a model alone does not establish that it fits the scene.

Preparation handles static meshes and common opaque Principled PBR graphs. It bakes the supported channels, projects source normals onto the reduced model, checks sampled bidirectional shape error, makes reduced LODs and configures native collision. A requested budget that cannot be met within the error threshold fails before engine import. Glass, rigs, animation, mixed shaders and unsupported lobes need a compatible source; do not silently discard them. LODs with no safe reduction are skipped and reported. Neither sampled error nor the report is a guarantee of texture quality or aesthetic quality.

Use `target_size` for the largest dimension in meters when size is specified; default import honors the format's units and axes. `up_axis` applies an explicit correction after format conversion, so do not automatically set it to the target engine's up axis. `prepare_asset` reprocesses the retained original; omitted settings keep the current preparation settings. An explicit preparation may change geometry even when recipe parts are locked.

Routine requests can import directly. If a source review is requested, set `preview_only=true`, wait for `completed`, compare `get_studio_preview(view="before")` and `view="studio"`, then `publish_prepared` with that asset and request ID. Publication retains the original and provenance. Do not substitute a new build or claim that preview completion means the engine imported it.

## Revise only the intended properties

`revise_prop` changes shared recipe dimensions, style or quality. `edit_prop_part` changes a named part's scale, offset, rotation, color, material or wear. Inspect the recipe's available parts first. Geometry and material locks are independent; `part="all"` supports locking the complete design. Explicitly unlock a property before modifying it. Locked geometry retains its frozen construction inputs during later whole-asset revisions. Large changes around locked parts can create gaps: inspect the resulting views.

Semantic changes affect all instances of the asset. For “only this object”, inspect actual engine selection and use `edit_scene` for native transforms/tints. Part-edit coordinates are Blender XYZ meters with **Z up**; scene positions use target-engine axes: Unity Y up, UE Z up. Recipe scaling pivots at the bottom center; imported groups pivot around their bounds center. Do not confuse these coordinate spaces.

`edit_selected_prop` resolves the editor selection before editing a named part; it requires one unambiguous managed asset. If inspection is queued, resume with `inspection_request_id`. For imported models, inspect actual `report.parts`, source paths and locks. `edit_imported_part` groups existing parts via `members`, independently locks geometry/materials, or fits a local replacement model to one part. A fused mesh remains one part; do not claim automatic semantic segmentation. Unchanged base geometry retains its previous reduction ratio. If a replacement cannot meet its remaining budget, increase the budget explicitly or choose a lighter part. Unchanged maps may use a validated bake cache; matching geometry hashes let native adapters skip mesh/LOD/collision rebuilds. First-time slot changes still need normal import.

## Place assets in context

`inspect_scene` returns managed instances plus real static scene bounds and selected context objects. `arrange_props` accepts a selected or explicit anchor and asset/count groups. It supports around, along, under, right and front, conservative overlap checks, optional shrinking to fit under the anchor, and persistent undo of moved/created instances. Layouts support arbitrary horizontal anchor yaw, with native oriented bounds and conservative overlap checks. `face_anchor=true` can orient props toward the anchor, and `snap_to_surface=true` aligns to detected collision surfaces. Tilted anchors, arbitrary path following and exact concave-space collision are unsupported.

If inspection is still queued, continue with `inspection_request_id`. Once an arrangement request is queued, poll its original ID. Resubmitting it can create extra copies. Save its `undo_id`; `undo_scene_edit` restores original poses and removes instances created by that layout. Never label source studio renders as engine screenshots: use `get_preview` for the real in-scene result.

## Art references, quality and performance

`set_art_brief` saves a reference image and notes. `get_art_reference` returns the image to client vision. Adopt style parameters explicitly; saving an image does not automatically infer or reconstruct a style. `review_quality` creates same-camera before/after images and reads native missing-material, support-gap and potential-overlap findings. Optional `auto_fix` only grounds a measured gap no larger than 0.5m. Read both images with `get_preview` and compare to the saved reference; a technical pass is not an aesthetic pass.

When a concrete appearance issue can be fixed within the user's request, `repair_quality` edits a named part then automatically rechecks and refreshes the after image. At most two repairs per review, including auto-grounding. Wait for the same review workflow to complete, inspect fresh captures and stop at the limit. An outside asset revision invalidates the review. Never invent a beauty score or claim vision inspected an image without actually reading it.

`inspect_performance` returns real editor triangles, vertices, material slots, texture counts and LOD data. Resume queued checks with their request ID. `apply_usage_preset` prepares for mobile_prop, scene_prop or hero_prop. Texture sizes are RGBA8+mip estimates; draw calls, FPS and compressed VRAM require the engine profiler. Excess material slots are recommendations, not an automatic atlas fix.

## Optional provider generation

Use `list_generation_providers` before `generate_model`. Meshy or the configured self-hosted adapter can supply textured GLB candidates from text or 1–4 PNG/JPEG references; Blender then prepares them through the same pipeline. Defaults create isolated previews. Compare them and use `publish_prepared` to publish the chosen candidate. Keep the workflow ID distinct from each candidate's build ID.

Meshy consumes provider credits. Set `allow_paid=true` only when the user's authorization covers this provider/count; do not invent authorization or fixed pricing. If that is absent, continue with local recipes/scripts/files where suitable. A configured key is not authorization to spend. Credentials are entered through the local app, never requested as chat/tool arguments. Self-hosted APIs require the documented adapter contract, not an arbitrary inference URL.

Resume an interrupted multi-step task with `resume_workflow`. Saved provider IDs are reused for polling; do not call generation again to get status. An ambiguous submission outcome must be reconciled in the provider dashboard to avoid duplicate charges. Cancel stops local processing; an already submitted provider task may continue and be billed. Report generation quality as provider-dependent, not a guaranteed result of this plugin.

## Finish and recover

Builds return immediately. Wait through building/queued using the exact `request_id` and `wait_seconds` up to 30. Report import success only for that request. Two Blender slots per project limit batch resource usage. A client wait timeout does not stop the worker. An offline editor needs to open/leave Play mode; preserve its queued task.

Repair actionable script/material errors at most twice within the user's scope. After two unsuccessful repairs report the diagnostic. Do not regenerate for an offline editor, install unrelated dependencies, alter host approval settings, or rely on an old receipt. Native import already executing may finish despite cancellation; check the final receipt.

Use source studio views to compare shape/materials under consistent light and native previews to assess the actual game scene. Reports check supported geometry/material/UV/budget constraints; they do not establish aesthetic quality. Human choices remain decisive.

For a native comparison, call `capture_review(stage="before")`, wait for completion, make the requested edit, then capture `stage="after"` with the same `review_id`, asset and view. `get_review` reads the existing captures and `get_preview(request_id=...)` returns their images. The camera frame is retained; project lighting remains the engine's own. Reusing a completed capture ID does not take another picture.

`restore_asset` reimports a previous successful source; `undo_scene_edit` restores a tool edit in its original loaded scene. Neither is whole-project rollback. Hand-made edits inside generated geometry are not retained. The user saves scenes normally.
