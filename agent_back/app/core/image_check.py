"""图片文件魔数（Magic Number）校验工具。

上传接口仅凭 HTTP 的 Content-Type 判断文件类型是不可靠的：客户端可随意伪造该头，
把 HTML/JS 等可执行内容伪装成图片落盘，再通过 URL 直链访问形成存储型 XSS。

本模块通过读取文件头字节（魔数）判断真实图片类型，作为类型判定的唯一依据。
支持 jpg / png / webp / gif 四种格式，与上传接口的白名单保持一致。
"""

# 各格式的文件头特征（bytes）与对应扩展名
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "jpg"),                      # JPEG：FF D8 FF
    (b"\x89PNG\r\n\x1a\n", "png"),                 # PNG：89 50 4E 47 0D 0A 1A 0A
    (b"GIF87a", "gif"),                            # GIF87a
    (b"GIF89a", "gif"),                            # GIF89a
]

# WebP 需要额外校验：RIFF....WEBP（第 0-3 字节 RIFF，第 8-11 字节 WEBP）
_RIFF_MAGIC = b"RIFF"
_WEBP_MAGIC = b"WEBP"


def detect_image_ext(data: bytes) -> str | None:
    """读取字节流魔数，返回真实图片扩展名；无法识别时返回 None。

    - 只读取文件头，不做完整图片解码，开销极低；
    - 返回值为 "jpg" / "png" / "webp" / "gif"，与 ALLOWED_IMAGE_TYPES 的 value 对齐。
    """
    if not data:
        return None

    for signature, ext in _SIGNATURES:
        if data.startswith(signature):
            return ext

    # WebP：RIFF 容器格式，需同时校验头部与格式标识
    if data[:4] == _RIFF_MAGIC and data[8:12] == _WEBP_MAGIC:
        return "webp"

    return None
