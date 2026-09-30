# Asset contract v1

The MCP client is the planner. Blender builds the asset. Unity is the authority on whether an import actually succeeded.

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

All work is rooted at the explicitly configured Unity project:

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

`schema_version=1`. `asset_id` matches `[a-z][a-z0-9_-]{0,63}`. `request_id` is a 32-character lowercase UUID hex. Position is Unity XYZ in meters. `work_dir` must equal `work/<asset_id>/<request_id>`.

## Success semantics

The editor writes `imported` only after native import, material mapping, prefab creation/update and placement in the active scene. Receipts identify the exact request and include prefab GUID, geometry counts, asset bounds and scene path. A blank scene path means the active scene has not been saved.

`queued` is not success. Match `request_id` before reporting completion. `error` includes the editor exception. Import is not a full transaction: a mid-import engine error can leave partially updated Assets. Repair the input and rebuild the same asset ID; use version control for restoration.

## Ownership on revisions

Stable asset ID + stable material names preserve imported asset paths and their Unity metadata. Prefab root components and existing instance transforms survive. The generated `Visual` subtree is replaced; do not attach user scripts or scene overrides there. The root BoxCollider and mapped material properties belong to the bridge. Extra old textures/materials are retained for reference safety.

Each active scene gets at most one automatically placed instance for an asset if none already exists; manually duplicated instances are not deleted. Position is used only for first placement. This version has no general natural-language scene-selection or move command.
