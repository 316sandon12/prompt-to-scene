# Advanced workflows

In compact mode, invoke named legacy tools through `game_workflow`: describe the tool name, then execute it with `values`. All legacy actions remain available.

## Workbench and connection

`open_workbench` exposes an optional MCP App with task cards, selection and real previews. Hosts without MCP Apps still use every normal tool or the local app. Do not promise that Codex/Harness necessarily renders an embedded UI just because its tools work. The local app contains no separate chat model. Use the current client's understanding and vision.

## Organize existing project assets

For naming/classifying Assets or /Game, use `organize_project_assets`: `scan` (optionally a folder), poll its request, then `plan(scan_id=request_id)`. The plan lists exact old/new paths, categories, skipped reasons and collision numbering. Default rules group by type and add consistent prefixes; `group_by="source"` keeps relative source groups. `rename=false` only groups. Use `settings.overrides={old_path:meaningful_name}` for semantic names inferred from user context; the tool itself uses native types, filenames and texture roles, not image recognition.

Apply the saved `plan_id` and poll that request. An explicit request to organize authorizes doing so; do not add another approval step unless the user requested a preview or an unresolved choice would alter scope. Honor exclusions and naming conventions. Do not bypass skipped folders/types: runtime loading paths, generated revisions and script/config resources may depend on them. Arbitrary code/config string paths are not rewritten.

Inspect the saved plan after completion. `history` retrieves recent plans, `inspect` paginates rows, and `undo` restores native paths without deleting asset content. A stale preview or occupied destination stops before replacement. Failed/cancelled applies attempt to restore completed moves; inspect `organization_status` and errors. After an interrupted editor, use the saved plan's undo to recover; do not resubmit unrelated plans or claim an unfinished batch completed. UE keeps required redirectors. Asset files are saved; this is not whole-project or scene-content rollback.

## Connect and inherit the project's design

Inspect the target. If unconfigured, list projects and connect the user's chosen one. UE needs one editor restart after bridge installation. Missing Blender is a setup problem: offer the setup app. Do not switch projects merely because another editor is open.

Read `inspect_library` and `get_project_style`. Prefer the project's existing style. `set_project_style` changes defaults for future props; changing existing props requires `revise_prop(apply_project_style=true)`. Styles are concrete palettes, shape parameters, surface wear and quality budgets. A reference recipe can supply art direction. If the client can see a reference image, interpret its palette/proportions into explicit supported parameters; do not claim automatic image reconstruction. Reuse an existing engine material only through an appropriate explicit material binding; the bridge does not edit that shared material.

## Recognize and match the project's existing style

When asked to match style, use the saved reference image or capture 1–3 representative project
assets with `describe_project_assets`. Poll once per request as usual. Pass their evidence IDs
to `match_game_style`, or set `use_reference=true`. This tool returns the actual images and a
source token; inspect the images with your vision before writing any analysis. If the host
cannot see images, say so and use available text direction instead of inventing observations.
If the project has no established direction yet, use available project/reference images before
the first themed build. If no images exist, proceed from the user's text with stated assumptions;
do not block ordinary creation on an unnecessary reference-selection form.

Identify common proportions and silhouette, edge softness, construction, material finish,
palette and detail placement. Read colors as estimates and account for illumination; do not
copy highlights/shadows into every base color. Omit unidentified material roles. A screenshot
does not reveal hidden topology, exact physical roughness, or the game's full art bible.

Call `match_game_style` again with that token and concrete `analysis` using its returned schema.
It validates that the image evidence is unchanged, converts sRGB hex colors to linear material
values and saves reusable style defaults plus shape/material/detail notes. Low confidence
retains existing defaults; use clearer available references before continuing. The connected
host does the recognition; no extra model API, charge or mandatory approval is introduced.
Do not force the reference into Cozy/Heritage/Workshop names: inferred palette, numeric shape
parameters and free-form design notes are the actual direction. Existing material bindings are
still respected. New briefs snapshot this analysis; changing defaults does not restyle old assets.

## Design for this game's world and gameplay

Read `game_art_direction` before modeling. Save the user's gameplay, world, visual style and
view with that tool once; infer sensible structured choices from what they already told you.
Do not make them fill a form or repeatedly answer the same questions. `construction` chooses
handcrafted, salvaged or machined treatments for simple recipes; `set_project_style` still
controls the actual palette, surface wear and budget. Plain text is interpreted by **you**, the
connected AI host, not a hidden second model or a keyword classifier in the plugin.

For a detailed or themed asset, call `design_asset` with a stable ID, its description, role
(environment/interactable/hero), focal point and concrete `decisions`: silhouette, structure,
materials, story and avoid. Derive these decisions from the game: what players do with the
object, how close they get, how it was manufactured, and why particular wear or repairs exist.
Include functional thickness, supports, clearances and recognisable interaction points.
Keep primary forms readable, secondary construction purposeful, and small decoration sparse.
Do not add noise, trim everywhere or a higher triangle budget as a substitute for design.

The default modeling route is **custom Blender code**, following the brief's specific forms.
`build_asset` with the same ID snapshots the design and applies the shared preparation pipeline,
including supported procedural PBR baking. Use recipes only when the requested form truly fits;
pass `recipe_kind` explicitly when planning such an asset. Custom briefs reject accidental recipe
substitution. Recipe treatments add real joinery, framed panels, shaped crests, hardware and
grain aligned with each piece of timber. They are a limited vocabulary, not arbitrary concept art.

New plans use the latest game context; running builds and existing recipes keep their saved
brief. To redesign an existing recipe, save its new `design_asset` brief then use
`revise_prop(apply_design=true)`; protected geometry and materials still retain their snapshots.
For custom revisions, inspect the existing source and edit that design rather than replacing it
with a template. Planning alone does not change an imported asset or implement gameplay.

Inspect one relevant actual source render, judge silhouette/construction/materials against the
brief and reference, and correct concrete faults within the existing two-repair limit. Use the
native preview for the actual engine appearance when needed. Do not require approval rounds,
multiple candidates or repeated captures for routine creation. Never call a completed plan or
successful import a passed aesthetic review.

## Create, compare and publish

Use the nine parameterized recipes listed by `inspect_library` for fitting simple props. They retain semantic parts and automatically prepare UVs and bake the curated PBR surfaces. Choose and remember an asset ID; the user need not invent one. `create_prop_set` submits matching designs, while repeated instances belong to `arrange_props`. Partial batch results list already-submitted work: resume missing designs rather than resubmitting the whole batch.

`compose_scene` builds a curated reading corner, village market or workshop and arranges the actual imported assets, with surface placement and undo. A selected upright context object can supply position and horizontal yaw; explicit positions use engine axes. `mode="save"` stores a selected group as a named layout; `mode="place"` duplicates a saved layout inside this same project. Poll its single workflow ID. Legacy `create_style_kit` only builds a spaced row and remains available when no layout is wanted.

Use `create_variants` when the user wants alternatives or visual exploration. Two or three inexpensive drafts remain in the source workspace. Wait with `get_variants`; use `get_studio_preview` for actual studio/front/back views. The user's preferred candidate is published through `choose_variant`, which builds final textures. Routine requests can go directly through `create_prop`; do not add mandatory selection steps.

For other static shapes, author a complete Blender Python script with an `Export` mesh collection or publish a compatible saved `.blend`. Each custom build starts a fresh Blender process. Inspect saved source before revising it and retain the existing design.

## Bring in existing or externally generated models

Use `import_asset` with a local GLB/glTF, FBX or Blender path when another AI tool has produced a model. `search_assets` searches English Poly Haven tags; import a returned catalog ID and retain its CC0 attribution. Search and import do not call or bill an AI generation provider. Choose sources based on the user's requested look; downloading a model alone does not establish that it fits the scene.

Preparation handles static meshes and common Principled PBR with emission and alpha mask/blend graphs. It bakes the supported channels, projects source normals onto the reduced model, checks sampled bidirectional shape error, makes reduced LODs and configures native collision. A requested budget that cannot be met within the error threshold fails before engine import. Refractive glass, rigs, animation, mixed shaders and unsupported lobes need a compatible source; do not silently discard them. LODs with no safe reduction are skipped and reported. Neither sampled error nor the report is a guarantee of texture quality or aesthetic quality.

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

## Interactive assets, levels and real play checks

`create_interactive_prop` builds a door, chest, pickup, harvestable resource or switch with baked PBR, separate moving geometry and native interaction. Poll its workflow ID until completed. Unity gets an editable prefab and `Interaction.TryInteract(worldPosition)` in meters; UE gets a reusable child Blueprint with `TryInteract(WorldPosition)` in centimeters and `OnInteracted`. Optional demo input is aim and E. These are five templates, not general game-logic or arbitrary Blueprint generation. Use `configure_interaction` for a specific range/angle or existing separate base/moving meshes. Pivots and offsets use the target engine's local axes in meters; do not infer them from Blender coordinates without checking the import.

Recreating the same interactive ID keeps range/input/open-angle settings. `protect_asset` inspects or sets canonical material assignments and named root attachment points. Geometry inside generated Visual/mesh content remains managed. `review_asset_update` checks a retained candidate's material slots and Unity renderer names before publication; a missing protected binding blocks import. Resolve by explicit remapping/clearing, not by silently dropping the user's material. Native asset identity, instance transforms and supported root settings remain stable after a successful update.

`set_scene_look` applies warm_cartoon, cool_scifi, moonlit or neutral lighting, sky and color grading. First placement establishes a fixed presentation camera. Capture before and after preset changes with `mode="capture"`; `mode="restore"` restores the saved previous lighting. This changes the loaded scene and cannot guarantee a match across render pipelines. Inspect actual screenshots.

`build_level(mode="plan")` returns a read-only grid plan of room/corridor/stair modules. Build validates matching ports, graph connectivity, door dimensions and sampled native capsule clearance; a blocker causes the staged creation to be discarded. `mode="check"` rechecks the current generated level against surrounding geometry. This is a modular blockout, not NavMesh generation, arbitrary floor-plan inference or a controller traversal guarantee.

`run_playcheck` intentionally enters real Unity Play or UE PIE and returns to Edit mode. Poll that request; do not tell the user to leave Play during a running check. Read `development.passed` and individual assertions, not only `status="completed"`. It exercises range rejection, interaction count, opening/closing or pickup, level clearance, runtime errors, captures and real frame intervals. `get_preview(request_id)` returns the after screenshot; `view="before"` returns the initial image. Editor frame samples are machine-specific measurements, not target-platform FPS promises. Arbitrary project scripts execute when entering Play; run it only when the user's requested test covers this.

Before generating a duplicate, `search_project_assets` can index local models/prefabs/compatible Blueprints. Wait for its request then call it again with the same `request_id` and query to rank results. Search uses names, tags, bilingual keyword aliases and optional size, not visual embeddings. `reuse_project_asset(mode="preview")` captures a native thumbnail; `mode="place"` places the original asset reference. `tag_project_asset` stores notes, tags, declared source and license. Preserve verified provenance and leave unknown licenses unknown.

## Shared conventions and automatic intake

Read `project_conventions` when joining a project. Save the user's naming prefixes, folders,
triangle/texture budgets, LOD and collision choices there so Codex, Harness, native panels and
the local app agree. `suggest` uses an `organize_project_assets` scan to report existing prefix
frequencies; adopt only the chosen suggestions. Existing managed assets keep their paths.

`manage_asset_inbox` accepts `status`, `scan`, or `retry`. Only the configured source folder is
watched. Enable `intake.enabled` for files to be imported while an editor/app/host is running.
Files must settle first; unchanged revisions are skipped and updated sources keep their asset ID.
Poll the returned parent workflow until completed and inspect `import_result`. Failed imports
use inbox `retry`; originals remain in the inbox. Do not promise a background watcher after every
editor and app has closed.

## Visual descriptions and reference materials

For content recognition, call `describe_project_assets` on actual indexed native paths. Poll,
then call `get_asset_evidence` for each returned evidence ID and inspect the image. Save a concise
`save_asset_description` with object type, materials, style, likely uses and honest confidence.
Names alone are not visual proof. Use `corrected=true` only for a user correction; automated
reruns must retain those corrections. Search ranks these descriptions and tags by keywords,
not embeddings. Suggested names become explicit organization overrides with `settings.include`
restricted to the chosen assets; managed assets remain protected from relocation.

A separately configured vision endpoint is optional. `allow_remote=true` sends the selected
thumbnails and native metadata to it; use existing user authorization, and never invent it.
Keys belong in the OS credential store, never a project file.

Use `adapt_asset_materials` for reference color, roughness and texture scale. Target Unity prefabs
or UE static meshes; choose an existing material/model as reference. A preview creates independent
variants and actual renders without replacing target geometry or textures. Inspect both pictures
with `get_preview`, report skipped shader properties, then apply authorized selected row IDs.
`undo` restores original assignments. Changed materials/assignments require a fresh preview.
Reused texture maps can prevent scalar roughness adaptation; never claim unsupported properties
were applied. Native panels and the workshop expose the same workflow.

## Optional provider generation

Use `list_generation_providers` before `generate_model`. Meshy or the configured self-hosted adapter can supply textured GLB candidates from text or 1–4 PNG/JPEG references; Blender then prepares them through the same pipeline. Defaults create isolated previews. Compare them and use `publish_prepared` to publish the chosen candidate. Keep the workflow ID distinct from each candidate's build ID.

Text generation incorporates the saved game/asset brief within the existing prompt budget.
The complete user prompt is retained; `effective_prompt` and `shortened_context` disclose what
was sent and which context fields were compacted or omitted. Shorten the request explicitly
if essential context did not fit. A resumed job uses its original snapshot. Meshy's image-only
route does not receive this text; `context_application=reference_images_only` makes that limit
explicit. A saved local reference is not automatically uploaded to any generation provider.

Meshy consumes provider credits. Set `allow_paid=true` only when the user's authorization covers this provider/count; do not invent authorization or fixed pricing. If that is absent, continue with local recipes/scripts/files where suitable. A configured key is not authorization to spend. Credentials are entered through the local app, never requested as chat/tool arguments. Self-hosted APIs require the documented adapter contract, not an arbitrary inference URL.

Resume an interrupted multi-step task with `resume_workflow`. Saved provider IDs are reused for polling; do not call generation again to get status. An ambiguous submission outcome must be reconciled in the provider dashboard to avoid duplicate charges. Cancel stops local processing; an already submitted provider task may continue and be billed. Report generation quality as provider-dependent, not a guaranteed result of this plugin.

## Finish and recover

Builds return immediately. Wait through building/queued using the exact `request_id` and `wait_seconds` up to 30. Report import success only for that request. Two Blender slots per project limit batch resource usage. A client wait timeout does not stop the worker. An offline editor needs to open/leave Play mode for imports; preserve its queued task. A running play check owns the temporary Play session and exits it itself.

Repair actionable script/material errors at most twice within the user's scope. After two unsuccessful repairs report the diagnostic. Do not regenerate for an offline editor, install unrelated dependencies, alter host approval settings, or rely on an old receipt. Native import already executing may finish despite cancellation; check the final receipt.

Use source studio views to compare shape/materials under consistent light and native previews to assess the actual game scene. Reports check supported geometry/material/UV/budget constraints; they do not establish aesthetic quality. Human choices remain decisive.

For a native comparison, call `capture_review(stage="before")`, wait for completion, make the requested edit, then capture `stage="after"` with the same `review_id`, asset and view. `get_review` reads the existing captures and `get_preview(request_id=...)` returns their images. The camera frame is retained; project lighting remains the engine's own. Reusing a completed capture ID does not take another picture.

`restore_asset` reimports a previous successful source; `undo_scene_edit` restores a tool edit in its original loaded scene. Neither is whole-project rollback. Hand-made edits inside generated geometry are not retained. The user saves scenes normally.
