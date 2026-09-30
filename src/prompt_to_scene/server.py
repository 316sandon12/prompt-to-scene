"""MCP tools; the user's existing AI client supplies natural-language understanding."""

import asyncio

from mcp.server.fastmcp import FastMCP

from .core import build, inspect_project, wait_for_status
from .targets import configured_target

mcp = FastMCP(
    "Prompt-to-Scene",
    instructions="""
Create static opaque PBR assets in Blender, then publish to the configured Unity or Unreal project.
Inspect the target first. Blender scripts must create an Export collection containing meshes,
use meters, +Z up, applied modifiers, Principled BSDF materials. Python runs with local user
permissions. Read tool errors and fix the asset. Build returns QUEUED, not imported: always poll
get_asset_status with the returned request_id (wait_seconds up to 30). Only report success when
the request matches and status is imported. Position is target-engine XYZ in meters: Unity Y-up,
Unreal Z-up (converted to centimeters by the adapter). Reuse asset_id for revisions.
Existing scene instance transforms are preserved. Unity retains prefab root components; Unreal
retains its StaticMeshActor. Generated geometry and managed material properties are replaced.
This is not an image-to-3D model. Author bpy Python or publish a saved .blend from another tool.
""",
)


def project():
    target = configured_target()
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
    return await asyncio.to_thread(
        build,
        **project(),
        name=asset_id,
        script=blender_python,
        position=position,
        collider=collider,
    )


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
    return await asyncio.to_thread(
        build,
        **project(),
        name=asset_id,
        script="",
        position=position,
        collider=collider,
        blend_file=blend_file,
    )


@mcp.tool()
async def get_asset_status(
    asset_id: str, request_id: str | None = None, wait_seconds: float = 0
) -> dict:
    """Read an engine receipt, optionally wait up to 30s for a specific build request.

    Pass the build's request_id to prevent stale success. A wait timeout remains queued/unknown;
    superseded means another revision is current. Imported includes paths, geometry and scene.
    """
    return await asyncio.to_thread(
        wait_for_status,
        **project(),
        name=asset_id,
        request_id=request_id,
        wait_seconds=wait_seconds,
    )


def main():
    mcp.run(transport="stdio")
