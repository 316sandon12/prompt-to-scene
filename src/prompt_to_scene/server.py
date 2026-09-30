"""MCP tools; the user's existing AI client supplies natural-language understanding."""

import asyncio
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from . import authoring, core, layout, recipes, registry, studies, styles, workflow
from .core import inspect_project, wait_for_status

mcp = FastMCP(
    "Prompt-to-Scene",
    instructions="""
Create static opaque PBR assets in Blender, then publish to the configured Unity or Unreal project.
If no project is connected, use list_projects then connect_project with the user's chosen project.
Use inspect_library for nine designed recipes, semantic parts, styles and quality budgets.
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
    """Edit or lock one semantic part of a shared recipe; inspect_asset lists its parts.

    Changes: scale XYZ factors, offset XYZ meters, rotation XYZ degrees, color linear RGB,
    material wood/metal/paint/stone, roughness and wear. Part coordinates are Blender Z-up.
    Geometry transforms pivot around the part's bottom center. Locks retain their saved
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
) -> dict:
    """Place managed props relative to a selected real scene anchor, with collision checks/undo.

    items: [{asset_id, count=1, object_id?}], up to 32 instances. Relations: around, along,
    under, right, front. fit can shrink under-anchor props. Uses world-axis bounds; anchor
    should align to 90-degree axes. Existing instances move, additional ones are duplicated.
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
    planned = layout.plan(scene, items, relation, anchor_id, gap, fit, clearance)
    task = workflow.action(
        target, "arrange", values={k: planned[k] for k in ("scene", "anchor", "placements")}
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
    """Direct engine edit: transform, tint or focus, without a Blender rebuild.

    selected scope changes selected managed instances only. asset scope changes all LOADED
    instances of asset_id in this scene. transform values: move=[x,y,z] meters, rotate=[x,y,z]
    degrees, scale=[x,y,z] multipliers. tint values: color=[r,g,b] linear, optional material=
    original Blender material name. Result contains undo_id for restoring the edit.
    """
    if operation not in {"transform", "tint", "focus"}:
        raise ValueError("Use transform, tint or focus")
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
async def get_preview(asset_id: str | None = None, request_id: str | None = None):
    """Return an engine PNG of selected props or asset. If queued, retry with request_id."""
    if request_id is None:
        task = workflow.action(
            str(project()["project"]),
            "preview",
            asset_id=asset_id,
            scope="asset" if asset_id else "selected",
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


def main():
    try:
        mcp.run(transport="stdio")
    finally:
        # SDK wrappers can close stdout during garbage collection after disconnect.
        # PyInstaller flushes it again during shutdown, so give that flush a live sink.
        if getattr(sys, "frozen", False):
            sys.stdout = sys.__stdout__ = open(os.devnull, "w")
