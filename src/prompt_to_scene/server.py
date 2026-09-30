"""MCP tools; the user's existing AI client supplies natural-language understanding."""

import asyncio
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from . import (
    authoring,
    background,
    compositions,
    core,
    generation,
    kits,
    layout,
    parts,
    performance,
    quality,
    recipes,
    registry,
    reviews,
    sources,
    studies,
    styles,
    workbench,
    workflow,
)
from .core import inspect_project, wait_for_status

mcp = FastMCP(
    "Prompt-to-Scene",
    instructions="""
Create static opaque PBR assets in Blender, then publish to the configured Unity or Unreal project.
open_workbench offers an optional MCP App; normal tools work without an embedded UI.
Use compose_scene to build and furnish a kit, or save/place a reusable layout, with arbitrary yaw.
Use edit_imported_part for grouping, locks and local replacements on existing source meshes.
Use set_art_brief/get_art_reference for saved references. review_quality measures native issues
and captures before/after. Inspect the images with client vision, apply concrete repair_quality
changes at most twice, and inspect the refreshed images. No aesthetic pass is inferred.
inspect_performance reads native counts; apply_usage_preset prepares for a target use case.
Optional generate_model calls a configured Meshy or self-hosted service. Paid Meshy calls need
user authorization for provider/count. Default candidates are isolated until publish_prepared.
resume_workflow continues saved multi-step jobs; never resubmit paid tasks just to poll.
If no project is connected, use list_projects then connect_project with the user's chosen project.
Use inspect_library for nine designed recipes, semantic parts, styles and quality budgets.
Use search_assets to find credited CC0 Poly Haven models, or import_asset for a local GLB/glTF,
FBX or Blender model produced by another AI tool. Import automatically prepares static opaque PBR,
measured simplification, native LODs and collision. Use preview_only then publish_prepared when
the user wants to review first. Check the preparation report and before/studio views: sampled
shape error is not an aesthetic guarantee. prepare_asset reprocesses the retained original.
Use create_style_kit for coherent curated sets. edit_selected_prop resolves the editor selection
before changing a recipe; do not guess which asset the user means. capture_review before/after
reuses an engine camera frame so the user can compare actual engine results.
New props inherit get_project_style. set_project_style remembers concrete art direction; reference
images can inform palette/shape through the client's own vision, not hidden image-to-3D claims.
Prefer create_prop/create_prop_set with saved style. edit_prop_part edits or locks named parts;
revise_prop preserves frozen parts. Use create_variants only for requested design exploration,
get_studio_preview for source views, choose_variant for final textured import. Drafts do not
enter the engine scene. Native get_preview remains the authority for in-game appearance.
Arrange_props reads actual anchor/obstacle bounds and can duplicate props, shrink to fit and undo.
Do not retry a queued arrangement; poll its ID to avoid extra copies. For other shapes author bpy.
Build returns immediately: wait through building/queued until the exact request is imported.
Use inspect_scene to resolve 'this object'. edit_scene edits selected instances directly; use
asset scope only for all loaded instances. revise_prop changes persistent shared recipe parameters.
Before custom revisions inspect_asset and preserve its existing design. Use get_preview for a real
engine PNG. restore_asset restores an earlier source; undo_scene_edit restores instance edits.
Repair script errors at most twice. An offline editor needs opening, not repeated regeneration.
Inspect the target first. Blender scripts must create an Export collection containing meshes,
use meters, +Z up, applied modifiers, Principled BSDF materials. Python runs with local user
permissions. Read tool errors and fix the asset. Build returns building: always poll
get_asset_status with the returned request_id (wait_seconds up to 30). Only report success when
the request matches and status is imported. Position is target-engine XYZ in meters: Unity Y-up,
Unreal Z-up (converted to centimeters by the adapter). Reuse asset_id for revisions.
Existing scene instance transforms are preserved. Unity retains prefab root components; Unreal
retains its StaticMeshActor. Generated geometry and managed material properties are replaced.
This is not an image-to-3D model. Author bpy Python or publish a saved .blend from another tool.
""",
)


def project():
    target = registry.resolve()
    return {"project": target.project_file or target.root, "engine": target.engine}


@mcp.tool()
def inspect_target() -> dict:
    """Inspect engine, coordinates, Blender, editor heartbeat and pending/completed assets."""
    return inspect_project(**project())


@mcp.tool()
async def build_asset(
    asset_id: str,
    blender_python: str,
    position: list[float] | None = None,
    collider: bool = True,
) -> dict:
    """Execute trusted bpy code in background Blender; save .blend and queue engine import.

    Use stable asset_id (lowercase letters/digits/_/-) to update the same asset. Position is
    engine XYZ meters, applied ONLY when first placing the asset. Each script builds a complete
    asset from scratch. Delete default scene objects, create an Export collection, link meshes
    to it. Static meshes, constant opaque PBR, direct base-color / tangent normal textures.
    Unsupported materials fail explicitly. No paid model API or additional Blender MCP required.
    """
    return workflow.submit(str(project()["project"]), asset_id, blender_python, position, collider)


@mcp.tool()
async def publish_blend(
    asset_id: str,
    blend_file: str,
    position: list[float] | None = None,
    collider: bool = True,
) -> dict:
    """Publish the Export collection of an existing saved .blend without modifying the original.

    Use this after another Blender tool has modeled and saved an asset. Same material contract
    and queued/result semantics as build_asset. Blender file auto-execution is disabled.
    Use publish_prepared for a reviewed import_asset preview to retain preparation/provenance.
    """
    return workflow.submit(str(project()["project"]), asset_id, "", position, collider, blend_file)


@mcp.tool()
async def get_asset_status(
    asset_id: str, request_id: str | None = None, wait_seconds: float = 0
) -> dict:
    """Read an engine receipt, optionally wait up to 30s for a specific build request.

    Pass the build's request_id to prevent stale success. A wait timeout remains queued/unknown;
    superseded means another revision is current. Imported includes paths, geometry and scene.
    """
    core.asset_id(asset_id)
    if wait_seconds and not request_id:
        raise ValueError("Pass request_id when waiting")
    root = core.state_root(registry.resolve().root)
    if not request_id:
        last = core.read_optional_json(root / "latest" / (asset_id + ".json"))
        if last:
            request_id = last["request_id"]
    if request_id:
        workflow.identifier(request_id)
        state = core.read_optional_json(root / "jobs" / request_id / "state.json")
        if state:
            if state["asset_id"] != asset_id:
                raise ValueError("This request belongs to another asset")
            return await asyncio.to_thread(
                workflow.job_status, str(project()["project"]), request_id, wait_seconds
            )
    return await asyncio.to_thread(
        wait_for_status,
        **project(),
        name=asset_id,
        request_id=request_id,
        wait_seconds=wait_seconds,
    )


@mcp.tool()
def list_projects() -> dict:
    """Discover saved/local projects, Blender and recipe defaults without a connection."""
    return {
        "projects": registry.discover(),
        "active": registry.read().get("active"),
        "blender": registry.find_blender(),
        "recipes": recipes.DEFAULTS,
    }


@mcp.tool()
def connect_project(
    project_path: str, blender_path: str | None = None, install_bridge: bool = True
) -> dict:
    """Connect the chosen project for both clients and install its bridge with a backup.

    Unity takes a project folder; UE takes a folder or .uproject. Restart UE after installation.
    """
    return registry.connect(project_path, blender_path, install_bridge)


@mcp.tool()
def create_prop(
    kind: str,
    asset_id: str,
    parameters: dict | None = None,
    position: list[float] | None = None,
    collider: bool = True,
    quality: str | None = None,
) -> dict:
    """Create an art-directed prop using the saved project style and automatic PBR baking.

    inspect_library lists nine recipes, parameters, parts and quality settings. Omit quality
    to inherit the project. New assets are placed near the camera; revisions keep transforms.
    """
    return authoring.create(
        str(project()["project"]), kind, asset_id, parameters, position, collider, quality
    )


@mcp.tool()
def inspect_asset(asset_id: str) -> dict:
    """Read source script, recipe parameters and successful revisions before editing."""
    return workflow.inspect_asset(str(project()["project"]), asset_id)


@mcp.tool()
def revise_prop(
    asset_id: str,
    parameters: dict | None = None,
    apply_project_style: bool = False,
    quality: str | None = None,
) -> dict:
    """Change shared recipe dimensions or apply the current project style; preserve locked parts.

    This changes every instance using this asset. For one instance use edit_scene instead.
    """
    return authoring.revise(
        str(project()["project"]), asset_id, parameters, apply_project_style, quality
    )


@mcp.tool()
def inspect_library() -> dict:
    """List curated styles, quality budgets, recipe parameters and semantic part names."""
    return authoring.catalog(str(project()["project"]))


@mcp.tool()
async def search_assets(query: str = "", limit: int = 12, offset: int = 0) -> dict:
    """Search CC0 Poly Haven models by English tags; returns credited sources and thumbnails.

    Uses a cached catalog, no API key. Choose a result and import_asset with
    source={provider: polyhaven, id: returned_id}. Search never downloads model files.
    """
    return await asyncio.to_thread(sources.search, query, limit, offset)


@mcp.tool()
def import_asset(
    asset_id: str,
    source: dict,
    settings: dict | None = None,
    position: list[float] | None = None,
    preview_only: bool = False,
) -> dict:
    """Prepare and import local GLB/glTF/FBX/BLEND or a selected Poly Haven model.

    source={provider: local, path: absolute_file} or {provider: polyhaven, id: catalog_id}.
    settings: triangle_budget, texture_size (256/512/1024/2048), max_deviation_percent,
    lod_ratios (decreasing list), collision (convex/box/none), target_size (largest dimension
    in meters), unit_scale, up_axis (auto or +/-X/Y/Z), ground. File importers honor format
    axes; up_axis is an explicit correction AFTER that conversion. Original file is unchanged.
    Common opaque Principled PBR graphs and glTF ORM inputs are baked; rigs/transparency/mixed
    shaders fail explicitly. preview_only makes an isolated prepared draft; use its source
    with publish_prepared when accepted. Poll the exact request, inspect report and before/studio
    views. Poly Haven downloads retain CC0 provenance. No generation service is billed.
    """
    return sources.submit(
        str(project()["project"]), asset_id, source, settings, position, preview_only
    )


@mcp.tool()
def publish_prepared(asset_id: str, request_id: str) -> dict:
    """Send an accepted isolated import_asset preview to the engine, retaining its original.

    Pass the completed preview's asset_id and request_id. Materials, LOD settings and source
    attribution survive publication; the retained original remains available for reprocessing.
    """
    return sources.publish(str(project()["project"]), asset_id, request_id)


@mcp.tool()
def prepare_asset(asset_id: str, settings: dict | None = None) -> dict:
    """Reprocess an imported asset from retained source with measured simplification and LODs.

    Uses import_asset settings. A failed error/budget check queues nothing. Existing engine
    identities/instances survive successful reimport. Geometry locks apply to recipe edits;
    explicit preparation may reduce geometry. Review source before/studio and engine captures.
    """
    return authoring.optimize(str(project()["project"]), asset_id, settings)


@mcp.tool()
def create_style_kit(kit: str, prefix: str, quality: str | None = None) -> dict:
    """Create a curated reading_corner, village_market or makers_workshop set.

    Each uses matching art direction and purpose-designed structures, placed in a spaced row.
    A new prefix is required. Does not change project-wide defaults. Poll each task to imported.
    """
    return kits.create(str(project()["project"]), kit, prefix, quality)


@mcp.tool()
async def edit_selected_prop(
    part: str,
    changes: dict | None = None,
    lock_geometry: bool | None = None,
    lock_material: bool | None = None,
    inspection_request_id: str | None = None,
) -> dict:
    """Resolve the engine selection and edit a named recipe part without typing an asset ID.

    Changes the selected asset's shared recipe (all its instances). Requires exactly one
    selected managed asset. If inspection is queued, resume with inspection_request_id.
    Imported static models also support named-part geometry/material edits and locks.
    """
    task = (
        await get_task_status(inspection_request_id, 10)
        if inspection_request_id
        else await inspect_scene()
    )
    if task.get("status") != "completed":
        return {**task, "inspection_request_id": task["request_id"]}
    selected = {obj["asset_id"] for obj in task.get("selected", []) if obj.get("asset_id")}
    if len(selected) != 1:
        raise ValueError("Select exactly one managed asset in the engine")
    return authoring.edit_part(
        str(project()["project"]), selected.pop(), part, changes, lock_geometry, lock_material
    )


@mcp.tool()
def capture_review(
    asset_id: str, review_id: str | None = None, stage: str = "before", view: str = "studio"
) -> dict:
    """Capture a native before/after comparison with identical saved camera framing.

    Capture before, wait for completion, modify asset, then capture after with the same
    review_id and view. get_review lists capture tasks; get_preview(request_id) returns images.
    Engine project lighting remains visible; Blender source previews use the studio rig.
    """
    return reviews.capture(str(project()["project"]), asset_id, review_id, stage, view)


@mcp.tool()
def get_review(review_id: str) -> dict:
    """Return before/after native capture task states without creating another capture."""
    return reviews.read(str(project()["project"]), review_id)


@mcp.tool()
def get_project_style() -> dict:
    """Read persistent art direction shared by Codex, Harness, new props and prop sets."""
    return styles.read(str(project()["project"]))


@mcp.tool()
def set_project_style(
    preset: str | None = None,
    quality: str | None = None,
    overrides: dict | None = None,
    reference_asset: str | None = None,
) -> dict:
    """Remember art direction for future assets; existing assets change only on explicit revision.

    Presets: cozy, heritage, workshop. Quality: draft/mobile/desktop/hero. Overrides:
    palette (wood/metal/paint/stone linear RGB), roundness/taper/wear 0..1, material_bindings
    (role -> existing Assets/ or /Game/ material path). Reused materials remain untouched.
    reference_asset adopts an existing recipe's style. Use client vision for reference images,
    then propose concrete palette/shape values; this tool does not reconstruct images.
    """
    return authoring.set_style(
        str(project()["project"]), preset, quality, overrides, reference_asset
    )


@mcp.tool()
def edit_prop_part(
    asset_id: str,
    part: str,
    changes: dict | None = None,
    lock_geometry: bool | None = None,
    lock_material: bool | None = None,
) -> dict:
    """Edit or lock one named part of a recipe or imported model; inspect_asset lists parts.

    Changes: scale XYZ factors, offset XYZ meters, rotation XYZ degrees, color linear RGB,
    material wood/metal/paint/stone, roughness and wear. Part coordinates are Blender Z-up.
    Recipe transforms pivot at the bottom center; imported parts use their bounds center.
    Locks retain their saved
    geometry/material on later changes; explicitly unlock before changing locked properties.
    """
    return authoring.edit_part(
        str(project()["project"]), asset_id, part, changes, lock_geometry, lock_material
    )


@mcp.tool()
def create_prop_set(items: list[dict]) -> dict:
    """Create up to eight matching designs with one saved style. Each needs kind and asset_id.

    Optional fields: parameters, position, collider. Poll every returned task; after all imports
    use arrange_props for copies/placement. Partial submission reports already-started tasks.
    """
    return authoring.create_set(str(project()["project"]), items)


@mcp.tool()
def create_variants(
    kind: str, asset_id: str, parameters: dict | None = None, count: int = 3
) -> dict:
    """Generate two or three real 3D drafts with identical studio lighting and three views.

    Drafts stay outside the engine assets/scenes. Use only when exploring alternatives is useful;
    normal create_prop publishes directly. Wait with get_variants, view get_studio_preview,
    and publish the user's chosen candidate with choose_variant.
    """
    return studies.create(str(project()["project"]), kind, asset_id, parameters, count)


@mcp.tool()
def get_variants(study_id: str) -> dict:
    """Read each candidate's exact status, report and preview views; no aesthetic score."""
    return studies.read(str(project()["project"]), study_id)


@mcp.tool()
def choose_variant(
    study_id: str, index: int, quality: str | None = None, position: list[float] | None = None
) -> dict:
    """Publish the selected draft at final quality with automatic textures and engine import."""
    return studies.choose(str(project()["project"]), study_id, index, quality, position)


@mcp.tool()
def get_studio_preview(asset_id: str, request_id: str, view: str = "studio"):
    """Return an actual Blender source render (studio/front/back), including isolated drafts.

    Clearly label as Blender studio, not an engine screenshot. get_preview shows the game scene.
    """
    path = studies.preview_path(str(project()["project"]), asset_id, request_id, view)
    return Image(data=path.read_bytes(), format="png")


@mcp.tool()
async def arrange_props(
    items: list[dict],
    relation: str = "around",
    anchor_id: str | None = None,
    gap: float = 0.12,
    fit: bool = False,
    inspection_request_id: str | None = None,
    face_anchor: bool = False,
    snap_to_surface: bool = True,
) -> dict:
    """Place managed props relative to a selected real scene anchor, with collision checks/undo.

    items: [{asset_id, count=1, object_id?}], up to 32 instances. Relations: around, along,
    under, right, front. fit can shrink under-anchor props. Uses oriented bounds for upright
    objects and any horizontal anchor yaw. Existing instances move, extra ones are duplicated.
    If inspection is queued, retry with inspection_request_id. If arrangement is queued,
    poll its exact request with get_task_status; do not submit the layout again.
    """
    target = str(project()["project"])
    if inspection_request_id is None:
        task = workflow.action(target, "inspect")
        inspection_request_id = task["request_id"]
    scene = await get_task_status(inspection_request_id, 10)
    if scene["status"] != "completed":
        return {**scene, "inspection_request_id": inspection_request_id}
    clearance = None
    selected = scene.get("selected_context", [])
    anchor = (
        next((o for o in scene.get("context", []) + selected if o["id"] == anchor_id), None)
        if anchor_id
        else (selected[0] if len(selected) == 1 else None)
    )
    if anchor and anchor.get("asset_id") and relation == "under":
        info = workflow.inspect_asset(target, anchor["asset_id"])
        recipe = (info.get("metadata") or {}).get("recipe") or {}
        if recipe.get("kind") in {"table", "chair", "stool", "bench"}:
            p = recipe["parameters"]
            up = 1 if scene.get("engine") == "unity" else 2
            clearance = (
                (
                    p.get("seat_height", p["height"])
                    - p.get("thickness", min(p["width"], p["depth"]) * 0.11)
                )
                * anchor["scale"][up]
            ) - gap
    planned = layout.plan(scene, items, relation, anchor_id, gap, fit, clearance, face_anchor)
    task = workflow.action(
        target,
        "arrange",
        values={
            **{k: planned[k] for k in ("scene", "anchor", "placements")},
            "snap_to_surface": snap_to_surface,
        },
    )
    return await get_task_status(task["request_id"], 10)


@mcp.tool()
async def get_task_status(request_id: str, wait_seconds: float = 0) -> dict:
    """Query or wait up to 30 seconds for any editor action, preview or build task."""
    return await asyncio.to_thread(
        workflow.job_status, str(project()["project"]), request_id, wait_seconds
    )


@mcp.tool()
def cancel_task(request_id: str) -> dict:
    """Request cancellation. A native import already in progress may finish; check status."""
    return workflow.cancel(str(project()["project"]), request_id)


@mcp.tool()
async def inspect_scene() -> dict:
    """Read the active scene and actual selected managed props to resolve 'this object'."""
    task = workflow.action(str(project()["project"]), "inspect")
    return await get_task_status(task["request_id"], 10)


@mcp.tool()
async def edit_scene(
    operation: str, values: dict | None = None, scope: str = "selected", asset_id: str | None = None
) -> dict:
    """Direct engine edit: transform, tint, ground or focus, without a Blender rebuild.

    selected scope changes selected managed instances only. asset scope changes all LOADED
    instances of asset_id in this scene. transform values: move=[x,y,z] meters, rotate=[x,y,z]
    degrees, scale=[x,y,z] multipliers. tint values: color=[r,g,b] linear, optional material=
    original Blender material name. Result contains undo_id for restoring the edit.
    """
    if operation not in {"transform", "tint", "focus", "ground"}:
        raise ValueError("Use transform, tint, ground or focus")
    task = workflow.action(
        str(project()["project"]), operation, asset_id=asset_id, scope=scope, values=values
    )
    return await get_task_status(task["request_id"], 10)


@mcp.tool()
async def undo_scene_edit(undo_id: str) -> dict:
    """Restore a tool edit's instance transforms/material overrides in its original scene."""
    task = workflow.action(str(project()["project"]), "undo", undo_id=undo_id)
    return await get_task_status(task["request_id"], 10)


@mcp.tool()
def restore_asset(asset_id: str, revision: str | None = None) -> dict:
    """Reimport a previous successful source, retaining scene instances."""
    return workflow.restore(str(project()["project"]), asset_id, revision)


@mcp.tool()
async def get_preview(
    asset_id: str | None = None, request_id: str | None = None, view: str = "studio"
):
    """Return an engine PNG of selected props or asset. If queued, retry with request_id."""
    if request_id is None:
        task = workflow.action(
            str(project()["project"]),
            "preview",
            asset_id=asset_id,
            scope="asset" if asset_id else "selected",
            values={"view": view},
        )
        request_id = task["request_id"]
    result = await get_task_status(request_id, 30)
    if result.get("status") != "completed":
        return result
    relative = result.get("preview")
    if relative != "previews/" + workflow.identifier(request_id) + ".png":
        raise ValueError("This request is not a preview")
    root = core.state_root(registry.resolve().root)
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Invalid preview path/size")
    return Image(data=Path(path).read_bytes(), format="png")


@mcp.resource(
    workbench.URI,
    mime_type="text/html;profile=mcp-app",
    meta={"ui": {"prefersBorder": True, "csp": {"connectDomains": [], "resourceDomains": []}}},
)
def workbench_resource() -> str:
    """Optional task UI; clients without MCP Apps use the normal tools or local app."""
    return workbench.page()


@mcp.tool(meta={"ui": {"resourceUri": workbench.URI}})
def open_workbench() -> dict:
    """Show the unified task, selection, preview, generation and review workbench.

    MCP Apps-capable hosts can display this in chat. Other clients can use all normal tools
    and the double-click local app; an embedded UI is never required for the workflow.
    """
    return workbench.dispatch("state")


@mcp.tool(meta={"ui": {"resourceUri": workbench.URI, "visibility": ["app"]}})
def workbench_action(action: str, values: dict | None = None) -> dict:
    """Perform a workbench button action. Uses the same validated workflows as normal tools."""
    return workbench.dispatch(action, values)


@mcp.tool()
def compose_scene(
    kit: str = "reading_corner",
    prefix: str = "corner",
    position: list[float] | None = None,
    yaw: float = 0,
    anchor_id: str | None = None,
    mode: str = "create",
    template: str | None = None,
    asset_ids: list[str] | None = None,
) -> dict:
    """Build and furnish a small scene, or save/place a reusable layout in this project.

    create builds a matching kit then places it around its table; selected upright anchors
    supply position/yaw. An explicit position is metres in engine axes. mode=save records
    selected instances (or asset_ids) as template; mode=place duplicates saved instances.
    Poll the returned workflow ID. Interrupted workflows resume without repeating completed
    stages. Result has undo_id. Arbitrary horizontal yaw is supported, tilted anchors are not.
    """
    return compositions.submit(
        str(project()["project"]), kit, prefix, position, yaw, anchor_id, mode, template, asset_ids
    )


@mcp.tool()
def edit_imported_part(
    asset_id: str,
    part: str,
    changes: dict | None = None,
    members: list[str] | None = None,
    lock_geometry: bool | None = None,
    lock_material: bool | None = None,
    replacement_path: str | None = None,
) -> dict:
    """Group, edit, lock or replace parts of an imported static model.

    inspect_asset.report.parts lists source parts. members groups existing named parts into
    part. Changes: scale/offset/rotation XYZ in Blender Z-up, linear color RGB, roughness,
    metallic. replacement_path is a local GLB/glTF/FBX/BLEND fitted to the chosen part bounds.
    Unlock explicitly before changes. Untouched parts and engine instances retain identity.
    A single fused mesh is one part: this tool does not invent semantic segmentation.
    """
    return parts.edit(
        str(project()["project"]),
        asset_id,
        part,
        changes,
        members,
        lock_geometry,
        lock_material,
        replacement_path,
    )


@mcp.tool()
def set_art_brief(
    image_path: str | None = None,
    reference_asset: str | None = None,
    notes: str = "",
    overrides: dict | None = None,
) -> dict:
    """Persist a reference image and art direction; optionally adopt a recipe style/palette.

    Use the client's vision for interpretation. Images are reference evidence, not a claim of
    automatic style extraction or reconstruction. Existing assets require explicit edits.
    """
    return quality.set_brief(
        str(project()["project"]), image_path, reference_asset, notes, overrides
    )


@mcp.tool()
def get_art_reference():
    """Return the saved reference image for client visual review; notes are in open_workbench."""
    import base64

    uri = workbench.image("reference")["url"]
    header, data = uri.split(",", 1)
    return Image(data=base64.b64decode(data), format=header.split("/")[1].split(";")[0])


@mcp.tool()
def review_quality(asset_id: str, auto_fix: bool = False, preset: str = "scene_prop") -> dict:
    """Measure native issues and capture same-camera before/after with a two-repair limit.

    auto_fix aligns to a detected collision surface only when the measured gap is <=0.5m.
    Visual findings need client vision, using get_preview and get_art_reference. No aesthetic
    score or visual-pass claim is generated. repair_quality applies concrete part edits and
    refreshes the comparison automatically. Poll the exact workflow via get_task_status.
    """
    return quality.start(str(project()["project"]), asset_id, auto_fix, preset)


@mcp.tool()
def repair_quality(request_id: str, part: str, changes: dict) -> dict:
    """Apply a concrete part repair to a completed quality review, then recapture and recheck.

    At most two repairs including automatic grounding; rejects assets changed outside this
    review. Wait for the returned review request, then inspect its fresh before/after images.
    """
    return quality.repair(str(project()["project"]), request_id, part, changes)


@mcp.tool()
def inspect_performance(
    asset_id: str | None = None,
    request_id: str | None = None,
    preset: str = "scene_prop",
    wait_seconds: float = 0,
) -> dict:
    """Read actual native triangles, vertices, material slots, textures and LOD counts.

    If queued, retry with request_id. Presets mobile_prop/scene_prop/hero_prop expose budgets.
    Texture bytes are an RGBA8+mip estimate, not measured VRAM. Shared meshes are identified;
    FPS and draw calls require an actual engine profiler and are never inferred here.
    """
    return performance.inspect(
        str(project()["project"]), asset_id, request_id, preset, wait_seconds
    )


@mcp.tool()
def apply_usage_preset(asset_id: str, preset: str = "scene_prop") -> dict:
    """Prepare a retained source for mobile_prop, scene_prop or hero_prop with measured LODs.

    Uses the preset's triangle budget, texture resolution and LOD ratios. Reduction may fail
    explicitly when its deviation limit cannot be met; existing imported geometry stays usable.
    """
    return performance.optimize(str(project()["project"]), asset_id, preset)


@mcp.tool()
def list_generation_providers() -> dict:
    """List optional configured Meshy/self-hosted generation adapters; never return secrets."""
    return {
        "providers": generation.inventory(),
        "usage_presets": performance.PRESETS,
        "layouts": compositions.templates(str(project()["project"])),
    }


@mcp.tool()
def generate_model(
    asset_id: str,
    prompt: str,
    provider: str = "local",
    image_paths: list[str] | None = None,
    candidate_count: int = 1,
    preview_only: bool = True,
    allow_paid: bool = False,
    settings: dict | None = None,
    position: list[float] | None = None,
) -> dict:
    """Generate 1-3 textured GLB candidates, then use the existing preparation/import pipeline.

    Configure providers in the local app. Meshy consumes credits: allow_paid only when user
    authorization covers this provider/count. Self-hosted adapter implements docs/PROVIDERS.md.
    Optional 1-4 PNG/JPEG references. Default candidates stay outside the scene for review;
    publish_prepared selects one. Saved provider IDs survive interruption without resubmission.
    Cancellation stops local work; an already submitted provider task may still consume credits.
    """
    return generation.submit(
        str(project()["project"]),
        asset_id,
        prompt,
        provider,
        image_paths,
        candidate_count,
        preview_only,
        allow_paid,
        settings,
        position,
    )


@mcp.tool()
def resume_workflow(request_id: str) -> dict:
    """Resume an interrupted composition, quality or generation task using its saved stages."""
    return background.resume(str(project()["project"]), request_id)


def main():
    try:
        mcp.run(transport="stdio")
    finally:
        # SDK wrappers can close stdout during garbage collection after disconnect.
        # PyInstaller flushes it again during shutdown, so give that flush a live sink.
        if getattr(sys, "frozen", False):
            sys.stdout = sys.__stdout__ = open(os.devnull, "w")
