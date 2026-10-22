"""image_utils 公共模块单元测试（不联网、不碰真实 uploads）。

覆盖两条真实场景：
- 用户上传的签名 URL（`item 73` 原图实际是 **WEBP**）→ 必须转成真 JPEG；
- 种子物品的 Unsplash **外链** → 下载后落盘，已是 JPEG 则零重编码。
"""
import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import settings
from app.services import image_utils


class _FakeResp:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code


def _jpeg_bytes(size=(32, 32), color=(200, 100, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def _webp_bytes(size=(32, 32), color=(10, 120, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "WEBP")
    return buf.getvalue()


def _patch_upload_dir(monkeypatch, tmp_path) -> Path:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    return tmp_path / "uploads"


def _patch_get(monkeypatch, content: bytes, status_code: int = 200) -> None:
    monkeypatch.setattr(
        image_utils.requests, "get",
        lambda url, timeout=30, headers=None: _FakeResp(content, status_code),
    )


# ============================================================
# 签名静态 URL
# ============================================================
def test_static_url_jpeg_returns_source_untouched(monkeypatch, tmp_path):
    """签名 URL + 已是 JPEG：原样返回源文件（零拷贝零重编码）。"""
    root = _patch_upload_dir(monkeypatch, tmp_path)
    target = root / "items" / "a.jpg"
    target.parent.mkdir(parents=True)
    data = _jpeg_bytes()
    target.write_bytes(data)

    got = image_utils.ensure_local_jpeg(
        f"{settings.api_prefix}/static/items/a.jpg?exp=1&sig=x",
        dest=root / "items" / "copy.jpg",
    )

    assert got.resolve() == target.resolve()
    assert got.read_bytes() == data
    assert not (root / "items" / "copy.jpg").exists()


def test_static_url_query_string_stripped(monkeypatch, tmp_path):
    """带 ?exp=&sig= 的 URL 必须先剥 query 再找文件（否则 exists() 恒为 False）。"""
    root = _patch_upload_dir(monkeypatch, tmp_path)
    target = root / "items" / "signed.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(_jpeg_bytes())

    got = image_utils.ensure_local_jpeg(
        f"{settings.api_prefix}/static/items/signed.jpg?exp=9999999999&sig=abc"
    )
    assert got.resolve() == target.resolve()


def test_static_url_webp_converted_to_jpeg(monkeypatch, tmp_path):
    """上传原图是 WEBP（item 73 的真实情况）：转码为真 JPEG 落到 dest。"""
    root = _patch_upload_dir(monkeypatch, tmp_path)
    target = root / "items" / "b.webp"
    target.parent.mkdir(parents=True)
    target.write_bytes(_webp_bytes())

    dest = root / "items" / "9" / "models" / "source.jpg"
    got = image_utils.ensure_local_jpeg(
        f"{settings.api_prefix}/static/items/b.webp?exp=1&sig=x", dest=dest
    )

    assert got.resolve() == dest.resolve()
    with Image.open(dest) as img:
        assert img.format == "JPEG"
        assert img.size == (32, 32)


def test_missing_local_file_raises(monkeypatch, tmp_path):
    _patch_upload_dir(monkeypatch, tmp_path)
    with pytest.raises(image_utils.ImageSourceError, match="不存在"):
        image_utils.ensure_local_jpeg(f"{settings.api_prefix}/static/items/nope.jpg")


def test_unsupported_url_scheme_raises(monkeypatch, tmp_path):
    _patch_upload_dir(monkeypatch, tmp_path)
    with pytest.raises(image_utils.ImageSourceError, match="格式不支持"):
        image_utils.ensure_local_jpeg("ftp://example.com/x.jpg")


# ============================================================
# 公网外链
# ============================================================
def test_external_url_downloaded_as_jpeg(monkeypatch, tmp_path):
    """外链 JPEG：原样落盘（字节不变），返回 dest。"""
    root = _patch_upload_dir(monkeypatch, tmp_path)
    data = _jpeg_bytes()
    _patch_get(monkeypatch, data)

    dest = root / "items" / "55" / "views" / "front.jpg"
    got = image_utils.ensure_local_jpeg(
        "https://images.unsplash.com/photo-1?w=800", dest=dest
    )

    assert got.resolve() == dest.resolve()
    assert dest.read_bytes() == data


def test_external_url_webp_converted(monkeypatch, tmp_path):
    """外链 WEBP（unsplash 带 auto=format 会返回 WEBP）：转成 JPEG。"""
    root = _patch_upload_dir(monkeypatch, tmp_path)
    _patch_get(monkeypatch, _webp_bytes())

    dest = root / "items" / "73" / "models" / "source.jpg"
    got = image_utils.ensure_local_jpeg("https://example.com/x.webp", dest=dest)

    with Image.open(got) as img:
        assert img.format == "JPEG"


def test_external_download_failure_raises(monkeypatch, tmp_path):
    _patch_upload_dir(monkeypatch, tmp_path)

    def _boom(url, timeout=30, headers=None):
        raise image_utils.requests.ConnectionError("network down")

    monkeypatch.setattr(image_utils.requests, "get", _boom)
    with pytest.raises(image_utils.ImageSourceError, match="无法下载"):
        image_utils.ensure_local_jpeg("https://example.com/x.jpg")


def test_external_http_error_raises(monkeypatch, tmp_path):
    _patch_upload_dir(monkeypatch, tmp_path)
    _patch_get(monkeypatch, b"", status_code=404)
    with pytest.raises(image_utils.ImageSourceError, match="无法下载"):
        image_utils.ensure_local_jpeg("https://example.com/x.jpg")


def test_oversize_remote_raises(monkeypatch, tmp_path):
    _patch_upload_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(image_utils, "MAX_REMOTE_IMAGE_BYTES", 10)
    _patch_get(monkeypatch, _jpeg_bytes())
    with pytest.raises(image_utils.ImageSourceError, match="过大"):
        image_utils.ensure_local_jpeg("https://example.com/big.jpg")


def test_non_image_bytes_raise(monkeypatch, tmp_path):
    """下载回来的不是图片：明确报错，不写出一个坏文件。"""
    root = _patch_upload_dir(monkeypatch, tmp_path)
    _patch_get(monkeypatch, b"not-an-image" * 100)
    dest = root / "items" / "x.jpg"
    with pytest.raises(image_utils.ImageSourceError, match="不是有效图片"):
        image_utils.ensure_local_jpeg("https://example.com/x.jpg", dest=dest)
    assert not dest.exists()


def test_default_dest_lands_under_derived_dir(monkeypatch, tmp_path):
    """未指定 dest：落到 uploads/_derived/ 下（该目录可被静态路由签名访问）。"""
    _patch_upload_dir(monkeypatch, tmp_path)
    _patch_get(monkeypatch, _webp_bytes())

    got = image_utils.ensure_local_jpeg("https://example.com/x.webp")

    assert got.parent.name == "_derived"
    assert got.suffix == ".jpg"
    assert got.is_file()


def test_to_public_url_carries_base_and_signature(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://tunnel.example.com")
    url = image_utils.to_public_url("items/7/models/source.jpg")
    assert url.startswith("https://tunnel.example.com/api/v1/static/items/7/models/source.jpg?exp=")
    assert "sig=" in url
