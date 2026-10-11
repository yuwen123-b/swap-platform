"""panorama_service 单元测试（异步函数仅测逻辑入口与状态回写）。"""
import json
import os
from pathlib import Path

import pytest
from conftest import FakeCursor, make_connection
from PIL import Image

from app.services import panorama_service


def _patch_db(monkeypatch, rows):
    cursor = FakeCursor(rows=rows)
    monkeypatch.setattr("app.services.panorama_service.connection", make_connection(cursor))
    return cursor


def test_get_views_not_exists(monkeypatch):
    _patch_db(monkeypatch, [])
    with pytest.raises(ValueError, match="物品不存在"):
        panorama_service.get_views(999)


def test_get_views_none_status(monkeypatch):
    _patch_db(monkeypatch, [{"panorama_status": "none", "panorama_views": None}])
    result = panorama_service.get_views(1)
    assert result["status"] == "none"
    assert result["views"] == {}
    assert result["fallback"] is False


def test_get_views_ready_with_data(monkeypatch):
    payload = json.dumps({"views": {"front": "/f.jpg"}, "fallback": True, "generated_at": "2026-10-11T00:00:00+00:00"})
    _patch_db(monkeypatch, [{"panorama_status": "ready", "panorama_views": payload}])
    result = panorama_service.get_views(1)
    assert result["status"] == "ready"
    assert result["views"]["front"] == "/f.jpg"
    assert result["fallback"] is True


def _noise_jpeg(path: Path, size: int = 1400) -> None:
    """生成随机噪声 JPEG（随机像素几乎不可压缩，稳定产出大文件）。"""
    img = Image.frombytes("RGB", (size, size), os.urandom(size * size * 3))
    img.save(path, "JPEG", quality=95)


def test_generate_compresses_oversize_views(tmp_path, monkeypatch):
    """外推下载的四视角图总量超限时自动 PIL 压缩，最终 ready 且 ≤2MB。"""
    monkeypatch.setattr(
        "app.services.panorama_service.settings.public_base_url", "https://example.com"
    )
    monkeypatch.setattr(
        "app.services.panorama_service.settings.upload_dir", str(tmp_path / "uploads")
    )
    monkeypatch.setattr(
        "app.services.panorama_service.llm_client.image_edit",
        lambda url, prompt: "https://example.com/img.jpg",
    )

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        _noise_jpeg(dest)

    monkeypatch.setattr("app.services.panorama_service.llm_client.download_file", fake_download)
    _patch_db(monkeypatch, [])
    source = tmp_path / "front.jpg"
    _noise_jpeg(source, size=1000)

    result = panorama_service.generate(1, source)

    views_dir = tmp_path / "uploads" / "items" / "1" / "views"
    files = list(views_dir.glob("*.jpg"))
    assert result["status"] == "ready"
    assert result["fallback"] is False
    assert len(files) == 4
    assert sum(p.stat().st_size for p in files) <= panorama_service.MAX_TOTAL_BYTES


def test_compress_views_noop_under_limit(tmp_path):
    """总大小已达标时不重压缩，文件字节保持不变。"""
    views_dir = tmp_path / "views"
    views_dir.mkdir()
    original = {}
    for name in panorama_service.VIEW_NAMES:
        path = views_dir / f"{name}.jpg"
        Image.new("RGB", (64, 64), color=(120, 40, 40)).save(path, "JPEG", quality=90)
        original[name] = path.read_bytes()

    panorama_service._compress_views(views_dir)

    for name, data in original.items():
        assert (views_dir / f"{name}.jpg").read_bytes() == data


def test_compress_views_garbage_raises(tmp_path):
    """坏图无法解析时抛 RuntimeError（保留超限失败兜底语义）。"""
    views_dir = tmp_path / "views"
    views_dir.mkdir()
    for name in ("front", "left", "back"):
        (views_dir / f"{name}.jpg").write_bytes(b"not-an-image" * 60000)  # 每张约 700KB

    with pytest.raises(RuntimeError, match="压缩失败"):
        panorama_service._compress_views(views_dir)


def test_generate_async_starts_thread(monkeypatch, tmp_path):
    called = {}
    monkeypatch.setattr(
        "app.services.panorama_service.settings.public_base_url", ""
    )
    monkeypatch.setattr(
        "app.services.panorama_service.generate",
        lambda item_id, source_image: called.setdefault("sync", (item_id, source_image)),
    )
    front = tmp_path / "front.jpg"
    front.write_bytes(b"fake")
    panorama_service.generate_async(2, front)
    assert os.path.exists(front)
    # generate_async 启动线程，这里只验证不抛异常即可；非阻塞测试中不等待线程
