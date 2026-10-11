"""panorama_service 单元测试（异步函数仅测逻辑入口与状态回写）。"""
import json
import os
from pathlib import Path

import pytest
from conftest import FakeCursor, make_connection

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


def test_generate_total_size_exceeds_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.panorama_service.settings.public_base_url", "https://example.com"
    )
    # 让 image_edit 成功并写一个大文件
    def fake_edit(url, prompt):
        return "https://example.com/img.jpg"

    monkeypatch.setattr("app.services.panorama_service.llm_client.image_edit", fake_edit)

    def fake_download(url, dest):
        # 故意写超大文件触发上限
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x" * (3 * 1024 * 1024))

    monkeypatch.setattr("app.services.panorama_service.llm_client.download_file", fake_download)
    _patch_db(monkeypatch, [])
    source = tmp_path / "front.jpg"
    source.write_bytes(b"fake")
    with pytest.raises(RuntimeError, match="超过 2MB"):
        panorama_service.generate(1, source)


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
