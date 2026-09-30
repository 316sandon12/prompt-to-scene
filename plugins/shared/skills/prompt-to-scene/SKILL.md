---
name: prompt-to-scene
description: Create, place and revise static Blender props in a connected Unity or Unreal project using Prompt-to-Scene tools. Use for natural-language asset creation, selected-object edits, engine previews and restoring generated revisions.
---

Use the Prompt-to-Scene tools supplied by this plugin. Both Codex and DeepSeek Harness connect to the same project records; do not depend on another client's chat history.

## Connect once

Inspect the target. If it is unconfigured, list projects and connect the project the user chose. A UE bridge installation requires an editor restart. A missing Blender executable is a setup problem; offer the setup app rather than asking the user to edit MCP configuration. If several projects are plausible, ask which one to connect. Do not switch targets merely because another editor is open.

## Create and revise

For a crate, table, chair or sign, prefer `create_prop`; it saves parameters for `revise_prop`. Let the user describe the object naturally. Choose and remember a stable lowercase asset ID; the user need not invent it. Omit position for visible, grounded placement. Explicit coordinates are target-engine meters: Unity Y-up; Unreal Z-up.

For another static shape, call `build_asset` with a complete Blender Python script: use an `Export` mesh collection, meters/Z-up, applied modifiers and opaque Principled BSDF materials. Supported textures are directly connected base color and tangent-space normal images. Reject unsupported requirements clearly; do not silently approximate an important appearance. Use `publish_blend` for a saved compatible model.

Before revising a custom asset, inspect its saved script/source and retain existing details. Every custom build runs a fresh Blender process. For a recipe change merge only requested parameters. Distinguish changes to a shared asset from edits to one scene instance.

## Selected instances

For “this object”, inspect the scene's actual selection. `edit_scene` defaults to selected managed instances. Move/rotate/scale/tint use native engine operations without rebuilding. Use `scope=asset` only when the user asks to change every loaded instance in the current scene. This scope does not search unloaded levels. Preserve returned `undo_id` for “undo that edit”. Revisions restore with `restore_asset`; these are different operations.

## Finish and recover

Build returns immediately with a request ID. Wait with `get_asset_status`, passing that ID, for at most 30 seconds per call. Repeat while building/queued and give brief progress updates during longer work. Report success only for the exact imported request. Editor actions use `get_task_status`; if an action remains queued, query it instead of submitting the same edit twice.

After a successful import, request a real engine preview when useful. If image input/display is unavailable, provide the native asset path and offer to focus it. A failed preview does not mean the import failed. Never manufacture a render as evidence.

An offline editor needs to be opened or leave Play mode; keep its queued job. Fix an actionable script/material error and retry the same asset at most twice within the user's requested scope. After two unsuccessful repairs, report the diagnostic and the remaining requirement. Do not repeatedly regenerate, install unrelated dependencies, alter host approval settings, or claim success from a stale receipt. Cancellation can stop Blender or queued work; a native import already executing may finish.

Source revisions and recipe parameters live with the project. `restore_asset` reimports a previous successful source while retaining instance transforms; `undo_scene_edit` restores a tool edit's transforms/material overrides. Neither is a whole-project rollback. Remind the user to save their scene normally when appropriate.
