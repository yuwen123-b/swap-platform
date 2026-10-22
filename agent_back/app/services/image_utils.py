"""物品图片本地化公共模块。

背景：物品图片在 DB 里以 `item.images` JSON 数组存储，两种形态混用——
种子数据是**公网外链**（Unsplash），用户上传是**签名静态 URL**
（`/api/v1/static/items/xxx.jpg?exp=&sig=`）。而下游能力对"本地文件 + JPEG"
有硬要求：

- 图像编辑 / 360° 外推：需要本地文件（魔搭走 multipart，百炼走公网 URL）；
- 图生 3D：格式仅 JPEG / PNG / WEBP，且混元（TokenHub）要求编码前 ≤6MB。用户上传的
  `item 73` 原图实际是 **WEBP**（扩展名与真实字节不一定一致，必须按内容判断）。

因此这里统一提供 `ensure_local_jpeg()`：把任意形态的图片 URL 落到本地 JPEG。
`panorama.py` 与 `three_d_service.py` 共用同一份逻辑，避免出现两份会漂移的实现。
"""
import json
import logging
import uuid
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

# 外链原图下载上限：与上传接口的 5MB 不同，这里宽一些（相机原图常见 8-12MB，
# Tripo 单图上限是 20MB，但 10MB 已足够覆盖社区场景且能防住超大文件）
MAX_REMOTE_IMAGE_BYTES = 10 * 1024 * 1024

# 已确认"就是 JPEG"的扩展名：命中即原样返回，不重复编码（避免二次压缩掉画质）
_JPEG_SUFFIXES = {".jpg", ".jpeg"}

# 转码质量：只用于 WEBP/PNG/GIF → JPEG，92 在体积与观感之间取平衡
_JPEG_QUALITY = 92


class ImageSourceError(Exception):
    """物品图片无法本地化：外链下载失败 / 本地文件缺失 / URL 形态不支持。

    由 API 层捕获后转成 400 + 中文提示，绝不把网络堆栈透给用户。
    """


def static_prefix() -> str:
    """静态资源前缀（与 files.py 的路由前缀一致）。"""
    return f"{settings.api_prefix}/static/"


def resolve_static_path(image_url: str) -> Path | None:
    """签名静态 URL / 相对路径 → uploads 下的真实文件路径；无法解析返回 None。

    必须先剥掉 `?exp=&sig=` 再拼路径，否则文件名里会带上 query，`exists()` 恒为 False。
    兼容**裸相对路径**（`items/xxx.webp`）：DB 改为只存相对路径后，
    `ensure_local_jpeg` 的输入不再是带前缀的签名 URL，而是相对路径本身。
    """
    prefix = static_prefix()
    text = str(image_url or "")
    # 其它 scheme（ftp:// 等）不属于本系统的静态资源，明确拒绝而非当相对路径
    if "://" in text and not text.startswith(("http://", "https://")):
        return None
    if text.startswith(prefix):
        text = text[len(prefix):]
    elif text.startswith("/static/"):
        text = text[len("/static/"):]
    elif text.startswith(("http://", "https://")):
        return None
    relative = text.split("?", 1)[0].lstrip("/")
    if not relative:
        return None
    return Path(settings.upload_dir).resolve() / relative


def normalize_image_ref(value) -> str | None:
    """`item.images` 里的单条值 → 统一成「相对路径」或「外链原样」。

    兼容三种历史形态（这是 2026-10 修复「发布 1 小时后封面 403」的关键）：

    - 外链 `https://...`                      → 原样返回（演示数据 55-61）；
    - **已签名的静态 URL**（带 `?exp=&sig=`）  → 剥掉静态前缀与 query，只留相对路径
      （存量脏数据如 `item.id=77`，改读取逻辑后**无需写 SQL 即自动恢复**）；
    - 相对路径 `items/xxx.webp`               → 原样返回（2026-10 起的标准形态）。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        return text
    prefix = static_prefix()
    if text.startswith(prefix):
        text = text[len(prefix):]
    elif text.startswith("/static/"):
        text = text[len("/static/"):]
    # 剥掉残留的签名 query，再归一成不带开头斜杠的相对路径
    text = text.split("?", 1)[0].lstrip("/")
    return text or None


def to_signed_url(value) -> str | None:
    """相对路径 / 历史签名 URL / 外链 → 可直接给 `<img>` 的受控 URL。

    **签名在读取时现场补**——签名只 1 小时有效，落库必然过期
    （与 `merchant_service.sign_relative` 同一口径，本函数是其唯一实现）。
    """
    ref = normalize_image_ref(value)
    if not ref:
        return None
    if ref.startswith(("http://", "https://")):
        return ref
    return f"{static_prefix()}{ref}?{_sign(ref)}"


def item_covers(raw) -> list[str]:
    """`item.images`（JSON 字符串 / 已解析列表 / 裸值）→ 已签名 URL 列表。

    所有读取端（物品列表 / 详情 / 我的物品 / 我的收藏 / 交换记录 / 回收单）
    统一走这里，保证「DB 存相对路径 + 读取时签名」只有一份实现。
    解析失败一律降级为空列表，绝不让脏数据导致接口 500。
    """
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        values = [str(v) for v in raw if v]
    else:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            # 非 JSON 的裸路径（历史数据）：看起来像路径才采用
            values = [raw] if isinstance(raw, str) and "/" in raw else []
        else:
            values = [str(v) for v in parsed] if isinstance(parsed, list) else []
    urls = [to_signed_url(v) for v in values]
    return [u for u in urls if u]


def item_covers_json(raw) -> str | None:
    """`item_covers` 的 JSON 字符串版本：保持接口返回形态与历史一致（字符串）。"""
    covers = item_covers(raw)
    return json.dumps(covers, ensure_ascii=False) if covers else None


def to_public_url(relative_path: str) -> str:
    """uploads 下的相对路径 → 外部可抓取的签名公网 URL。

    仅供**需要公网图**的远端服务使用（Tripo 回退分支、图像编辑）。
    混元 3D 走 base64 本地上传，不经过这里，因此不依赖 `PUBLIC_BASE_URL`。
    """
    return (
        f"{settings.public_base_url}{static_prefix()}{relative_path}"
        f"?{_sign(relative_path)}"
    )


def _sign(relative_path: str) -> str:
    # 惰性 import：避免本模块被 db/security 层反向依赖时出现循环导入
    from app.core.security import sign_file_path

    return sign_file_path(relative_path)


def _derived_dir() -> Path:
    """未指定落盘位置时的默认目录（uploads 下，保证可被静态路由签名访问）。"""
    return Path(settings.upload_dir).resolve() / "_derived"


def _fetch_remote_image(url: str) -> bytes:
    """下载外链图片原始字节；任何异常都归一为 ImageSourceError + 中文原因。"""
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (swap-app)"})
    except requests.RequestException:
        raise ImageSourceError("物品图片无法下载，请稍后重试") from None
    if resp.status_code >= 400 or not resp.content:
        raise ImageSourceError("物品图片无法下载，请检查图片链接是否有效")
    if len(resp.content) > MAX_REMOTE_IMAGE_BYTES:
        raise ImageSourceError("物品图片过大（超过 10MB），无法使用")
    return resp.content


def _write_jpeg(data: bytes, dest: Path) -> Path:
    """把图片字节落到 dest 为 JPEG：本身是 JPEG 则原样写入（零重编码）。"""
    try:
        with Image.open(BytesIO(data)) as img:
            fmt = (img.format or "").upper()
            if fmt == "JPEG":
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                return dest
            rgb = img.convert("RGB")
    except (OSError, ValueError) as exc:
        raise ImageSourceError(f"物品图片不是有效图片：{exc}") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(dest, "JPEG", quality=_JPEG_QUALITY)
    return dest


def _convert_to_jpeg(source: Path, dest: Path) -> Path:
    """本地非 JPEG（WEBP/PNG/GIF）→ JPEG。"""
    try:
        with Image.open(source) as img:
            rgb = img.convert("RGB")
            dest.parent.mkdir(parents=True, exist_ok=True)
            rgb.save(dest, "JPEG", quality=_JPEG_QUALITY)
    except (OSError, ValueError) as exc:
        raise ImageSourceError(f"物品图片转码失败：{exc}") from exc
    return dest


def ensure_local_jpeg(image_url: str, dest: Path | str | None = None) -> Path:
    """把物品图片 URL 解析为本地 JPEG 文件并返回其路径。

    - 外链（http(s)://）：下载（≤10MB）后写为 JPEG；
    - 签名静态 URL：映射到 uploads 下真实文件，**已是 JPEG 则原样返回**
      （不重复编码，调用方拿到的就是库里的原件）；
    - 其余形态 / 文件缺失 / 下载失败：抛 ImageSourceError。

    `dest` 指定落盘位置；留空则写入 `uploads/_derived/` 下的随机文件名。
    注意：已是 JPEG 的本地文件会**忽略 dest 直接返回源路径**——语义是
    "给出一个可用的 JPEG 本地路径"，而非"必须复制一份到 dest"。
    """
    dest_path = Path(dest) if dest else _derived_dir() / f"{uuid.uuid4().hex}.jpg"

    if image_url.startswith(("http://", "https://")):
        return _write_jpeg(_fetch_remote_image(image_url), dest_path)

    source = resolve_static_path(image_url)
    if source is None:
        raise ImageSourceError("物品图片 URL 格式不支持")
    if not source.is_file():
        raise ImageSourceError("物品图片文件不存在")
    if source.suffix.lower() in _JPEG_SUFFIXES:
        return source
    return _convert_to_jpeg(source, dest_path)
