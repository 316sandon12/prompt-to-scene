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
Unity editor package (polls local project inbox)
  │ import → material mapping → prefab → scene instance
  ▼
Import receipt returned to the AI on its next status call
```

MCP uses stdio. No project-facing HTTP listener, cloud service or model API is required by this implementation. The AI client is separately responsible for its model connection and tool permissions. The Unity destination is configured once with `PTS_UNITY_PROJECT`, rather than selected from arbitrary model-generated paths on every request.

The v0.1 exporter uses native FBX for geometry and an explicit small PBR manifest. This avoids requiring a glTF Unity package and makes supported material conversion deliberate. It does not claim to translate arbitrary Blender shader graphs. The transport can accept a future glTF exporter or UE adapter without changing the user's conversational workflow.

Stable IDs, deterministic paths and receipts are the project's central contribution. Blender Python authors the mesh; the bridge handles the repeatable cross-application lifecycle.
