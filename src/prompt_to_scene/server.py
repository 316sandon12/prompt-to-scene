"""MCP tools; the user's existing AI client supplies natural-language understanding."""

import asyncio
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from . import core, recipes, registry, workflow
from .core import inspect_project, wait_for_status

mcp = FastMCP(
    "Prompt-to-Scene",
    instructions="""
Create static opaque PBR assets in Blender, then publish to the configured Unity or Unreal project.
If no project is connected, use list_projects then connect_project with the user's chosen project.
Prefer create_prop recipes for crates, tables, chairs and signs. For other shapes author bpy.
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
) -> dict:
    """Create a repeatable crate/table/chair/sign. Dimensions are meters; colors are linear RGB.

    Parameters: width, depth, height, color, metal_color, roughness; crate: planks; table:
    thickness; chair: seat_height; sign: board_height. Omit position to place near the editor
    camera on the ground. Parameters persist across clients for revise_prop.
    """
    script, recipe = recipes.prepare(kind, parameters)
    return workflow.submit(
        str(project()["project"]), asset_id, script, position, collider, recipe=recipe
    )


@mcp.tool()
def inspect_asset(asset_id: str) -> dict:
    """Read source script, recipe parameters and successful revisions before editing."""
    return workflow.inspect_asset(str(project()["project"]), asset_id)


@mcp.tool()
def revise_prop(asset_id: str, parameters: dict) -> dict:
    """Change supplied recipe parameters; retain other details and instance transforms."""
    info = workflow.inspect_asset(str(project()["project"]), asset_id)
    recipe = (info.get("metadata") or {}).get("recipe")
    if not recipe:
        raise ValueError(
            "Custom model: read inspect_asset's script and revise that script with build_asset."
        )
    script, recipe = recipes.prepare(recipe["kind"], {**recipe["parameters"], **parameters})
    return workflow.submit(
        str(project()["project"]),
        asset_id,
        script,
        recipe=recipe,
        collider=info["metadata"].get("collider", True),
    )


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
        # The SDK closes its TextIOWrapper over stdout on clean disconnect.
        # PyInstaller flushes stdout once more during shutdown; keep that flush valid.
        if sys.stdout is not None and sys.stdout.closed:
            sys.stdout = open(os.devnull, "w")
