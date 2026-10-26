"""验证实际下载的媒体，不解释供应商特有的业务规则。"""

from core import process
import json
import shutil
import subprocess
from core.validation import require


def video_metadata(path):
    """检查实际解码帧、尺寸、时长以及是否包含音轨。"""
    probe = shutil.which("ffprobe")
    require(probe is not None, "ffprobe is required to validate downloaded videos")
    try:
        with open(path, "rb") as stream:
            head = stream.read(12)
        require(len(head) >= 12 and head[4:8] == b"ftyp", "Invalid MP4/MOV container")
        result = process.run(
            [
                probe,
                "-v",
                "error",
                "-count_frames",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        data = json.loads(result.stdout)
        stream = next((s for s in data["streams"] if s.get("codec_type") == "video"))
        duration = float(data.get("format", {}).get("duration", stream.get("duration", 0)))
        require(
            result.returncode == 0
            and (not result.stderr.strip())
            and (duration > 0)
            and (stream.get("width", 0) > 0)
            and (stream.get("height", 0) > 0)
            and (int(stream.get("nb_read_frames", 0)) > 0),
            "Invalid video stream",
        )
        from core.media_probe import display_dimensions
        display_width, display_height = display_dimensions(stream)
        return {
            "display_width": display_width,
            "display_height": display_height,
            "width": stream["width"],
            "height": stream["height"],
            "duration": duration,
            "codec": stream.get("codec_name"),
            "frame_rate": stream.get("avg_frame_rate"),
            "has_audio": any((s.get("codec_type") == "audio" for s in data["streams"])),
        }
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, StopIteration):
        raise ValueError("Downloaded video has no valid decodable video stream") from None


def valid_media(path, kind, expected_size=None, require_alpha=False):
    with open(path, "rb") as f:
        head = f.read(32)
    if kind == "video":
        if not (len(head) > 8 and head[4:8] == b"ftyp"):
            return False
        try:
            video_metadata(path)
            return True
        except ValueError:
            return False
    if not (
        head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"))
        or (head.startswith(b"RIFF") and head[8:12] == b"WEBP")
    ):
        return False
    probe = shutil.which("ffprobe")
    require(probe is not None, "ffprobe is required to validate downloaded images")
    try:
        result = process.run(
            [
                probe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_streams",
                "-show_frames",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(result.stdout)
        if require_alpha:
            formats = [stream.get("pix_fmt", "") for stream in data.get("streams", [])]
            if not any(
                (
                    fmt in ("rgba", "bgra", "argb", "abgr", "ya8", "ya16be", "ya16le")
                    or fmt.startswith(("yuva", "gbrap"))
                    for fmt in formats
                )
            ):
                return False
        if expected_size and "x" in expected_size:
            width, height = map(int, expected_size.split("x"))
            if not any(
                (
                    s.get("width") == width and s.get("height") == height
                    for s in data.get("streams", [])
                )
            ):
                return False
        return (
            result.returncode == 0
            and (not result.stderr.strip())
            and any(
                (s.get("width", 0) > 0 and s.get("height", 0) > 0 for s in data.get("streams", []))
            )
            and bool(data.get("frames"))
        )
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        return False


def verification_source(compiled, context=None):
    """从已确认素材中定位首帧或编辑、延长的目标，不猜测多视频目标。"""
    assets = compiled.get('assets', [])
    operation = compiled.get('operation')
    if operation == 'image-to-video':
        return assets[0] if assets else None
    if operation == 'extend-video' or (operation == 'reference-to-video' and compiled.get('mode') == 'edit'):
        from core.target_asset import target_index
        index = target_index(assets, compiled.get('target_asset_id'), context)
        if index is not None:
            return assets[index]
    return None


def verify_spec(path, kind, compiled, metadata=None, estimate_context=None):
    """记录可观察规格的差异；保留供应商原件，不自动重生成或隐藏已付费产物。"""
    import math
    from core.video_dimensions import table_dimensions
    from core.cost_reconcile import image_dimensions
    from core.catalogs import CATALOGS
    p = compiled['parameters']
    actual = metadata if kind == 'video' else dict(zip(('width', 'height'), image_dimensions(path)))
    differences = []
    checks = []
    def compare(field, expected, observed, matches):
        checks.append(field)
        if not matches:
            differences.append({'field': field, 'expected': expected, 'actual': observed})
    if kind == 'video':
        source = verification_source(compiled, estimate_context)
        if p.get('resolution') and p.get('ratio') not in (None, 'adaptive'):
            dims = table_dimensions(compiled['model'], p['resolution'], p['ratio'])
            observed = [actual['width'], actual['height']]
            compare('dimensions', dims, observed, observed == dims)
        elif p.get('resolution'):
            choices = [table_dimensions(compiled['model'], p['resolution'], ratio)
                       for ratio in ('16:9', '4:3', '1:1', '3:4', '9:16', '21:9')]
            area = actual['width'] * actual['height']
            compare('resolution', p['resolution'], [actual['width'], actual['height']],
                    min(math.prod(d) for d in choices) * .95 <= area <= max(math.prod(d) for d in choices) * 1.05)
        if p.get('ratio') == 'adaptive' and source and p.get('resolution'):
            m = source.get('metadata', {})
            width = m.get('display_width', m.get('width'))
            height = m.get('display_height', m.get('height'))
            if width and height:
                expected_ratio = width / height
                if compiled['model'] == 'seedance-2.5':
                    observed_ratio = (actual.get('display_width', actual['width']) /
                                      actual.get('display_height', actual['height']))
                    compare('ratio', [width, height], [actual['width'], actual['height']],
                            abs(math.log(observed_ratio / expected_ratio)) <= .01)
                else:
                    # 2.0 输出标准比例；采用该模型的像素表，容纳 864×496 等取整规格。
                    ratios = [16 / 9, 4 / 3, 1, 3 / 4, 9 / 16, 21 / 9]
                    distances = [abs(math.log(expected_ratio / ratio)) for ratio in ratios]
                    nearest = min(range(len(ratios)), key=distances.__getitem__)
                    allowed = [choices[nearest]] if distances[nearest] <= .01 else choices
                    compare('dimensions', allowed, [actual['width'], actual['height']],
                            [actual['width'], actual['height']] in allowed)
        if p.get('duration', -1) != -1:
            # 容器时间基和尾帧取整允许最多约半秒差异。
            compare('duration', p['duration'], actual['duration'], abs(actual['duration'] - p['duration']) <= .5)
        else:
            maximum = CATALOGS[compiled['provider']]['models'][compiled['model']]['max_duration']
            compare('duration', [4, maximum], actual['duration'],
                    3.5 <= actual['duration'] <= maximum + .5)
            if (compiled['model'] == 'seedance-2.5' and
                    compiled.get('operation') == 'reference-to-video' and
                    compiled.get('mode') == 'edit' and source):
                seconds = source.get('metadata', {}).get('duration')
                if seconds is not None:
                    compare('source_duration', seconds, actual['duration'],
                            abs(actual['duration'] - seconds) <= .5)
        if 'generate_audio' in p:
            compare('has_audio', p['generate_audio'], actual['has_audio'], p['generate_audio'] == actual['has_audio'])
    elif compiled['kind'] == 'image' and compiled['operation'] != 'decompose-layers':
        size = p.get('size', '')
        dims = [actual['width'], actual['height']]
        if 'x' in size:
            expected = list(map(int, size.split('x')))
            compare('dimensions', expected, dims, expected == dims)
        elif size in ('1K', '1.5K', '2K'):
            # 档位对应像素面积，不能只比较长边；容纳供应商比例表的整数取整。
            nominal = {'1K': 1024**2, '1.5K': 1536**2, '2K': 2048**2}[size]
            compare('size', size, dims, .9 * nominal <= math.prod(dims) <= 1.1 * nominal)
    return {'status': 'mismatch' if differences else 'matched' if checks else 'not_checked', 'differences': differences}
