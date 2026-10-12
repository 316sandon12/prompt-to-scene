"""Optional Images API adapter. Host-generated files need no second API or credentials."""

import base64
import binascii
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from . import core, credentials, registry
from .generation import NoRedirect


def config():
    return core.read_optional_json(registry.home() / "image-provider.json") or {}


def validate(data):
    parsed = urlsplit(data.get("endpoint", ""))
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Configure an HTTP(S) image API base URL without credentials/query/fragment"
        )
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Plain HTTP is allowed only for a local image server")
    if not isinstance(data.get("model"), str) or not 1 <= len(data["model"].strip()) <= 160:
        raise ValueError("Configure the image model supported by your provider")
    if data.get("api_style") not in {"gpt_image", "b64_json"}:
        raise ValueError("Use gpt_image or b64_json API style")
    if data.get("size") not in {"auto", "1024x1024", "1536x1024", "1024x1536"}:
        raise ValueError("Choose auto or a supported generation size; final game size is separate")
    return data


def remote(data):
    return urlsplit(data["endpoint"]).hostname not in {"127.0.0.1", "localhost", "::1"}


def key_for(data):
    return credentials.get("image") if data.get("use_key", True) else None


def configure(
    project=None, endpoint=None, model=None, api_key=None, api_style="gpt_image", size="auto"
):
    """Read/configure a local or remote Images API; keys stay in the OS credential store.

    endpoint includes /v1. gpt_image supports reference edits and alpha; b64_json is text-only.
    A configured key is not spending authorization. Use PTS_IMAGE_API_KEY in headless setups.
    """
    if endpoint is None and model is None and api_key is None:
        data = config()
        return {**data, "configured": bool(data), "has_key": bool(key_for(data))}
    data = validate(
        dict(
            endpoint=(endpoint or "").rstrip("/"),
            model=(model or "").strip(),
            api_style=api_style,
            size=size,
        )
    )
    if api_key:
        credentials.put("image", api_key)
    previous = config()
    data["use_key"] = bool(api_key) or (
        (not previous or previous["endpoint"] == data["endpoint"]) and previous.get("use_key", True)
    )
    core.atomic_json(registry.home() / "image-provider.json", data)
    return {**data, "configured": True, "has_key": bool(key_for(data))}


def request(data, design):
    from . import image_assets

    validate(data)
    if data != config():
        raise ValueError(
            "Image provider settings changed; explicitly start a task with the new provider"
        )
    body = dict(model=data["model"], prompt=design["effective_prompt"], n=1)
    settings = design["settings"]
    size = data["size"]
    if data["api_style"] == "b64_json":
        if design["references"]:
            raise ValueError(
                "This adapter is text-only; use gpt_image or the host image tool for references"
            )
        body["response_format"] = "b64_json"
        if size == "auto":
            size = "1024x1024"
    else:
        body.update(
            background="transparent" if settings["transparent"] else "opaque", output_format="png"
        )
    body["size"] = size
    headers = {"User-Agent": "PromptToScene-Images", "Content-Type": "application/json"}
    key = key_for(data)
    if key:
        headers["Authorization"] = "Bearer " + key
    endpoint = data["endpoint"] + "/images/generations"
    if design["references"]:
        boundary = "pts" + uuid.uuid4().hex
        chunks = []
        for name, value in body.items():
            chunks.append(
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                    f"\r\n\r\n{value}\r\n"
                ).encode()
            )
        for index, reference in enumerate(design["references"]):
            image = Path(reference["path"]).read_bytes()
            if image_assets.digest(image) != reference["sha256"]:
                raise ValueError("Reference image changed; create a new image plan")
            image_assets.decode(image)
            chunks.extend(
                [
                    (
                        f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; '
                        f'filename="reference_{index}.png"\r\nContent-Type: image/png\r\n\r\n'
                    ).encode(),
                    image,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode())
        payload = b"".join(chunks)
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
        endpoint = data["endpoint"] + "/images/edits"
    else:
        payload = json.dumps(body).encode()
    request = urllib.request.Request(endpoint, data=payload, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=180) as response:
            content = response.read(30 * 1024**2 + 1)
            if len(content) > 30 * 1024**2:
                raise ValueError("Image API response exceeds 30 MiB")
            result = json.loads(content)
        encoded = result.get("data", [{}])[0].get("b64_json")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError(
                "Image API must return data[0].b64_json; URL downloads are not supported"
            )
        return base64.b64decode(encoded, validate=True)
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            "Image API returned HTTP "
            + str(error.code)
            + "; check model, permissions and provider settings"
        ) from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError(
            "Image API connection failed/timed out. The outcome may be unknown; "
            "automatic retries are disabled to avoid duplicate charges."
        ) from None
    except (json.JSONDecodeError, binascii.Error, IndexError, AttributeError, TypeError):
        raise ValueError("Image API returned an invalid base64 image response") from None
