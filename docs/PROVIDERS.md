# Optional generation providers

Prompt-to-Scene v0.6 adapts generation services into the same retained-source, static opaque PBR preparation pipeline as file imports. The core library and Blender scripting do not require a service.

## Configure

Open the local **创作台 → 生成 → 配置可选生成服务**. Choose Meshy or self-hosted (`local`); enter the base URL for a self-hosted adapter and an optional API key. macOS stores keys in Keychain and Windows in Credential Manager. No key is stored in the project, JSON configuration, MCP arguments or receipts. Environment overrides are `MESHY_API_KEY` and `PTS_LOCAL_API_KEY`. Linux uses those environment variables.

Endpoints are saved under `PTS_HOME/providers.json`. Plain HTTP is accepted only on loopback. HTTPS self-hosted endpoints can be remote and receive the request's prompt/images. Local file imports, recipes and Blender scripts never call these services. AI-host data handling remains governed by that host.

## Meshy

The adapter follows the official [text-to-3D](https://docs.meshy.ai/en/api/text-to-3d), [image-to-3D](https://docs.meshy.ai/en/api/image-to-3d), and [multi-image-to-3D](https://docs.meshy.ai/en/api/multi-image-to-3d) endpoints:

- Text: `/openapi/v2/text-to-3d`, preview followed by refine with PBR enabled.
- One image: `/openapi/v1/image-to-3d`; 2–4 images: `/openapi/v1/multi-image-to-3d`.
- Reference images are PNG/JPEG data URIs, at most 8 MiB each. Text prompts are at most 800 characters. On the image routes, geometry follows images; the descriptive prompt is retained as provenance, not sent as an unsupported combined text/image parameter.
- Requests use `Authorization: Bearer …`, ask for GLB and keep provider task IDs. No deprecated model identifier is hard-coded; the service uses its current default.
- Downloads allow the HTTPS `assets.meshy.ai` / `cdn.meshy.ai` hosts. API redirects are rejected and download redirects are revalidated.

`generate_model(provider="meshy", allow_paid=true)` requires user authorization covering the provider and candidate count. Preview+refine may consume multiple provider operations per text candidate. Do not assume a fixed price. No live paid Meshy generation was performed for this release; request/state behavior is contract-tested. The self-hosted fixture was exercised through real Blender and native editors, which verifies the integration, not AI model quality.

## Self-hosted adapter contract

Run your own adapter in front of the generation model you choose. The plugin does not bundle inference weights, GPU runtimes or an adapter for every model API. Use a base URL such as `http://127.0.0.1:7860`. Optional Bearer authentication applies to JSON API requests; download URLs should be authorized by a short-lived signed URL if required (the plugin never forwards API credentials to a model download).

`POST /jobs` receives:

```json
{"prompt":"A small weathered wood stool","images":[],"format":"glb","candidate":0}
```

`images` contains zero to four PNG/JPEG data URIs. `candidate` is zero-based. Each requested candidate is a separate job. Respond with HTTP 200/201 and:

```json
{"id":"job_123"}
```

The ID must match `[A-Za-z0-9_-]{1,100}`. `GET /jobs/job_123` can return:

```json
{"status":"RUNNING","progress":45}
```

or:

```json
{"status":"SUCCEEDED","model_url":"http://127.0.0.1:7860/files/job_123.glb"}
```

`COMPLETED` is also accepted. Failure states are `FAILED`, `CANCELED`, `CANCELLED`. Downloads must stay on the configured origin and contain a GLB 2 file with embedded dependencies, at most 256 MiB. JSON responses are capped at 8 MiB. The usual preparation limitations apply: no rigs, animation, transparent/mixed shaders or unbounded mesh sizes.

## Persistence and cancellation

The worker saves a submission marker before POST and a returned ID immediately afterward. On resume, saved IDs are polled rather than resubmitted. An ambiguous POST outcome is intentionally not retried: reconcile it in the provider dashboard first. Download and preparation stages are persisted independently. The provider may continue after local cancellation; this adapter does not claim to cancel or refund a remote operation.

Preview candidates are isolated builds. Use their `asset_id` and build `request_id` with `get_studio_preview` and `publish_prepared`. Use the enclosing generation workflow ID for `get_task_status`, `cancel_task` and `resume_workflow`.

A local transport fixture lives in `tools/workbench_checks.py`; it serves a known GLB to exercise the entire pipeline and is explicitly not a model-generation implementation.
