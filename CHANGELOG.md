# Changelog

## Unreleased — Game art direction

- Evidence-backed style matching: the connected host sees actual native thumbnails/reference images, infers shape/material/detail language, and saves numeric palette, roughness and shape defaults. Keep existing defaults when confidence is low; reject changed image evidence. No extra vision API is invoked.
- Persistent gameplay/world/camera context and asset design snapshots shared by Codex and Harness. Detailed requests route to custom Blender modeling, with explicit recipe selection for simple forms and automatic preparation for designed custom builds.
- Recipe joinery, framed doors, formed crests, handles/hinges, turned feet, repair plates and mechanical details. Directional wood grain follows each piece; baking caches track the grain attribute.
- Explicit redesign retains independent geometry/material locks. Provider prompts use saved context within the existing limit and expose compacted fields. Image-only provider routes remain explicit.
- Workbench context controls, 68 MCP tools and a reproducible same-camera Blender comparison. Native adapters are unchanged; this source update is not yet in the v0.9.1 portable apps.

## 0.8.0 — 2026-10-04

- Project asset naming and classification for Unity and UE: native type inventory, type/source folders, stable prefixes, texture-channel suffixes, collision numbering, exclusions and semantic name overrides.
- Preview every original/destination path before applying. Use native Unity GUID-preserving moves and a single UE rename batch for related assets, with stale-plan, dirty-asset, identity and destination preflight checks.
- Persistent journals, cooperative cancellation with recovery, restart-safe undo and migration of library tags, notes and provenance. Occupied original paths stop undo without overwriting newer content.
- Preserve scripts, scenes, special loading folders, Addressables/AssetBundle addresses, managed content and retained material-reuse paths. Incomplete 20,000-entry scans require a narrower scope.
- Workbench Organize tab with side-by-side path comparisons, pagination and history. One `organize_project_assets` tool exposes scan/plan/inspect/apply/undo/history to both hosts; 58 tools total.
- Real Unity Built-in/URP and UE tests cover collisions, stale plans, reference preservation across editor restart, repeated application, no-op reorganization and occupied-path undo rejection.

Update the app, host plugin and engine bridge together. Naming uses filenames, native types and explicit overrides; it does not perform visual semantic recognition. Custom code/config path strings are not rewritten. Undo restores resource names/locations, not resource contents or the entire project.

## 0.7.0 — 2026-10-03

- Door/chest/pickup templates with retained Blender source, beveled geometry, baked wood PBR, separate moving meshes, native Unity interaction components and reusable UE child Blueprints. No user C++ compilation.
- Preserve interaction settings, custom material assignments and root attachment points across regeneration. Canonical slot preflight rejects incompatible imports; moving parts update without loose duplicate instances.
- Four scene looks with native lighting, sky, color grading, a fixed comparison camera and restoration of saved lighting state.
- Room/corridor/stair blockouts with connected ports, dimension checks, staged replacement and native sampled player capsule clearance.
- Real Play/PIE checks for interaction range, events, geometry movement, closing, pickup, clearance, screenshots, runtime errors and measured frame intervals. Automatic return to Edit mode and cooperative cancellation.
- Local project asset indexing, keyword/size ranking, native thumbnails, original-reference placement and source/license annotations.
- Workbench gameplay/level/library tabs, native action task cards and 57 MCP tools shared by Codex and DeepSeek Harness.

Update the app, host plugin and engine bridge together. UE's content template was saved with 5.7.2; older UE asset compatibility is unverified. Templates do not implement arbitrary game logic, networking or inventory. Blockouts do not generate NavMesh. Play frame samples are editor measurements, not shipping-platform benchmarks.

## 0.6.0 — 2026-10-01

- Unified local/MCP App workbench, furnished scene kits and saved layouts, art-reference review with bounded repairs, external part editing and bake reuse, usage presets and optional Meshy/self-hosted generation. See the v0.6 verification record for host/editor/package evidence.

## 0.5.0 — 2026-09-30

- Local GLB/glTF, FBX and Blender intake; Poly Haven CC0 search, credited downloads, bounded dependency packages and retained provenance.
- Retained original files, dimension/axis normalization, seam-aware simplification and bidirectional sampled geometry checks. Failed budgets queue no import.
- Common opaque PBR baking, source-to-reduced tangent normals, original/prepared studio views and optional preview-before-publication.
- Real reduced FBX levels mapped to Unity LODGroup and UE native Static Mesh LODs. Convex/box/none collision, with an explicit native 26-DOP fallback when UE decomposition produces no hulls. Reimport removes obsolete LOD/collision configuration.
- Three matching kits and stronger structural variants for all nine recipes; selected-asset part editing and persisted native before/after camera comparisons.
- Workshop controls, shared client instructions and 34 MCP tools, including import/search/prepare/publish, kits, selected edits and review capture.

Update the core, client plugin and engine bridge together. Saved source revisions remain restorable. Revising older recipes adopts the updated structures; review before publishing substantial design changes. These tools prepare static opaque assets; they do not integrate a paid text-to-3D service.

## 0.4.0 — 2026-09-30

- Persistent project art direction: three palettes/styles, quality budgets, reference recipe adoption and read-only binding to existing engine materials.
- Nine designed prop recipes with structural alternatives, semantic parts, supports, bevels and hardware.
- UV preparation and real Cycles baking of curated wood/metal/paint/stone into base-color, roughness, metallic and tangent-normal maps; Unity metallic/smoothness packing and UE data-texture mapping.
- Independent semantic geometry/material edits and locks retained through shared recipe revisions.
- Real scene bounds and anchor-based around/along/under/right/front layouts, conservative overlap checks, fit-under scaling, native instances and persistent layout undo.
- Two/three isolated 3D candidate drafts, consistent studio/front/back renders, and selected-candidate final baking/import.
- A local creation workshop and 26 MCP tools shared by Codex and DeepSeek Harness.
- Two Blender worker slots per project, retained build drivers for detached portable workers, and source/report access.
- Avoid reverse DNS during local setup launch; use a read-only Windows process probe instead of `os.kill(pid, 0)`.
- Expanded real Blender/native editor checks and a full authoring guide.

Update the server, client plugin and engine bridge together. Existing saved sources remain restorable; revising v0.3 recipes adopts the new geometry designs. Baking covers curated recipe surfaces, and layouts use world-axis bounds with existing orientation. Static opaque assets remain the scope.

## 0.3.0 — 2026-09-30

- Portable setup app: project/Blender discovery, native pickers, bridge installation with backups, local dashboard and bundled Python.
- Native Codex plugin/skill and DeepSeek Harness bundle installation; shared project/source records across clients.
- Background Blender tasks with exact-request status, cancellation and bounded repair instructions.
- Parameterized crate/table/chair/sign creation and parameter-preserving revisions.
- Grounded placement, actual selection inspection, native transforms and isolated material tint with edit undo.
- Real engine PNG previews and restoration of successful source revisions.
- Preserve collider settings and tool-created instance tints through asset regeneration/restoration.
- Fix UE's repeated in-session FBX pipeline switching and verify stored material parameters despite its false setter return.
- Beginner download path, client/engine reproduction tools, automated portable builds and expanded tests.


## 0.2.0 — 2026-09-30

- Add Unreal Editor adapter: native combined Static Mesh, opaque PBR materials, texture import, optional box collision and automatic Actor placement.
- Preserve Unreal asset paths, Actor GUIDs, transforms, labels and user tags during geometry/material revisions.
- Convert meters to Unreal centimeters and Blender tangent normal maps to Unreal's convention.
- Add explicit engine routing and schema 2 requests; retain legacy Unity environment settings and schema 1 consumption in the updated Unity package.
- Use stable ASCII material-slot IDs to handle names with spaces, punctuation and Unicode.
- Add exact-request waiting, stale-revision detection, heartbeat freshness and non-blocking MCP build execution.
- Add Unreal engine smoke tests and a live MCP → Blender → editor-watcher verification script.

Update the Python server and engine adapter together. Static opaque props remain the supported scope; no rigs, procedural baking or Blueprint generation.

## 0.1.0 — 2026-09-30

First experimental release of the Blender → Unity workflow.

- MCP tools and CLI to build a static prop or publish a saved `.blend`.
- Validated FBX geometry and explicit opaque PBR material transfer.
- Unity Built-in/URP materials, prefab creation, scene placement and optional box collider.
- Stable asset IDs, revision updates and request-matched import receipts.
- Original procedural examples, real Blender/Unity smoke tests and bilingual setup documentation.

Unreal Engine, arbitrary material graphs, procedural texture baking, rigs and animation are not implemented in this release.
