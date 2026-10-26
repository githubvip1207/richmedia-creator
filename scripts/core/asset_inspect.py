"""只读检查素材，获取哈希及本地媒体信息。"""

from core import process
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from core.file_hash import sha256_file
from core.media_format import image_mime


def inspect_asset(asset):
    a = dict(asset)
    allowed = {"kind", "source", "role", "purpose", "metadata", "provenance"}
    if set(a) - allowed:
        raise ValueError("Unknown asset fields: " + str(sorted(set(a) - allowed)))
    if a.get("kind") not in ("image", "video", "audio"):
        raise ValueError("Asset kind must be image/video/audio")
    if not isinstance(a.get("purpose"), str) or not a["purpose"].strip():
        raise ValueError("Each asset needs a purpose")
    source = a.get("source", "")
    if not isinstance(source, str) or not source:
        raise ValueError("Each asset needs a source")
    a["metadata"] = dict(a.get("metadata", {}))
    parsed = urlparse(source)
    if parsed.scheme in ("https", "asset"):
        if parsed.scheme == "https" and (not parsed.hostname or parsed.username or parsed.password):
            raise ValueError("Invalid HTTPS asset URL")
        if parsed.scheme == "asset" and (not parsed.netloc):
            raise ValueError("Invalid asset:// ID")
        a["transport"] = parsed.scheme
        return a
    if parsed.scheme or not Path(source).is_absolute():
        raise ValueError("Use absolute local paths, HTTPS URLs or asset:// IDs; no inline Base64")
    path = Path(source).resolve(strict=True)
    if not path.is_file():
        raise ValueError("Asset must be a file")
    if a["kind"] == "video":
        raise ValueError(
            "Video API accepts HTTPS/asset://, not local video Base64. Upload to your approved storage first, then re-plan with its URL."
        )
    a["source"] = str(path)
    a["transport"] = "local-base64"
    a["sha256"] = sha256_file(path)
    a["metadata"]["bytes"] = path.stat().st_size
    mime = image_mime(path) if a["kind"] == "image" else mimetypes.guess_type(str(path))[0]
    if not mime or not mime.startswith(a["kind"] + "/"):
        raise ValueError("Unrecognized asset MIME type")
    a["metadata"]["mime"] = mime
    if shutil.which("ffprobe"):
        result = process.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode:
            raise ValueError("ffprobe could not decode local asset: " + path.name)
        probe = json.loads(result.stdout)
        stream = next(
            (
                s
                for s in probe.get("streams", [])
                if s.get("codec_type") == ("video" if a["kind"] == "image" else a["kind"])
            ),
            {},
        )
        if not stream:
            raise ValueError("ffprobe found no matching media stream: " + path.name)
        for k in ("width", "height"):
            if k in stream:
                a["metadata"][k] = stream[k]
        pixel_format = stream.get("pix_fmt", "")
        if a["kind"] == "image":
            a["metadata"]["has_alpha"] = pixel_format in (
                "rgba",
                "bgra",
                "argb",
                "abgr",
                "ya8",
                "ya16be",
                "ya16le",
            ) or pixel_format.startswith(("yuva", "gbrap"))
        if a["kind"] == "audio":
            duration = probe.get("format", {}).get("duration", stream.get("duration"))
            if duration:
                a["metadata"]["duration"] = float(duration)
    return a


def quoted_asset_matches(measured, asset):
    """估价 ID 可省略；已提供时必须一致，来源、类型和顺序始终核对。"""
    return (measured.get('kind') == asset.get('kind')
            and measured.get('source') == asset.get('source')
            and ('id' not in measured or measured['id'] == asset.get('id')))
