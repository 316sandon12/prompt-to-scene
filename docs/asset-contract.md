# Asset contract v2

The MCP client is the planner. Blender builds the asset. The target editor is the authority on whether an import actually succeeded.

## Blender inputs

- Create a collection named `Export`; all its mesh objects are exported.
- Work in meters, Blender Z-up. Ground props at Z=0 with a sensible origin.
- Static meshes only, 1–200,000 total triangles. Apply modifiers before publishing.
- Assign every material slot a node material. Connect Principled BSDF directly to the active Material Output.
- Use opaque materials: alpha=1, transmission/coat/subsurface/sheen/anisotropy=0, no emission.
- Keep IOR=1.5, Specular IOR Level=0.5 and Specular Tint white. No volume or shader displacement.
- Metallic and roughness are scalar constants in [0,1] or direct Non-Color image textures. Base color is scene-linear RGBA.
- Base color can be a direct sRGB Image Texture. Normals can be a Non-Color Image Texture through a tangent-space Normal Map node.
- Textured meshes need exactly one UV map. Connect the Image Texture's Color output; use default UV coordinates, flat projection, linear filtering and repeat. Texture transforms and named UV overrides are unsupported.
- No rigs, shape keys, animation, unbaked procedural texture nodes, HDRP-specific features or transparent surfaces. Recipes bake their surfaces before validation; import_asset additionally bakes common opaque Principled PBR inputs. This final transport contract stays strict.

`build_asset` starts from Blender factory startup. Delete its default objects in your script. A script must fully construct the asset on each invocation. `publish_blend` opens a saved file without overwriting it; save changes in your other Blender tool first.

## Transport

All work is rooted at the explicitly configured Unity or Unreal project:

```text
.prompt-to-scene/
  work/<asset_id>/<request_id>/
    model.py          # original AI/user script
    blender_*.py      # exact retained export/recipe/surface/preview drivers
    asset.json        # recipe and source metadata
    report.json       # geometry/material/UV/budget checks and per-part hashes
    studio.png        # actual Blender source views
    front.png
    back.png
    original.blend    # retained pre-preparation source, when prepared
    before.png        # aligned source view for external assets
    source.blend      # editable prepared source revision
    lod_1.fbx         # optional; up to three reduced levels
    model.fbx
    tex_<hash>.png    # optional normalized image files
    export.json
    blender.log
  art-direction.json
  studies/<study_id>.json
  inbox/<asset_id>.json
  receipts/<asset_id>.json
  editor.json
```

The Python server completes Blender export, hashes transfer files, then atomically publishes the request. A per-asset build lock prevents concurrent writers. The editor validates the schema, path/asset identity, transfer names, file hashes and material references before copying into Assets. A queued request cannot be replaced until the editor processes it.

`schema_version=2`. `target_engine` is `unity` or `unreal`; `position_unit` is `meters`. Adapters reject requests for the wrong engine/units before importing. `asset_id` matches `[a-z][a-z0-9_-]{0,63}`. `request_id` is a 32-character lowercase UUID hex. `work_dir` must equal `work/<asset_id>/<request_id>`.

Position uses the target engine's XYZ axes in meters: Unity Y-up, Unreal Z-up. The Unreal adapter multiplies positions by 100 for editor centimeters and converts FBX scene units/axes. Receipt `bounds_size` values are in meters (`bounds_unit=meters`) for both adapters.

Every material has its original `name` and an `fbx_name` of `PTS_` plus the first 16 lowercase hex characters of SHA-256 over the UTF-8 original name. Source `.blend` files retain the original names; the FBX uses these ASCII identities so engine name sanitization cannot disconnect material slots.

The current Unity package also accepts existing schema 1 requests (Unity-only, no FBX alias). The v0.1 package cannot consume schema 2 requests: update both server and package together. The Unreal adapter accepts schema 2 only.

## Optional v0.4 material fields

`roughness_texture`, `metallic_texture` and `mask_texture` contain transfer basenames or are empty. Every referenced file is included in the SHA-256 manifest. The Unity mask uses R=metallic, G=1, B=0, A=1−roughness and imports as linear data. UE uses the separate roughness/metallic images. These optional fields extend schema 2; update both adapters to consume them.

`reuse_path` optionally references an existing engine Material/MaterialInterface inside `Assets/` (Unity) or `/Game/` (UE). The adapter checks the path and object type, reuses it and does not update its properties. A missing or incompatible path fails the import. The source studio view uses recipe surfaces, so it does not reproduce arbitrary reused engine shaders.

## Optional v0.5 geometry fields

`lods` contains up to three entries with `file` (`lod_1.fbx` through `lod_3.fbx`, in order), positive `triangles` and strictly decreasing `screen_height` values between 0 and 1. Each FBX is included in the SHA-256 manifest. `model.fbx` is LOD0. Files use the same material aliases, units and axes. The new Unity adapter creates native LODGroup children; UE imports additional Static Mesh levels. Both clear obsolete generated levels on revision.

`collision_mode` is `none`, `box` or `convex`; `collider=false` always disables it. Missing mode preserves old box behavior. UE primitive and convex counts use separate APIs; `collision_count` reports their sum, and warnings disclose a 26-DOP convex fallback if decomposition produces no hulls. Source metadata includes preparation settings, measured reductions, LOD counts and provenance. Update both server and bridge: older schema-2 adapters do not know LOD file names.

External intake allows at most two million source triangles and 256 MiB per local model. Provider packages are bounded to 100 files / 512 MiB. Final export remains at most 200,000 triangles and 20 materials. Supported external materials must have a direct opaque Principled surface; shader displacement, mixed surfaces, unsupported lobes, emission and missing textures fail before import. Simplification error is sampled bidirectionally and does not certify all geometry or texture quality.

## Success semantics

The editor writes `imported` only after native import, material mapping, prefab/mesh creation or update, and placement in the active scene/level. Receipts identify the request and include engine-native identity, triangle counts, asset bounds and scene path. Unity returns prefab GUIDs; Unreal returns Static Mesh paths and Actor GUIDs. A blank Unity scene path means the active scene has not been saved.

Preview-only candidate builds end with `completed` and never enter the inbox. They are source drafts, not imported assets. `choose_variant` creates the final normal import request.

`queued` is not success. Pass `request_id` to `get_asset_status` and optionally `wait_seconds` (0–30). A mismatched current revision returns `superseded`; a timeout leaves the real queued/unknown status with `wait_timed_out=true`. `error` includes the editor exception. Import is not a full transaction: a mid-import engine error can leave partially updated assets. Repair the input and rebuild the same ID; use version control for restoration.

## Ownership on revisions

Stable asset ID + stable material names preserve imported asset paths and their Unity metadata. Prefab root components and existing instance transforms survive. The generated `Visual` subtree is replaced; do not attach user scripts or scene overrides there. Generated root BoxCollider / Visual convex colliders, LODGroup and mapped material properties belong to the bridge. Extra old textures/materials are retained for reference safety.

Each active scene gets at most one automatically placed instance for an asset if none already exists; manually duplicated instances are not deleted. Position is used only for first placement. `inspect_scene` reports actual selection; `edit_scene` modifies native instances and `arrange_props` manages contextual placement/copies with undo.

Unreal combines the exported meshes and updates the same native Static Mesh path. Existing StaticMeshActors tagged `PTS.Asset:<id>` in the current level are reused. Their GUIDs, transforms, labels and user tags survive. Generated mesh geometry, simple collision and material graphs are bridge-owned. Explicit component material overrides remain the user's responsibility. Levels/scenes are not saved automatically.
