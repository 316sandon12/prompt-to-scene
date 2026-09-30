# Changelog

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
