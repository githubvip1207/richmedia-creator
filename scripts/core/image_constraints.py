"""两家供应商共用的参考图片约束。"""

from core.validation import require


def validate_image_metadata(metadata, require_dimensions=True):
    """Seedream 参考图片限制；远程素材的字节大小可能尚未核验。"""
    width, height = (metadata.get("width"), metadata.get("height"))
    if width is not None or height is not None or require_dimensions:
        require(
            type(width) is int
            and type(height) is int
            and (min(width, height) > 14)
            and (width * height <= 36000000)
            and (0.0625 <= width / height <= 16),
            "Image dimensions outside supported reference limits",
        )
    if "bytes" in metadata:
        require(
            type(metadata["bytes"]) is int and 0 <= metadata["bytes"] <= 31457280,
            "Image exceeds 30 MB limit",
        )
    if metadata.get("mime") is not None:
        require(
            metadata["mime"]
            in (
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/bmp",
                "image/x-ms-bmp",
                "image/tiff",
                "image/gif",
                "image/heic",
                "image/heif",
            ),
            "Unsupported input image format",
        )
