"""根据媒体来源测量计费输入，绝不提交生成请求。"""

from core import process
import copy
import json
import math
import mimetypes
from fractions import Fraction
from core.file_hash import sha256_file
from core.media_format import image_mime
from core.payload_size import validate_image_request_size
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from core.validation import require


def display_dimensions(stream):
    """区分编码像素与用户看到的画幅，后者用于 adaptive 输出推导。"""
    width, height = stream['width'], stream['height']
    try:
        sar = Fraction(str(stream.get('sample_aspect_ratio', '1:1')).replace(':', '/'))
        if sar > 0:
            width *= float(sar)
    except (ValueError, ZeroDivisionError):
        pass
    rotation = stream.get('tags', {}).get('rotate', 0)
    for side in stream.get('side_data_list', []):
        if 'rotation' in side:
            rotation = side['rotation']
    try:
        if round(float(rotation)) % 180 == 90:
            width, height = height, width
    except (ValueError, TypeError):
        pass
    return width, height


def media_duration(stream, data, source, probe):
    """从头部、时间基、帧信息逐级恢复时长；最后尝试扫描时间戳。"""
    for value, basis in [(stream.get('duration'), 'stream_duration'),
                         (data.get('format', {}).get('duration'), 'container_duration')]:
        try:
            value = float(value)
            if math.isfinite(value) and value > 0:
                return value, basis
        except (ValueError, TypeError):
            pass
    try:
        value = float(stream['duration_ts']) * float(Fraction(stream['time_base']))
        if math.isfinite(value) and value > 0:
            return value, 'duration_ts_time_base'
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        pass
    # 不用固定24fps猜输入时长，优先读取真实包时间戳（含 VFR）。
    result = process.run([probe, '-v', 'error', '-protocol_whitelist', 'file,http,https,tcp,tls',
                          '-select_streams', str(stream.get('index', 0)), '-show_packets',
                          '-show_entries', 'packet=pts_time,duration_time', '-of', 'json', source],
                         capture_output=True, text=True, timeout=30)
    try:
        packets = json.loads(result.stdout)['packets']
        starts = [float(p['pts_time']) for p in packets if 'pts_time' in p]
        ends = [float(p['pts_time']) + float(p.get('duration_time', 0))
                for p in packets if 'pts_time' in p]
        value = max(ends) - min(starts)
        if result.returncode == 0 and math.isfinite(value) and value > 0:
            return value, 'packet_timestamps'
    except (ValueError, KeyError, TypeError):
        pass
    raise ValueError('No usable media duration after header/time-base/timestamp inspection')


def probe_asset(asset):
    require(
        isinstance(asset, dict)
        and {"kind", "source"} <= set(asset)
        and (set(asset) <= {"id", "kind", "source"}),
        "Each cost asset requires kind/source and an optional id",
    )
    if "id" in asset:
        require(
            isinstance(asset["id"], str) and bool(asset["id"].strip()),
            "Asset id must be a nonempty string",
        )
    kind, source = (asset["kind"], asset["source"])
    require(kind in ("image", "video", "audio"), "Invalid cost asset kind")
    require(isinstance(source, str) and bool(source), "Asset source must be a path or HTTPS URL")
    if source.startswith("https://"):
        url = urlsplit(source)
        require(
            bool(url.hostname) and (not url.username) and (not url.password),
            "Use an HTTPS URL without embedded credentials",
        )
    else:
        path = Path(source)
        require(
            path.is_absolute() and path.is_file(),
            "Use an existing absolute media path or HTTPS URL; asset IDs need an accessible original source",
        )
    local_hash = sha256_file(source) if not source.startswith("https://") else None
    probe = shutil.which("ffprobe")
    require(
        probe is not None,
        "ffprobe is required to inspect cost assets; run main.py doctor --dependencies",
    )
    try:
        result = process.run(
            [
                probe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,http,https,tcp,tls",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                source,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError("Could not inspect cost asset; check media access and ffprobe") from None
    require(result.returncode == 0, "Could not inspect cost asset; check media access and format")
    try:
        data = json.loads(result.stdout)
        stream = next(
            (
                s
                for s in data["streams"]
                if s.get("codec_type") == ("video" if kind == "image" else kind)
            )
        )
        metadata = {}
        if kind in ("image", "video"):
            w, h = (stream["width"], stream["height"])
            require(
                type(w) is int and type(h) is int and (w > 0) and (h > 0),
                "Invalid media dimensions",
            )
            metadata.update(width=w, height=h)
            display_width, display_height = display_dimensions(stream)
            metadata.update(display_width=display_width, display_height=display_height)
            if kind == "image":
                metadata["mime"] = {"png": "image/png", "mjpeg": "image/jpeg"}.get(
                    stream.get("codec_name")
                )
                byte_size = data.get("format", {}).get("size")
                if byte_size is not None and str(byte_size).isdigit():
                    metadata["bytes"] = int(byte_size)
                pixel_format = stream.get("pix_fmt", "")
                metadata["has_alpha"] = pixel_format in (
                    "rgba",
                    "bgra",
                    "argb",
                    "abgr",
                    "ya8",
                    "ya16be",
                    "ya16le",
                ) or pixel_format.startswith(("yuva", "gbrap"))
        if kind in ("video", "audio"):
            metadata["format_name"] = data.get("format", {}).get("format_name", "")
            metadata["codec_name"] = stream.get("codec_name")
            size = data.get("format", {}).get("size")
            if size is not None and str(size).isdigit():
                metadata["bytes"] = int(size)
            if kind == "video":
                rate = stream.get("avg_frame_rate")
                if rate in (None, "N/A", "0/0"):
                    rate = stream.get("r_frame_rate")
                metadata["frame_rate"] = float(Fraction(str(rate)))
            duration, duration_basis = media_duration(stream, data, source, probe)
            metadata["duration"] = duration
            metadata['duration_basis'] = duration_basis
    except (ValueError, TypeError, KeyError, StopIteration, AttributeError, ZeroDivisionError):
        raise ValueError(
            "Cost asset has no valid dimensions/duration for its declared kind"
        ) from None
    if local_hash is not None:
        require(
            sha256_file(source) == local_hash,
            "Local asset changed during inspection; estimate again",
        )
        metadata.update(
            sha256=local_hash,
            bytes=Path(source).stat().st_size,
            mime=image_mime(source) if kind == "image" else mimetypes.guess_type(source)[0],
        )
        if kind == "audio":
            formats = set(metadata.get("format_name", "").split(","))
            metadata["mime"] = (
                "audio/wav"
                if "wav" in formats
                else "audio/mpeg" if "mp3" in formats else metadata["mime"]
            )
    metadata['cost_probe_version'] = 2
    return {
        **({"id": asset["id"]} if "id" in asset else {}),
        "kind": kind,
        "source": source,
        "metadata": metadata,
    }
