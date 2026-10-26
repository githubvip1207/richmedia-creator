"""根据文件字节识别媒体容器格式。"""


def image_mime(path):
    """根据文件内容识别支持的本地图片格式，不依赖文件名。"""
    with open(path, "rb") as stream:
        head = stream.read(4096)
    signatures = (
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"BM", "image/bmp"),
        (b"II*\x00", "image/tiff"),
        (b"MM\x00*", "image/tiff"),
        (b"II+\x00", "image/tiff"),
        (b"MM\x00+", "image/tiff"),
    )
    for signature, mime in signatures:
        if head.startswith(signature):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp":
        box_size = int.from_bytes(head[:4], "big")
        if 16 <= box_size <= len(head):
            brands = {head[8:12]} | {head[i : i + 4] for i in range(16, box_size - 3, 4)}
            heic = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs"}
            if not brands & {b"avif", b"avis"}:
                if brands & heic:
                    return "image/heic"
                if brands & {b"mif1", b"msf1"}:
                    return "image/heif"
    raise ValueError("Unsupported input image format; file content must be a supported image")
