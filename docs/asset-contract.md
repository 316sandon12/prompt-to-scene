# Asset contract v2

The MCP client is the planner. Blender builds the asset. The target editor is the authority on whether an import actually succeeded.

## Blender inputs

- Create a collection named `Export`; all its mesh objects are exported.
- Work in meters, Blender Z-up. Ground props at Z=0 with a sensible origin.
- Static meshes only, 1–200,000 total triangles. Apply modifiers before publishing.
- Assign every material slot a node material. Connect Principled BSDF directly to the active Material Output.
- Use opaque materials: alpha=1, transmission/coat/subsurface/sheen/anisotropy=0, no emission.
- Keep IOR=1.5, Specular IOR Level=0.5 and Specular Tint white. No volume or shader displacement.
- Metallic and roughness are scalar constants in [0,1]. Base color is scene-linear RGBA.
- Base color can be a direct sRGB Image Texture. Normals can be a Non-Color Image Texture through a tangent-space Normal Map node.
- Textured meshes need exactly one UV map. Connect the Image Texture's Color output; use default UV coordinates, flat projection, linear filtering and repeat. Texture transforms and named UV overrides are unsupported.
- No rigs, shape keys, animation, procedural texture nodes, HDRP-specific features or transparent surfaces.

`build_asset` starts from Blender factory startup. Delete its default objects in your script. A script must fully construct the asset on each invocation. `publish_blend` opens a saved file without overwriting it; save changes in your other Blender tool first.

## Transport

All work is rooted at the explicitly configured Unity or Unreal project:

```text
.prompt-to-scene/
  work/<asset_id>/<request_id>/
    model.py          # original AI/user script
    source.blend      # editable source revision
    model.fbx
    tex_<hash>.png    # optional normalized image files
    export.json
    blender.log
  inbox/<asset_id>.json
  receipts/<asset_id>.json
  editor.json
```

The Python server completes Blender export, hashes transfer files, then atomically publishes the request. A per-asset build lock prevents concurrent writers. The editor validates the schema, path/asset identity, transfer names, file hashes and material references before copying into Assets. A queued request cannot be replaced until the editor processes it.

`schema_version=2`. `target_engine` is `unity` or `unreal`; `position_unit` is `meters`. Adapters reject requests for the wrong engine/units before importing. `asset_id` matches `[a-z][a-z0-9_-]{0,63}`. `request_id` is a 32-character lowercase UUID hex. `work_dir` must equal `work/<asset_id>/<request_id>`.

Position uses the target engine's XYZ axes in meters: Unity Y-up, Unreal Z-up. The Unreal adapter multiplies positions by 100 for editor centimeters and converts FBX scene units/axes. Receipt `bounds_size` values are in meters (`bounds_unit=meters`) for both adapters.

Every material has its original `name` and an `fbx_name` of `PTS_` plus the first 16 lowercase hex characters of SHA-256 over the UTF-8 original name. Source `.blend` files retain the original names; the FBX uses these ASCII identities so engine name sanitization cannot disconnect material slots.

The v0.3 Unity package also accepts existing schema 1 requests (Unity-only, no FBX alias). The v0.1 package cannot consume schema 2 requests: update both server and package together. The Unreal adapter accepts schema 2 only.

## Success semantics

The editor writes `imported` only after native import, material mapping, prefab/mesh creation or update, and placement in the active scene/level. Receipts identify the request and include engine-native identity, triangle counts, asset bounds and scene path. Unity returns prefab GUIDs; Unreal returns Static Mesh paths and Actor GUIDs. A blank Unity scene path means the active scene has not been saved.

`queued` is not success. Pass `request_id` to `get_asset_status` and optionally `wait_seconds` (0–30). A mismatched current revision returns `superseded`; a timeout leaves the real queued/unknown status with `wait_timed_out=true`. `error` includes the editor exception. Import is not a full transaction: a mid-import engine error can leave partially updated assets. Repair the input and rebuild the same ID; use version control for restoration.

## Ownership on revisions

Stable asset ID + stable material names preserve imported asset paths and their Unity metadata. Prefab root components and existing instance transforms survive. The generated `Visual` subtree is replaced; do not attach user scripts or scene overrides there. The root BoxCollider and mapped material properties belong to the bridge. Extra old textures/materials are retained for reference safety.

Each active scene gets at most one automatically placed instance for an asset if none already exists; manually duplicated instances are not deleted. Position is used only for first placement. This version has no general natural-language scene-selection or move command.

Unreal combines the exported meshes and updates the same native Static Mesh path. Existing StaticMeshActors tagged `PTS.Asset:<id>` in the current level are reused. Their GUIDs, transforms, labels and user tags survive. Generated mesh geometry, simple collision and material graphs are bridge-owned. Explicit component material overrides remain the user's responsibility. Levels/scenes are not saved automatically.
