---
name: prompt-to-scene
description: Create styled Blender props or prepare external models for Unity and Unreal with Prompt-to-Scene. Find CC0 assets, generate native LODs, compare real previews, edit selected recipe parts and arrange matching sets.
---

Use the supplied Prompt-to-Scene tools. Codex and DeepSeek Harness share project records, recipes, source history and art direction; another client's chat history is not needed.

## Connect and inherit the project's design

Inspect the target. If unconfigured, list projects and connect the user's chosen one. UE needs one editor restart after bridge installation. Missing Blender is a setup problem: offer the setup app. Do not switch projects merely because another editor is open.

Read `inspect_library` and `get_project_style`. Prefer the project's existing style. `set_project_style` changes defaults for future props; changing existing props requires `revise_prop(apply_project_style=true)`. Styles are concrete palettes, shape parameters, surface wear and quality budgets. A reference recipe can supply art direction. If the client can see a reference image, interpret its palette/proportions into explicit supported parameters; do not claim automatic image reconstruction. Reuse an existing engine material only through an appropriate explicit material binding; the bridge does not edit that shared material.

## Create, compare and publish

Prefer the nine parameterized recipes listed by `inspect_library`. They retain semantic parts and automatically prepare UVs and bake the curated opaque PBR surfaces. Choose and remember an asset ID; the user need not invent one. `create_prop_set` submits matching designs, while repeated instances belong to `arrange_props`. Partial batch results list already-submitted work: resume missing designs rather than resubmitting the whole batch.

`create_style_kit` makes a curated reading corner, village market or workshop set with its own matching style. It does not change project defaults. The items initially appear in a spaced row; use contextual placement for the final arrangement. Inspect the library for the kit's actual objects rather than promising a furnished scene.

Use `create_variants` when the user wants alternatives or visual exploration. Two or three inexpensive drafts remain in the source workspace. Wait with `get_variants`; use `get_studio_preview` for actual studio/front/back views. The user's preferred candidate is published through `choose_variant`, which builds final textures. Routine requests can go directly through `create_prop`; do not add mandatory selection steps.

For other static shapes, author a complete Blender Python script with an `Export` mesh collection or publish a compatible saved `.blend`. Each custom build starts a fresh Blender process. Inspect saved source before revising it and retain the existing design.

## Bring in existing or externally generated models

Use `import_asset` with a local GLB/glTF, FBX or Blender path when another AI tool has produced a model. `search_assets` searches English Poly Haven tags; import a returned catalog ID and retain its CC0 attribution. Search and import do not call or bill an AI generation provider. Choose sources based on the user's requested look; downloading a model alone does not establish that it fits the scene.

Preparation handles static meshes and common opaque Principled PBR graphs. It bakes the supported channels, projects source normals onto the reduced model, checks sampled bidirectional shape error, makes reduced LODs and configures native collision. A requested budget that cannot be met within the error threshold fails before engine import. Glass, rigs, animation, mixed shaders and unsupported lobes need a compatible source; do not silently discard them. LODs with no safe reduction are skipped and reported. Neither sampled error nor the report is a guarantee of texture quality or aesthetic quality.

Use `target_size` for the largest dimension in meters when size is specified; default import honors the format's units and axes. `up_axis` applies an explicit correction after format conversion, so do not automatically set it to the target engine's up axis. `prepare_asset` reprocesses the retained original; omitted settings keep the current preparation settings. An explicit preparation may change geometry even when recipe parts are locked.

Routine requests can import directly. If a source review is requested, set `preview_only=true`, wait for `completed`, compare `get_studio_preview(view="before")` and `view="studio"`, then `publish_prepared` with that asset and request ID. Publication retains the original and provenance. Do not substitute a new build or claim that preview completion means the engine imported it.

## Revise only the intended properties

`revise_prop` changes shared recipe dimensions, style or quality. `edit_prop_part` changes a named part's scale, offset, rotation, color, material or wear. Inspect the recipe's available parts first. Geometry and material locks are independent; `part="all"` supports locking the complete design. Explicitly unlock a property before modifying it. Locked geometry retains its frozen construction inputs during later whole-asset revisions. Large changes around locked parts can create gaps: inspect the resulting views.

Semantic changes affect all instances of the asset. For “only this object”, inspect actual engine selection and use `edit_scene` for native transforms/tints. Part-edit coordinates are Blender XYZ meters with **Z up**; scene positions use target-engine axes: Unity Y up, UE Z up. Part scaling pivots at the bottom center. Do not confuse these coordinate spaces.

`edit_selected_prop` resolves the editor selection before editing a recipe part; it requires one unambiguous managed asset. If inspection is queued, resume with `inspection_request_id`. External models have no procedural recipe parts: use native instance edits or revise their source.

## Place assets in context

`inspect_scene` returns managed instances plus real static scene bounds and selected context objects. `arrange_props` accepts a selected or explicit anchor and asset/count groups. It supports around, along, under, right and front, conservative overlap checks, optional shrinking to fit under the anchor, and persistent undo of moved/created instances. Layouts use world-axis bounds and preserve instance orientation. Use an axis-aligned anchor; do not promise arbitrary wall/path following or exact concave-space collision detection.

If inspection is still queued, continue with `inspection_request_id`. Once an arrangement request is queued, poll its original ID. Resubmitting it can create extra copies. Save its `undo_id`; `undo_scene_edit` restores original poses and removes instances created by that layout. Never label source studio renders as engine screenshots: use `get_preview` for the real in-scene result.

## Finish and recover

Builds return immediately. Wait through building/queued using the exact `request_id` and `wait_seconds` up to 30. Report import success only for that request. Two Blender slots per project limit batch resource usage. A client wait timeout does not stop the worker. An offline editor needs to open/leave Play mode; preserve its queued task.

Repair actionable script/material errors at most twice within the user's scope. After two unsuccessful repairs report the diagnostic. Do not regenerate for an offline editor, install unrelated dependencies, alter host approval settings, or rely on an old receipt. Native import already executing may finish despite cancellation; check the final receipt.

Use source studio views to compare shape/materials under consistent light and native previews to assess the actual game scene. Reports check supported geometry/material/UV/budget constraints; they do not establish aesthetic quality. Human choices remain decisive.

For a native comparison, call `capture_review(stage="before")`, wait for completion, make the requested edit, then capture `stage="after"` with the same `review_id`, asset and view. `get_review` reads the existing captures and `get_preview(request_id=...)` returns their images. The camera frame is retained; project lighting remains the engine's own. Reusing a completed capture ID does not take another picture.

`restore_asset` reimports a previous successful source; `undo_scene_edit` restores a tool edit in its original loaded scene. Neither is whole-project rollback. Hand-made edits inside generated geometry are not retained. The user saves scenes normally.
