"""MCP tools; the user's existing AI client supplies natural-language understanding."""

import os

from mcp.server.fastmcp import FastMCP

from .core import build, inspect_project, status

mcp = FastMCP(
    "Prompt-to-Scene",
    instructions="""
Create static opaque PBR assets in Blender and publish them to the configured Unity project.
Inspect the target first. Blender scripts must create an Export collection containing meshes,
use meters, +Z up, applied modifiers, Principled BSDF materials. Python runs with local user
permissions. Read tool errors and fix the asset. Build returns QUEUED, not imported: always poll
get_asset_status and only report success when its request_id matches and status is imported.
Reuse asset_id for revisions. Existing scene instance transforms and prefab root components
are preserved; the generated Visual subtree and managed material properties are regenerated.
This is not an image-to-3D model. Author bpy Python or publish a saved .blend from another tool.
""",
)


def project():
    value = os.environ.get("PTS_UNITY_PROJECT")
    if not value:
        raise ValueError("Set PTS_UNITY_PROJECT to an existing Unity project's absolute path")
    return value


@mcp.tool()
def inspect_target() -> dict:
    """Inspect Blender, Unity heartbeat, rendering pipeline and previous asset receipts."""
    return inspect_project(project())


@mcp.tool()
def build_asset(
    asset_id: str,
    blender_python: str,
    position: list[float] | None = None,
    collider: bool = True,
) -> dict:
    """Execute trusted bpy code in background Blender; save .blend and queue Unity import.

    Use stable asset_id (lowercase letters/digits/_/-) to update the same asset. Position is
    Unity XYZ meters, applied ONLY when first placing the asset. Each script builds a complete
    asset from scratch. Delete default scene objects, create an Export collection, link meshes
    to it. v0.1: static meshes, constant opaque PBR, direct base-color / tangent normal textures.
    Unsupported materials fail explicitly. No paid model API or additional Blender MCP required.
    """
    return build(project(), asset_id, blender_python, position, collider)


@mcp.tool()
def publish_blend(
    asset_id: str,
    blend_file: str,
    position: list[float] | None = None,
    collider: bool = True,
) -> dict:
    """Publish the Export collection of an existing saved .blend without modifying the original.

    Use this after another Blender tool has modeled and saved an asset. Same material contract
    and queued/result semantics as build_asset. Blender file auto-execution is disabled.
    """
    return build(project(), asset_id, "", position, collider, blend_file=blend_file)


@mcp.tool()
def get_asset_status(asset_id: str) -> dict:
    """Read Unity's receipt: request ID, asset paths, geometry, bounds, scene and errors."""
    return status(project(), asset_id)


def main():
    mcp.run(transport="stdio")
