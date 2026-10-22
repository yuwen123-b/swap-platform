"""panorama 真实路径测试：签名 URL 往返、真实静态路由取图、外链下载、触发保护。

背景：此前 11 个 panorama 用例全是 mock，未覆盖「签名 URL 是否真的能被静态路由
校验通过」这一断点，导致视角图 URL 未签名的前端加载故障漏检。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import FakeCursor, make_connection
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from starlette.background import BackgroundTasks

from app.api.v1 import panorama as panorama_api
from app.core.config import settings
from app.services import image_utils, panorama_service


# ---------------------------------------------------------------------------
# sign_view_url：与真实静态路由的签名校验往返
# ---------------------------------------------------------------------------

def test_sign_view_url_roundtrip_real_static_route(tmp_path, monkeypatch):
    """签名后的视角图 URL 必须能被真实静态路由 200 取回（B2 的核心断点）。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    views_dir = tmp_path / "uploads" / "items" / "7" / "views"
    views_dir.mkdir(parents=True)
    Image.new("RGB", (32, 32), color=(90, 140, 90)).save(views_dir / "front.jpg", "JPEG")

    relative = "items/7/views/front.jpg"
    unsigned = f"{settings.api_prefix}/static/{relative}"
    signed = panorama_service.sign_view_url(unsigned)

    assert "exp=" in signed and "sig=" in signed
    client = TestClient(__import__("app.main", fromlist=["app"]).app)
    assert client.get(unsigned).status_code == 400          # 未签名：缺 exp/sig
    assert client.get(f"{unsigned}?exp=1&sig=forged").status_code == 403  # 坏签名
    resp = client.get(signed)
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("image/")


def test_sign_view_url_keeps_external_url_untouched():
    """外链不做签名处理，原样返回。"""
    url = "https://images.unsplash.com/photo-1?w=800"
    assert panorama_service.sign_view_url(url) == url
    assert panorama_service.sign_view_url("") == ""
    assert panorama_service.sign_view_url(None) is None


def test_sign_view_url_strips_stale_query():
    """URL 上残留的旧签名参数会被剥掉后重新签名，不会拼出双 query。"""
    relative = "items/7/views/left.jpg"
    stale = f"{settings.api_prefix}/static/{relative}?exp=111&sig=old"
    signed = panorama_service.sign_view_url(stale)
    assert signed.count("?") == 1
    assert "sig=old" not in signed


# ---------------------------------------------------------------------------
# get_item / get_views：读取时签名
# ---------------------------------------------------------------------------

def test_get_views_signs_ready_urls(monkeypatch):
    payload = json.dumps({
        "views": {
            "front": f"{settings.api_prefix}/static/items/7/views/front.jpg",
            "left": f"{settings.api_prefix}/static/items/7/views/left.jpg",
        },
        "fallback": False,
    })
    cursor = FakeCursor(rows=[{
        "panorama_status": "ready", "panorama_views": payload, "panorama_generated_at": None,
    }])
    monkeypatch.setattr("app.services.panorama_service.connection", make_connection(cursor))
    result = panorama_service.get_views(7)
    for url in result["panorama_views"].values():
        assert "sig=" in url


def test_get_views_generating_timeout_marks_failed(monkeypatch):
    """generating 起始时间超过 10 分钟：判为失败并回写 failed。"""
    cursor = FakeCursor(rows=[{
        "panorama_status": "generating",
        "panorama_views": None,
        "panorama_generated_at": datetime.now() - timedelta(minutes=panorama_service.GENERATING_TIMEOUT_MINUTES + 1),
    }])
    monkeypatch.setattr("app.services.panorama_service.connection", make_connection(cursor))
    result = panorama_service.get_views(7)
    assert result["panorama_status"] == "failed"
    # 回写语句确实执行了
    assert any("failed" in str(sql) for sql in cursor.executed)


def test_get_views_generating_fresh_keeps_generating(monkeypatch):
    """刚置 generating：保持 generating，不误判。"""
    cursor = FakeCursor(rows=[{
        "panorama_status": "generating",
        "panorama_views": None,
        "panorama_generated_at": datetime.now() - timedelta(seconds=30),
    }])
    monkeypatch.setattr("app.services.panorama_service.connection", make_connection(cursor))
    result = panorama_service.get_views(7)
    assert result["panorama_status"] == "generating"


# ---------------------------------------------------------------------------
# generate_panorama：URL 解析 + 重复触发保护
# ---------------------------------------------------------------------------

def _patch_item_row(monkeypatch, row):
    cursor = FakeCursor(rows=[row] if row else [])
    monkeypatch.setattr("app.api.v1.panorama.connection", make_connection(cursor))
    return cursor


def test_generate_panorama_signed_url_strips_query(tmp_path, monkeypatch):
    """签名 URL（带 ?exp=&sig=）必须先剥 query 再找文件——修复前 100% 报 400 的场景。"""
    real_image = tmp_path / "uploads" / "items" / "abc.jpg"
    real_image.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16)).save(real_image, "JPEG")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    captured = {}
    monkeypatch.setattr(
        panorama_api.panorama_service, "run_generate",
        lambda item_id, source: captured.setdefault("source", source),
    )
    _patch_item_row(monkeypatch, {"user_id": 18, "images": json.dumps([
        f"{settings.api_prefix}/static/items/abc.jpg?exp=1760000000&sig=abc123",
    ]), "panorama_status": "none"})

    bg = BackgroundTasks()
    resp = panorama_api.generate_panorama(panorama_api.PanoramaRequest(item_id=55), bg, user_id=18)
    assert resp["code"] == 0
    # 直调函数时 BackgroundTasks 不会执行，断言后台任务已按正确参数注册
    assert len(bg.tasks) == 1
    assert bg.tasks[0].args == (55, real_image)


def test_generate_panorama_downloads_external_image(tmp_path, monkeypatch):
    """外链（Unsplash 种子图）：下载到 views/front.jpg 后作为原图。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    payload = tmp_path / "remote.jpg"
    Image.new("RGB", (24, 24), color=(10, 120, 60)).save(payload, "JPEG")

    class _FakeResp:
        status_code = 200
        content = payload.read_bytes()

    calls = []
    # 外链下载逻辑已收敛到公共模块 image_utils，打桩点随之移动（断言意图不变）
    monkeypatch.setattr(
        image_utils.requests, "get",
        lambda url, timeout=30, headers=None: calls.append(url) or _FakeResp(),
    )
    _patch_item_row(monkeypatch, {"user_id": 18, "images": json.dumps([
        "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=800",
    ]), "panorama_status": "none"})

    bg = BackgroundTasks()
    resp = panorama_api.generate_panorama(panorama_api.PanoramaRequest(item_id=55), bg, user_id=18)
    assert resp["code"] == 0
    downloaded = tmp_path / "uploads" / "items" / "55" / "views" / "front.jpg"
    assert downloaded.is_file()
    assert bg.tasks[0].args == (55, downloaded)
    assert calls == ["https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=800"]


def test_generate_panorama_external_download_failure_400(monkeypatch, tmp_path):
    """外链下载失败 → 400「物品图片无法下载」，绝不把网络异常直接抛给用户。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    def _boom(url, timeout=30, headers=None):
        raise image_utils.requests.ConnectionError("network down")

    monkeypatch.setattr(image_utils.requests, "get", _boom)
    _patch_item_row(monkeypatch, {"user_id": 18, "images": json.dumps([
        "https://images.unsplash.com/photo-1",
    ]), "panorama_status": "none"})

    with pytest.raises(HTTPException) as exc:
        panorama_api.generate_panorama(
            panorama_api.PanoramaRequest(item_id=55), BackgroundTasks(), user_id=18,
        )
    assert exc.value.status_code == 400
    assert "无法下载" in exc.value.detail


def test_generate_panorama_rejects_generating(monkeypatch, tmp_path):
    """重复触发保护：正在生成中 → 400，不再并发烧模型额度。"""
    _patch_item_row(monkeypatch, {"user_id": 18, "images": json.dumps(["https://x/y.jpg"]), "panorama_status": "generating"})
    with pytest.raises(HTTPException) as exc:
        panorama_api.generate_panorama(
            panorama_api.PanoramaRequest(item_id=55), BackgroundTasks(), user_id=18,
        )
    assert exc.value.status_code == 400
    assert "请勿重复触发" in exc.value.detail


def test_generate_panorama_owner_only(monkeypatch, tmp_path):
    """非所有者触发 → 403（回归保护）。"""
    _patch_item_row(monkeypatch, {"user_id": 18, "images": json.dumps(["https://x/y.jpg"]), "panorama_status": "none"})
    with pytest.raises(HTTPException) as exc:
        panorama_api.generate_panorama(
            panorama_api.PanoramaRequest(item_id=55), BackgroundTasks(), user_id=99,
        )
    assert exc.value.status_code == 403
