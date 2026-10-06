"""Local assets and the credited Poly Haven catalog. Downloads run in persistent jobs."""

import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

from . import core, preparation, registry, styles, workflow

API = "https://api.polyhaven.com"
CREDIT = "Powered by Poly Haven"
HOSTS = {"api.polyhaven.com", "cdn.polyhaven.com", "dl.polyhaven.com", "dl.polyhaven.org"}
FORMATS = {".glb", ".gltf", ".fbx", ".blend"}
MAX_FILE = 256 * 1024 * 1024


def provider_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOSTS
        or parsed.port
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Only HTTPS files from Poly Haven are downloaded")
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, provider_url(newurl))


def fetch(url, limit=8 * 1024 * 1024, cancel=None):
    request = urllib.request.Request(
        provider_url(url),
        headers={
            "User-Agent": "PromptToScene/0.5 (https://github.com/316sandon12/prompt-to-scene)"
        },
    )
    chunks, total = [], 0
    with urllib.request.build_opener(Redirect).open(request, timeout=20) as response:
        provider_url(response.url)
        if int(response.headers.get("Content-Length", "0")) > limit:
            raise ValueError("Provider file exceeds the download limit")
        while chunk := response.read(256 * 1024):
            if cancel and cancel.exists():
                raise RuntimeError("Cancelled during download")
            total += len(chunk)
            if total > limit:
                raise ValueError("Provider file exceeds the download limit")
            chunks.append(chunk)
    return b"".join(chunks)


def slug(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("Choose a Poly Haven asset ID from search results")
    return value


def search(query="", limit=12, offset=0):
    if type(limit) is not int or not 1 <= limit <= 30 or type(offset) is not int or offset < 0:
        raise ValueError("Use limit 1..30 and a non-negative offset")
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("Search query is too long")
    path = registry.home() / "catalog/polyhaven-models.json"
    cached = core.read_optional_json(path)
    stale = False
    if not cached or time.time() - cached["time"] > 3600:
        try:
            cached = {"time": time.time(), "assets": json.loads(fetch(API + "/assets?type=models"))}
            core.atomic_json(path, cached)
        except (OSError, ValueError):
            if not cached:
                raise
            stale = True
    words = query.casefold().split()
    rows = []
    for key, data in cached["assets"].items():
        haystack = " ".join(
            [key, data.get("name", ""), *data.get("tags", []), *data.get("categories", [])]
        ).casefold()
        if all(word in haystack for word in words):
            rows.append(
                {
                    "id": key,
                    "name": data.get("name", key),
                    "provider": "polyhaven",
                    "license": "CC0-1.0",
                    "authors": list(data.get("authors", {})),
                    "triangles_hint": data.get("polycount"),
                    "url": "https://polyhaven.com/a/" + quote(key),
                    "thumbnail_url": data.get("thumbnail_url", ""),
                }
            )
    rows.sort(key=lambda row: (row["name"].casefold(), row["id"]))
    return {
        "assets": rows[offset : offset + limit],
        "total": len(rows),
        "next_offset": offset + limit if offset + limit < len(rows) else None,
        "credit": CREDIT,
        "catalog_cached": stale,
        "query_language": "English asset tags",
    }


def validate_source(source):
    if not isinstance(source, dict):
        raise ValueError("Source must describe a local path or a Poly Haven ID")
    if source.get("provider") == "polyhaven":
        return {"provider": "polyhaven", "id": slug(source.get("id"))}
    if source.get("provider", "local") != "local":
        raise ValueError("Supported providers: local, polyhaven")
    path = Path(source.get("path", "")).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in FORMATS:
        raise ValueError("Choose an existing GLB, glTF, FBX or .blend file")
    if path.stat().st_size > MAX_FILE:
        raise ValueError("Local model exceeds 256 MiB")
    return {
        "provider": "local",
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def submit(project, asset_id, source, settings=None, position=None, preview_only=False):
    from . import project_profiles

    settings = project_profiles.preparation_defaults(project, settings)
    source = validate_source(source)
    config = preparation.options(settings, styles.read(project)["quality"])
    return workflow.submit(
        project,
        asset_id,
        "",
        position,
        config["collision"] != "none",
        source=source,
        preparation=config,
        preview_only=preview_only,
    )


def safe_relative(name):
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
        or any(part.startswith(".") for part in path.parts)
    ):
        raise ValueError("Invalid provider dependency path")
    return path


def resolve(source, folder, cancel):
    """Retain downloaded dependencies and provenance; never modify the user's source."""
    if source["provider"] == "local":
        path = Path(source["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Source file changed after submission; submit the new revision")
        return path, {**source, "license": "user-supplied", "name": path.name}
    asset = slug(source["id"])
    data = json.loads(fetch(API + "/files/" + asset, cancel=cancel))
    # glTF contains explicit PBR connections and dependency paths. Prefer its 1k download;
    # final maps are baked to the project's chosen budget, not the provider's full resolution.
    entry = None
    for format_name in ("gltf", "blend", "fbx", "glb"):
        sizes = data.get(format_name, {})
        for size in ("1k", "2k"):
            formats = sizes.get(size, {})
            if format_name in formats and "url" in formats[format_name]:
                entry = formats[format_name]
                break
        if entry:
            break
    if entry is None:
        raise ValueError("This model has no supported 1k/2k download; choose another asset")
    files = [(Path(urlsplit(entry["url"]).path).name, entry)]
    files += list(entry.get("include", {}).items())
    if len(files) > 100 or sum(f.get("size", 0) for _, f in files) > 512 * 1024 * 1024:
        raise ValueError("Asset package exceeds the 512 MiB / 100-file limit")
    folder.mkdir(parents=True, exist_ok=True)
    checksums, total = {}, 0
    for name, item in files:
        destination = folder / safe_relative(name)
        content = fetch(item["url"], MAX_FILE, cancel)
        total += len(content)
        if total > 512 * 1024 * 1024:
            raise ValueError("Asset package exceeds 512 MiB")
        if item.get("md5") and hashlib.md5(content).hexdigest() != item["md5"]:
            raise ValueError("Provider checksum mismatch: " + name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        checksums[name] = hashlib.sha256(content).hexdigest()
    provenance = {
        "provider": "polyhaven",
        "id": asset,
        "license": "CC0-1.0",
        "url": "https://polyhaven.com/a/" + asset,
        "credit": CREDIT,
        "files": checksums,
    }
    core.atomic_json(folder / "provenance.json", provenance)
    return folder / files[0][0], provenance


def script(path):
    return (
        "import runpy\nfrom pathlib import Path\n"
        'runpy.run_path(str(Path(__file__).with_name("blender_ingest.py")))["load"]('
        + repr(str(path))
        + ")\n"
    )


def publish(project, asset_id, request_id):
    core.asset_id(asset_id)
    workflow.identifier(request_id)
    state = workflow.job_status(project, request_id)
    if (
        state.get("asset_id") != asset_id
        or state.get("status") != "completed"
        or not state.get("preview_only")
    ):
        raise ValueError("Choose a completed isolated prepared asset")
    root = core.state_root(registry.resolve(project).root)
    work = root / "work" / asset_id / request_id
    metadata = core.read_optional_json(work / "asset.json") or {}
    request = core.read_optional_json(work / "request.json") or {}
    return workflow.submit(
        project,
        asset_id,
        "",
        position=None if request.get("auto_place", True) else request.get("position"),
        blend_file=str(work / "source.blend"),
        collider=metadata.get("collider", True),
        recipe=metadata.get("recipe"),
        provenance=metadata.get("provenance"),
    )
