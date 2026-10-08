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
    development,
    generation,
    kits,
    layout,
    levels,
    organization,
    parts,
    performance,
    project_library,
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
Use game_workflow as the primary entrypoint: search actions, describe their contract, then execute
with values. Installed clients expose only game_workflow, open_workbench and workbench_action.
All other tool names mentioned below remain callable through game_workflow by their exact name.
Use produce for a durable batch of custom scripts, recipes, sources, saved designs or interactive
props, optionally furnished into an existing level and reviewed. Poll its one parent request;
resume reuses completed stages. Prefer custom bpy for detailed shapes, not recipe substitution.
Use save_design/reuse_design for editable source families, and find_assets for purpose/style/size
matching from metadata and observed descriptions. Use review with view=game for the actual game
camera and lighting, review_images to inspect pixels, and feedback to retain concrete observations
and preferences. Never accept appearance from technical checks alone. Repair named parts only.
Furnish measures existing rooms and props, reserves approach/walking space, and undoes placement
if native clearance fails. It does not infer arbitrary floor plans or prove NavMesh traversal.
Create static PBR assets in Blender, then publish to the configured Unity or Unreal project.
Emission, alpha-cutout and ordinary alpha blending are supported; refraction remains unsupported.
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
FBX or Blender model produced by another AI tool. Import automatically prepares static PBR,
measured simplification, native LODs and collision. Use preview_only then publish_prepared when
the user wants to review first. Check the preparation report and before/studio views: sampled
shape error is not an aesthetic guarantee. prepare_asset reprocesses the retained original.
Use create_style_kit for coherent curated sets. edit_selected_prop resolves the editor selection
before changing a recipe; do not guess which asset the user means. capture_review before/after
reuses an engine camera frame so the user can compare actual engine results.
New props inherit get_project_style. set_project_style remembers concrete art direction; reference
images can inform palette/shape through the client's own vision, not hidden image-to-3D claims.
Read game_art_direction before modeling. Save the user's gameplay, world and look once.
Existing-project style matching starts with real images: capture representative native assets
with describe_project_assets or use a saved reference, then call match_game_style to see them.
When no art direction has been established, use available project/reference images before the
first themed build. If none exist, proceed from the user's text and state the visual assumptions.
Use the host's vision to supply observations and numeric style via its returned source_token.
Match proportion, construction, finish and detail density as well as palette. Do not force a
genre preset or invent visual evidence. Inferred colors/roughness are estimates under that light.
Interpret that context into concrete design_asset silhouette/structure/materials/story
decisions. Do not ask users to fill schemas. Detailed/themed requests default to custom build_asset
following that brief, with coherent primary/secondary shapes and functional construction. Use
create_prop/create_prop_set only when the described form really fits a listed recipe; those receive
saved construction treatments automatically. Do not substitute a plain template for a specific
art request. Inspect a real source render and address concrete flaws within the existing repair
limit; reference notes, extra polygons and a successful import are not evidence of visual quality.
edit_prop_part edits or locks named parts;
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
For playable props use create_interactive_prop (door/chest/pickup/resource/switch), or use
configure_interaction
with separate moving geometry for doors/chests. Resource uses, event_id, label, interaction_point
and depleted_asset_id configure range-checked interactions and depleted visuals. Unity exposes
onGameEvent/onDepleted; UE exposes GameEventId and OnInteracted/OnDepleted. They are hooks, not an
automatic inventory/quest integration. Read individual native Play/PIE assertions when testing.
protect_asset keeps custom material assignments and sibling attachment points; review_asset_update
compares a prepared candidate before publishing. Missing protected slots stop reimport.
set_scene_look applies/restores an owned lighting/sky/post/camera rig; capture it to inspect beauty.
build_level connects room/corridor/stair modules and checks capsule clearance; it is a blockout,
not a whole-game generator. run_playcheck enters and exits the real editor Play/PIE session,
tests interactions/clearance and measures frame deltas. Check development.passed and all checks.
search_project_assets indexes local models/prefabs; reuse_project_asset previews/places originals.
tag_project_asset saves notes/tags and declared source/license; keep unknowns explicit.
organize_project_assets scans the project's native asset inventory, plans consistent names/folders,
then applies that exact plan with reference-preserving native renames and a persistent undo journal.
Use scan -> poll -> plan(scan_id=request_id) -> apply(plan_id) -> poll. An organization request
authorizes applying the plan; show a preview first if requested. Skip protected paths and
code/config assets; custom string loading paths need exclusions. Use overrides for semantic names.
Read project_conventions for saved naming, preparation and inbox defaults. New managed assets
follow those rules; existing managed locations stay stable. manage_asset_inbox scans settled
sources once per revision; enabled watching runs while the app, MCP host or native editor is open.
describe_project_assets captures real thumbnails and metrics. Use get_asset_evidence before
save_asset_description; record uncertainty and retain user corrections. Remote vision is optional.
adapt_asset_materials previews a reference look on separate native variants, then applies chosen
material rows or undoes assignments. Inspect actual before/after images and unsupported-field
warnings. Unity targets prefabs; UE targets static meshes. Never claim a different shader matches
perfectly or that native Windows editor tests ran when only portable CI was available.
""",
)


def project():
    target = registry.resolve()
    return {"project": target.project_file or target.root, "engine": target.engine}


@mcp.tool()
def game_art_direction(settings: dict | None = None) -> dict:
    """Read/save gameplay, world, style_notes, view and construction for this game.

    Interpret the user's description with the current AI host; do not require a form.
    view: isometric/top_down/third_person/first_person.
    construction: handcrafted/salvaged/machined. Partial updates retain omitted fields.
    detail: auto/readable/balanced/closeup; match_game_style learns from actual reference images.
    Text guides custom modeling; structured choices also affect recipe geometry/surfaces.
    This changes future briefs, not already imported assets. Use set_project_style for palette.
    """
    from . import game_art

    return game_art.configure(None, settings)


@mcp.tool()
def match_game_style(
    evidence_ids: list[str] | None = None,
    use_reference: bool = False,
    source_token: str | None = None,
    analysis: dict | None = None,
):
    """Recognize this project's look using actual images and the current AI host's vision.

    First pass evidence IDs from describe_project_assets, or use_reference for set_art_brief's
    saved image. Returns the images and a source_token. Inspect them; then call again with that
    token and analysis using the returned schema. Applies inferred palette, material roughness,
    shape parameters, detail density and art notes to future designs. Confidence below 0.6 keeps
    current defaults. No external vision service is invoked and existing assets are not changed.
    The host interprets images; the tool validates/saves the interpretation, not a beauty score.
    """
    import json

    from . import style_matching

    if analysis is not None:
        return style_matching.apply(None, source_token, analysis)
    result = style_matching.inspect(None, evidence_ids, use_reference)
    return [
        json.dumps(result, ensure_ascii=False),
        *[Image(path=row["path"]) for row in result.get("sources", [])],
    ]


@mcp.tool()
async def game_workflow(
    operation: str = "search",
    action: str | None = None,
    values: dict | None = None,
    query: str = "",
):
    """One entry for a game-development task. Search/describe only the capability needed.

    Start with context and find_assets/find_designs, then produce a saved plan containing
    recipe/custom/source/template/interactive items. A single task tracks building, importing,
    gameplay attachment, optional room furnishing and review. Retry with resume, not a new plan.
    review_images returns actual images; inspect them before saving feedback or repairing parts.
    Existing tools are also available by their exact action name through this gateway.
    """
    import json

    from mcp.types import CallToolResult

    from . import production

    if action in production.routes() or operation == "search":
        result = production.dispatch(None, operation, action, values, query)
        if operation == "search":
            legacy = await mcp.list_tools()
            result["existing_tools"] = [
                {"action": t.name, "description": t.description.split("\n")[0]}
                for t in legacy
                if t.name not in {"game_workflow", "workbench_action"}
                and query
                and all(
                    word in (t.name + " " + t.description).lower() for word in query.lower().split()
                )
            ]
        if operation == "execute" and action == "review_images":
            return [
                json.dumps(result, ensure_ascii=False),
                *[Image(path=row["path"]) for row in result["images"]],
            ]
        return result
    legacy = {
        t.name: t
        for t in await mcp.list_tools()
        if t.name not in {"game_workflow", "workbench_action"}
    }
    if action not in legacy:
        raise ValueError("Unknown action; search workflow capabilities first")
    if operation == "describe":
        return {
            "action": action,
            "description": legacy[action].description,
            "parameters": legacy[action].inputSchema,
        }
    if operation != "execute":
        raise ValueError("Use search, describe or execute")
    result = await mcp.call_tool(action, values or {})
    if isinstance(result, tuple):
        return CallToolResult(content=result[0], structuredContent=result[1])
    if isinstance(result, dict):
        return result
    return CallToolResult(content=result)


@mcp.tool()
def design_asset(
    asset_id: str,
    description: str | None = None,
    role: str = "environment",
    focal_point: str = "",
    recipe_kind: str | None = None,
    decisions: dict | None = None,
) -> dict:
    """Save/read an asset design tied to the game's context and reference notes.

    Omit description to read. role: environment/interactable/hero. Supply concrete decisions
    (silhouette, structure, materials, story, avoid) derived from gameplay and world context.
    Default route is custom Blender modeling; specify recipe_kind only if a listed form fits.
    Build the same asset_id to retain this immutable brief with its source revision. Existing
    recipe revisions keep their original design; planning alone does not rebuild geometry.
    Follow the returned design, then inspect a real render. No model API or beauty score is used.
    """
    from . import game_art

    return game_art.plan(None, asset_id, description, role, focal_point, recipe_kind, decisions)


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
    to it. Static PBR, emission and alpha mask/blend; supported designed graphs bake automatically.
    Unsupported materials fail explicitly. No paid model API or additional Blender MCP required.
    """
    return authoring.build_custom(
        str(project()["project"]), asset_id, blender_python, position, collider
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
    apply_design: bool = False,
) -> dict:
    """Change shared recipe dimensions or apply the current project style; preserve locked parts.

    This changes every instance using this asset. For one instance use edit_scene instead.
    apply_design uses this asset's saved design_asset brief, including construction details.
    Omit it to retain the original design. Geometry/material locks remain independent.
    """
    return authoring.revise(
        str(project()["project"]), asset_id, parameters, apply_project_style, quality, apply_design
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
    """Return an engine PNG. Retry queued captures with their request_id.

    For a completed playcheck with captures, view='before' returns the initial image;
    the default returns the post-interaction image.
    """
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
    expected = "previews/" + workflow.identifier(request_id) + ".png"
    relative = result.get("preview")
    check = result.get("development", {})
    if check.get("command") == "playcheck":
        expected = "previews/" + request_id + ("_before" if view == "before" else "") + ".png"
        relative = expected if expected in check.get("screenshots", []) else None
    if relative != expected:
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


@mcp.tool()
def create_interactive_prop(
    kind: str,
    asset_id: str,
    dimensions: list[float] | None = None,
    position: list[float] | None = None,
    color: list[float] | None = None,
) -> dict:
    """Build a door, chest or pickup with Blender geometry and native gameplay behavior.

    Dimensions are width/depth/height in meters; position uses target engine axes. Retains
    separate base/moving meshes and a reusable Unity prefab or UE Blueprint. Poll this workflow
    until completed. Aim the game camera and press E for the optional demo, or bind your own input.
    """
    return development.interactive(None, kind, asset_id, dimensions, position, color)


@mcp.tool()
def configure_interaction(
    asset_id: str,
    kind: str,
    moving_asset_id: str | None = None,
    angle: float = 90,
    distance: float = 2.5,
    pivot: list[float] | None = None,
    moving_offset: list[float] | None = None,
    demo_input: bool = True,
    uses: int = 3,
    event_id: str = "",
    label: str = "",
    depleted_asset_id: str | None = None,
    interaction_point: list[float] | None = None,
) -> dict:
    """Attach/update door/chest/pickup behavior. Pivot/offset are local engine XYZ meters.

    A door/chest requires a separate prepared moving asset. The first UE attachment converts
    the plain managed StaticMeshActor to a native Blueprint; later revisions keep that Actor.
    """
    return development.configure(
        None,
        asset_id,
        kind,
        moving_asset_id,
        angle,
        distance,
        pivot,
        moving_offset,
        demo_input,
        uses=uses,
        event_id=event_id,
        label=label,
        depleted_asset_id=depleted_asset_id,
        interaction_point=interaction_point,
    )


@mcp.tool()
def protect_asset(
    asset_id: str,
    mode: str = "inspect",
    bindings: list[dict] | None = None,
    sockets: list[dict] | None = None,
) -> dict:
    """Inspect/set/clear custom material overrides and persistent root attachment points.

    bindings: [{slot, material_path}] in Assets/ or /Game/. sockets: [{name, position, rotation}]
    use engine XYZ meters/degrees. Missing protected slots block later imports. Generated material
    property edits and arbitrary generated hierarchy changes are outside the preservation contract.
    """
    return development.protection(None, asset_id, mode, bindings, sockets)


@mcp.tool()
def review_asset_update(asset_id: str, candidate_request_id: str) -> dict:
    """Read native protected slot conflicts before publishing a completed prepared candidate."""
    return development.review_update(None, asset_id, candidate_request_id)


@mcp.tool()
def set_scene_look(
    preset: str = "warm_cartoon", mode: str = "apply", position: list[float] | None = None
) -> dict:
    """Apply/inspect/capture/restore warm_cartoon, cool_scifi, moonlit or neutral scene lighting.

    Owns a native lighting/sky/post-process/camera rig; saves prior lighting for restore. The
    presentation camera stays fixed across preset changes. Poll request; get_preview(request_id)
    reads captures. Existing scene lights are disabled while the owned look is active.
    """
    return development.look(None, preset, mode, position)


@mcp.tool()
def build_level(level_id: str, mode: str = "build", settings: dict | None = None) -> dict:
    """Plan/build/check/remove a connected modular level with real collision clearance.

    settings: modules=[{cell:[grid_x,grid_y,floor],kind:room|corridor|stair,direction:0..3}],
    cell_size, story_height, door_width/height, player_radius/height, max_step, position, yaw.
    Directions: south/east/north/west. Stairs need a lower and upper connected landing. Max 24
    modules. Disconnected/too-small plans fail before editor mutation. Native checking uses sampled
    standing capsules, not a baked NavMesh or a complete character-controller simulation.
    """
    return levels.build(None, level_id, mode, **(settings or {}))


@mcp.tool()
def run_playcheck(
    asset_ids: list[str] | None = None,
    level_id: str | None = None,
    duration: float = 3,
    capture: bool = True,
) -> dict:
    """Run interaction/range/geometry and optional level-clearance checks in real Play/PIE.

    Requires Edit mode. Restores Edit mode after completion/cancellation; existing game scripts
    run normally. Poll the same ID; inspect development.passed, checks and warnings. Frame deltas
    are measured on this editor/machine, not a target-device benchmark. No paid AI is used.
    """
    return development.playcheck(None, asset_ids, level_id, duration, capture)


@mcp.tool()
def search_project_assets(
    query: str = "", request_id: str | None = None, size: float | None = None, limit: int = 20
) -> dict:
    """Index project meshes/prefabs, then rank names, tags, materials, notes and desired size.

    First call queues the native index. Poll then call again with the same request_id and query.
    Returns paths, dimensions, measured geometry and declared license. Preview before placement
    using reuse_project_asset(mode='preview'). This is local keyword search with Chinese aliases.
    """
    return project_library.search(None, query, request_id, size, limit)


@mcp.tool()
def reuse_project_asset(
    path: str, mode: str = "place", position: list[float] | None = None
) -> dict:
    """Preview or place an existing project model/prefab/Blueprint by its returned native path.

    Reuses the original native asset; does not duplicate asset files or claim new authorship.
    get_preview(request_id) reads the preview PNG after the action completes.
    """
    return project_library.reuse(None, path, mode, position)


@mcp.tool()
def tag_project_asset(
    path: str, tags: list[str] | None = None, notes: str = "", license: str = "", source: str = ""
) -> dict:
    """Save searchable local annotations and user-declared source/license for an asset path."""
    return project_library.annotate(None, path, tags, notes, license, source)


@mcp.tool()
def organize_project_assets(
    mode: str = "scan",
    scan_id: str | None = None,
    plan_id: str | None = None,
    scope: str | None = None,
    settings: dict | None = None,
    offset: int = 0,
    limit: int = 200,
) -> dict:
    """Automatically name/classify project assets through native Unity/UE moves; supports undo.

    scan: inventory Assets or /Game, optionally one subfolder; poll get_task_status. plan: use
    scan_id equal to the completed scan request_id. settings: destination, rename (bool), group_by
    ('type' or 'source'), exclude (project paths), overrides ({old_path:semantic_name}), rules
    ({kind:{folder,prefix}}). inspect: paginated exact plan; history: recent plans. apply/undo:
    use the saved plan_id then poll. Applies collision-resolved names, verifies stale candidates,
    preserves GUID/native references and records inverse moves. Native files are saved; unrelated
    scene edits are not rolled back. Protected folders, scripts, scenes/data/unknown types stay
    in place with reasons. Unreal keeps required redirectors. Code/config string paths are not
    rewritten; exclude those resources. No model provider, visual AI guessing or paid calls.
    """
    return organization.organize(None, mode, scan_id, plan_id, scope, settings, offset, limit)


@mcp.tool()
def project_conventions(
    mode: str = "read", settings: dict | None = None, scan_id: str | None = None
) -> dict:
    """Read/save shared naming, folder, preparation and intake defaults, or suggest prefixes
    from a native scan."""
    from . import project_profiles

    return project_profiles.configure(str(project()["project"]), mode, settings, scan_id)


@mcp.tool()
def manage_asset_inbox(mode: str = "status", paths: list[str] | None = None) -> dict:
    """Scan the designated source inbox, inspect jobs, or explicitly retry failed revisions.
    Originals are retained."""
    from . import intake

    return intake.manage(str(project()["project"]), mode, paths)


@mcp.tool()
def describe_project_assets(
    paths: list[str], use_provider: bool = False, allow_remote: bool = False
) -> dict:
    """Capture actual model thumbnails and metadata. Optional vision labels require a configured
        endpoint.

    Without a provider, poll this job, call get_asset_evidence on each evidence request_id, inspect
    the image, then save_asset_description. Never claim content recognition from filenames alone.
    """
    from . import semantics

    return semantics.start(str(project()["project"]), paths, use_provider, allow_remote)


@mcp.tool()
def get_asset_evidence(evidence_id: str):
    """Return the native thumbnail that supports an asset description."""
    from . import semantics

    _, path = semantics.evidence(str(project()["project"]), evidence_id)
    return Image(data=path.read_bytes(), format="png")


@mcp.tool()
def save_asset_description(evidence_id: str, description: dict, corrected: bool = False) -> dict:
    """Index a visual description: name, object_type, description, materials[], style, uses[],
        confidence.

    Keep uncertainty visible. Only set corrected for an explicit user correction. Corrections
    are protected from later automatic runs. This updates search metadata, not native filenames.
    To rename, use the saved name as an organize_project_assets override for the selected path.
    """
    from . import semantics

    return semantics.save(str(project()["project"]), evidence_id, description, corrected)


@mcp.tool()
def configure_asset_vision(
    endpoint: str | None = None, model: str | None = None, api_key: str | None = None
) -> dict:
    """Configure an optional OpenAI-compatible vision endpoint. Credentials stay in the OS store."""
    from . import semantics

    return semantics.configure(endpoint, model, api_key)


@mcp.tool()
def adapt_asset_materials(
    paths: list[str] | None = None,
    reference: str | None = None,
    fields: list[str] | None = None,
    mode: str = "preview",
    plan_id: str | None = None,
    selected: list[str] | None = None,
) -> dict:
    """Preview a reference look on Unity prefabs or UE static meshes; selectively apply/undo
        material slots.

    Reference can be a native material or model. Fields: color, roughness, texture_scale.
    Preview creates separate material/asset variants and real before/after renders. Inspect
    unsupported-field warnings; do not claim visual equality across different shaders.
    Apply uses selected row IDs, preserves geometry/textures, and refuses changed assignments.
    """
    from . import art_adaptation

    return art_adaptation.start(
        str(project()["project"]), paths, reference, fields, mode, plan_id, selected
    )


def main():
    from .intake import start_watcher

    if os.environ.get("PTS_COMPACT_TOOLS") == "1":

        @mcp._mcp_server.list_tools()
        async def compact_tools():
            return [
                tool
                for tool in await mcp.list_tools()
                if tool.name in {"game_workflow", "open_workbench", "workbench_action"}
            ]

    watcher = start_watcher()
    try:
        mcp.run(transport="stdio")
    finally:
        watcher.set()
        # SDK wrappers can close stdout during garbage collection after disconnect.
        # PyInstaller flushes it again during shutdown, so give that flush a live sink.
        if getattr(sys, "frozen", False):
            sys.stdout = sys.__stdout__ = open(os.devnull, "w")
