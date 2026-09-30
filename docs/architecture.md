# Architecture

```text
MCP-compatible AI client
  │ inspect_target / build_asset / publish_blend / get_asset_status
  ▼
Python MCP server + CLI
  │ runs background Blender with the AI-authored script
  ▼
Blender asset validator + FBX / PBR exporter
  │ atomic request, file hashes, stable asset ID
  ▼
Target editor adapter (polls the local project inbox)
  ├ Unity: FBX → Standard/URP materials → prefab → scene instance
  └ Unreal: FBX → Default Lit materials → Static Mesh → Actor
  ▼
Import receipt returned to the AI on its next status call
```

MCP uses stdio. No project-facing HTTP listener, cloud service or model API is required by this implementation. The AI client is separately responsible for its model connection and tool permissions. The destination is configured once with `PTS_PROJECT` and optional `PTS_ENGINE`. Legacy Unity configuration is retained. Blender execution and bounded status waits run outside the MCP event loop so other requests stay responsive.

The exporter uses native FBX geometry and an explicit small PBR manifest. A schema 2 envelope names the target engine and meter-based position unit. Stable ASCII export material IDs bridge different engine name-sanitization rules while editable source names are preserved. Unsupported Blender shader graphs fail validation instead of relying on a lossy automatic conversion.

Unity owns AssetDatabase mutations on its editor thread. Unreal owns native asset and level changes through a content-only editor Python plugin. It explicitly chooses the FBX factory, generates supported PBR graphs and uses tagged StaticMeshActors for revisions. Neither adapter modifies the other engine's project or silently saves the user's level.

Stable IDs, deterministic paths and receipts are the project's central contribution. Blender Python authors the mesh; the bridge handles the repeatable cross-application lifecycle.
