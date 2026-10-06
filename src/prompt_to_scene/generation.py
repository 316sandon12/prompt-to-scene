"""Optional Meshy and self-hosted adapters feeding the existing asset preparation pipeline."""

import base64
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from . import background, core, credentials, preparation, registry, sources, styles, workflow


def config():
    return core.read_optional_json(registry.home() / "providers.json") or {}


def configure(provider, endpoint=None, api_key=None):
    if provider not in {"meshy", "local"}:
        raise ValueError("Choose meshy or local")
    data = config()
    if provider == "local":
        parsed = urlsplit(endpoint or "")
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use a provider HTTP(S) base URL without embedded credentials")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Plain HTTP is supported only for a loopback generation server")
        data[provider] = {"endpoint": endpoint.rstrip("/")}
    else:
        data[provider] = {"endpoint": "https://api.meshy.ai"}
    if api_key:
        credentials.put(provider, api_key)
    core.atomic_json(registry.home() / "providers.json", data)
    return inventory()


def inventory():
    data = config()
    return [
        {
            "provider": name,
            "configured": bool(credentials.get(name)) if name == "meshy" else name in data,
            "endpoint": "https://api.meshy.ai"
            if name == "meshy"
            else data.get(name, {}).get("endpoint"),
            "paid_service": name == "meshy",
        }
        for name in ("meshy", "local")
    ]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Provider API redirects are not accepted")


def validate_glb(path, size):
    with path.open("rb") as handle:
        header = handle.read(20)
        if (
            len(header) != 20
            or header[:4] != b"glTF"
            or int.from_bytes(header[4:8], "little") != 2
            or int.from_bytes(header[8:12], "little") != size
            or header[16:20] != b"JSON"
        ):
            raise ValueError("Provider must return a GLB 2 model")
        length = int.from_bytes(header[12:16], "little")
        if not 0 < length <= min(size - 20, 8 * 1024**2):
            raise ValueError("Generated GLB metadata is invalid or too large")
        data = json.loads(handle.read(length))
    if not isinstance(data, dict):
        raise ValueError("Invalid GLB metadata")
    for name in ("buffers", "images"):
        for item in data.get(name, []):
            uri = item.get("uri")
            if uri is not None and (not isinstance(uri, str) or not uri.startswith("data:")):
                raise ValueError("Generated GLB must embed every buffer and image dependency")


class Adapter:
    def __init__(self, name):
        self.name = name
        self.endpoint = (
            "https://api.meshy.ai" if name == "meshy" else config().get("local", {}).get("endpoint")
        )
        self.key = credentials.get(name)
        if not self.endpoint or (name == "meshy" and not self.key):
            raise ValueError("Configure this provider in the workshop first")

    def request(self, path, payload=None):
        headers = {"Content-Type": "application/json", "User-Agent": "PromptToScene/0.6"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        request = urllib.request.Request(
            self.endpoint + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
        )
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=45) as response:
                content = response.read(8 * 1024**2 + 1)
                if len(content) > 8 * 1024**2:
                    raise ValueError("Provider response too large")
                return json.loads(content)
        except urllib.error.HTTPError as error:
            raise RuntimeError("Generation provider returned HTTP " + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError(
                "Could not reach generation provider; check its endpoint and resume"
            ) from None

    def url(self, value):
        parsed = urlsplit(value)
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("Invalid model download URL")
        if self.name == "meshy":
            valid = (
                parsed.scheme == "https"
                and parsed.hostname in {"assets.meshy.ai", "cdn.meshy.ai"}
                and parsed.port in {None, 443}
            )
        else:
            base = urlsplit(self.endpoint)
            valid = (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc)
        if not valid:
            raise ValueError("Model URL is outside the configured provider")
        return value

    def download(self, url, destination, job):
        adapter = self

        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return super().redirect_request(req, fp, code, msg, headers, adapter.url(newurl))

        request = urllib.request.Request(self.url(url), headers={"User-Agent": "PromptToScene/0.6"})
        temporary = destination.with_suffix(".partial")
        total = 0
        try:
            with (
                urllib.request.build_opener(Redirect).open(request, timeout=45) as response,
                temporary.open("wb") as stream,
            ):
                self.url(response.url)
                while chunk := response.read(256 * 1024):
                    job.check()
                    total += len(chunk)
                    if total > sources.MAX_FILE:
                        raise ValueError("Generated model exceeds 256 MiB")
                    stream.write(chunk)
            validate_glb(temporary, total)
            temporary.replace(destination)
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError("Generated model download failed; resume to retry") from None
        finally:
            temporary.unlink(missing_ok=True)


def submit(
    project,
    asset_id,
    prompt,
    provider="local",
    image_paths=None,
    candidate_count=1,
    preview_only=True,
    allow_paid=False,
    settings=None,
    position=None,
):
    core.asset_id(asset_id)
    if provider not in {"meshy", "local"}:
        raise ValueError("Choose a configured generation provider")
    if provider == "meshy" and not allow_paid:
        raise ValueError(
            "Meshy uses provider credits. Set allow_paid only when the user requested "
            "this provider."
        )
    if type(allow_paid) is not bool or type(preview_only) is not bool:
        raise ValueError("Generation flags must be booleans")
    if image_paths is not None and (
        not isinstance(image_paths, list) or any(not isinstance(p, str) for p in image_paths)
    ):
        raise ValueError("Reference paths must be a list of filenames")
    Adapter(provider)
    if type(candidate_count) is not int or not 1 <= candidate_count <= 3:
        raise ValueError("Choose one to three candidates")
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 800:
        raise ValueError("Describe the model in 1 to 800 characters")
    images = []
    if len(image_paths or []) > 4:
        raise ValueError("Use at most four reference images")
    for filename in image_paths or []:
        path = Path(filename).expanduser().resolve()
        if (
            not path.is_file()
            or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}
            or path.stat().st_size > 8 * 1024**2
        ):
            raise ValueError("Reference images must be PNG/JPEG files up to 8 MiB")
        images.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    from . import project_profiles

    config = preparation.options(
        project_profiles.preparation_defaults(project, settings), styles.read(project)["quality"]
    )
    if position is not None:
        core.position_values(position)
    return background.submit(
        project,
        "generation",
        dict(
            asset_id=asset_id,
            prompt=prompt,
            provider=provider,
            images=images,
            candidate_count=candidate_count,
            preview_only=preview_only,
            settings=config,
            position=position,
        ),
        asset_id,
    )


def run(job, asset_id, prompt, provider, images, candidate_count, preview_only, settings, position):
    adapter = Adapter(provider)
    encoded = []
    for image in images:
        path = Path(image["path"])
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != image["sha256"]:
            raise ValueError("A reference image changed after submission")
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        encoded.append("data:" + mime + ";base64," + base64.b64encode(content).decode())
    rows = job.state.get("candidates") or [{} for _ in range(candidate_count)]
    job.update(candidates=rows)

    def phase(row, key, endpoint, payload):
        if not row.get(key):
            if row.get(key + "_submitting"):
                raise RuntimeError(
                    "Provider submission outcome is unknown; check the provider dashboard "
                    "before creating another paid task"
                )
            row[key + "_submitting"] = True
            job.update(candidates=rows, stage="Submitting generation")
            response = adapter.request(endpoint, payload)
            task_id = response.get("result") if provider == "meshy" else response.get("id")
            if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", task_id):
                raise ValueError("Provider returned an invalid task ID")
            row[key] = task_id
            job.update(candidates=rows)
        for _ in range(1200):
            job.check()
            result = adapter.request(endpoint + "/" + row[key])
            status = str(result.get("status", "")).upper()
            job.update(
                stage="Generating candidate " + str(rows.index(row) + 1),
                provider_progress=result.get("progress"),
            )
            if status in {"SUCCEEDED", "COMPLETED"}:
                return result
            if status in {"FAILED", "CANCELED", "CANCELLED"}:
                raise RuntimeError(
                    "Provider generation " + status.lower() + "; inspect its dashboard"
                )
            time.sleep(2)
        raise TimeoutError(
            "Provider is still running; resume this task to continue polling its saved ID"
        )

    for index, row in enumerate(rows):
        job.check()
        if not row.get("downloaded"):
            if provider == "meshy":
                if encoded:
                    endpoint = "/openapi/v1/" + (
                        "multi-image-to-3d" if len(encoded) > 1 else "image-to-3d"
                    )
                    payload = {
                        "image_urls" if len(encoded) > 1 else "image_url": encoded
                        if len(encoded) > 1
                        else encoded[0],
                        "enable_pbr": True,
                        "target_formats": ["glb"],
                    }
                    result = phase(row, "model_task", endpoint, payload)
                else:
                    endpoint = "/openapi/v2/text-to-3d"
                    phase(
                        row,
                        "preview_task",
                        endpoint,
                        {"mode": "preview", "prompt": prompt, "target_formats": ["glb"]},
                    )
                    result = phase(
                        row,
                        "model_task",
                        endpoint,
                        {
                            "mode": "refine",
                            "preview_task_id": row["preview_task"],
                            "enable_pbr": True,
                            "target_formats": ["glb"],
                        },
                    )
                url = result.get("model_urls", {}).get("glb")
            else:
                result = phase(
                    row,
                    "model_task",
                    "/jobs",
                    {"prompt": prompt, "images": encoded, "format": "glb", "candidate": index},
                )
                url = result.get("model_url")
            if not isinstance(url, str):
                raise ValueError("Provider did not return a GLB URL")
            destination = job.path.parent / ("candidate_" + str(index) + ".glb")
            job.update(stage="Downloading generated GLB")
            adapter.download(url, destination, job)
            row["downloaded"] = str(destination)
            job.update(candidates=rows)
        if not row.get("asset_task"):
            name = asset_id if candidate_count == 1 else asset_id[:59] + "_c" + str(index + 1)
            source = sources.validate_source({"path": row["downloaded"]})
            row["asset_task"] = workflow.submit(
                job.project,
                name,
                "",
                position,
                settings["collision"] != "none",
                source=source,
                preparation=settings,
                preview_only=preview_only,
                provenance={
                    "provider": provider,
                    "provider_task_id": row["model_task"],
                    "prompt": prompt,
                    "license": "provider-and-user-terms",
                    "sha256": source["sha256"],
                },
            )
            job.update(candidates=rows, stage="Preparing generated asset")
        row["result"] = job.wait(row["asset_task"])
        job.update(candidates=rows)
    return {
        "stage": "Candidates ready" if preview_only else "Generated assets imported",
        "candidates": rows,
        "preview_only": preview_only,
        "message": "Choose a candidate with publish_prepared"
        if preview_only
        else "Verified engine imports",
    }
