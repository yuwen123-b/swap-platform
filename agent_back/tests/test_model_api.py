"""3D 模型接口测试：开关硬校验、归属校验、重复触发保护、后台任务注册。

与 panorama 接口测试同套路——SQL 走 conftest 的 FakeCursor，断言集中在
「HTTP 语义 + 后台任务参数」，真实链路在《验证清单》中单独说明。
"""
import json

import pytest
from conftest import FakeCursor, make_connection
from fastapi import HTTPException
from starlette.background import BackgroundTasks

from app.api.v1 import item as item_api
from app.api.v1 import model as model_api

USER_ID = 7


def _patch(monkeypatch, row, *, enabled=True):
    cursor = FakeCursor(rows=[row] if row else [])
    monkeypatch.setattr("app.api.v1.model.connection", make_connection(cursor))
    # 开关读的是真实 settings 单例（与 three_d_service.is_enabled 同源）
    monkeypatch.setattr(model_api.three_d_service.settings, "model_3d_enabled", enabled)
    return cursor


def _item_row(**overrides):
    row = {"user_id": USER_ID, "images": json.dumps(["https://x/y.jpg"]), "model_status": "none"}
    row.update(overrides)
    return row


def _call(item_id=9, user_id=USER_ID):
    return model_api.generate_model(
        model_api.ModelGenerateRequest(item_id=item_id), BackgroundTasks(), user_id=user_id
    )


# ============================================================
# 开关 / 归属 / 状态前置
# ============================================================
def test_generate_model_disabled_403(monkeypatch):
    """开关关闭：即便前端绕过隐藏按钮直接打接口，也必须被 403 拦下（防白烧额度）。"""
    _patch(monkeypatch, _item_row(), enabled=False)
    with pytest.raises(HTTPException) as exc:
        _call()
    assert exc.value.status_code == 403
    assert "未开启" in exc.value.detail


def test_generate_model_not_found_404(monkeypatch):
    _patch(monkeypatch, None)
    with pytest.raises(HTTPException) as exc:
        _call()
    assert exc.value.status_code == 404


def test_generate_model_owner_only_403(monkeypatch):
    _patch(monkeypatch, _item_row())
    with pytest.raises(HTTPException) as exc:
        _call(user_id=99)
    assert exc.value.status_code == 403
    assert "无权" in exc.value.detail


def test_generate_model_rejects_generating(monkeypatch):
    """重复触发保护：生成中再触发 → 400，避免并发烧 2~3.5 元/次。"""
    _patch(monkeypatch, _item_row(model_status="generating"))
    with pytest.raises(HTTPException) as exc:
        _call()
    assert exc.value.status_code == 400
    assert "请勿重复触发" in exc.value.detail


def test_generate_model_without_image_400(monkeypatch):
    _patch(monkeypatch, _item_row(images=None))
    with pytest.raises(HTTPException) as exc:
        _call()
    assert exc.value.status_code == 400
    assert "没有图片" in exc.value.detail


def test_generate_model_bad_images_json_400(monkeypatch):
    _patch(monkeypatch, _item_row(images="not-json"))
    with pytest.raises(HTTPException) as exc:
        _call()
    assert exc.value.status_code == 400
    assert "格式错误" in exc.value.detail


# ============================================================
# 正常触发
# ============================================================
def test_generate_model_registers_background_task(monkeypatch):
    _patch(monkeypatch, _item_row())
    bg = BackgroundTasks()
    resp = model_api.generate_model(
        model_api.ModelGenerateRequest(item_id=9), bg, user_id=USER_ID
    )

    assert resp["code"] == 0
    assert resp["data"] == {"item_id": 9, "status": "generating"}
    # 直调函数时 BackgroundTasks 不执行，断言任务已按正确参数注册
    assert len(bg.tasks) == 1
    assert bg.tasks[0].args == (9,)


def test_generate_model_allows_retry_after_failed(monkeypatch):
    """failed 状态可重新触发（与 generating 的拒绝形成对照）。"""
    _patch(monkeypatch, _item_row(model_status="failed"))
    bg = BackgroundTasks()
    resp = model_api.generate_model(
        model_api.ModelGenerateRequest(item_id=5), bg, user_id=USER_ID
    )
    assert resp["code"] == 0
    assert len(bg.tasks) == 1


# ============================================================
# 查询接口
# ============================================================
def test_get_model_endpoint_ok(monkeypatch):
    monkeypatch.setattr(
        model_api.three_d_service, "get_model",
        lambda item_id: {"item_id": item_id, "model_status": "ready", "model_url": "u"},
    )
    resp = model_api.get_model(5)
    assert resp["code"] == 0
    assert resp["data"]["model_status"] == "ready"


def test_get_model_endpoint_404(monkeypatch):
    def _boom(item_id):
        raise ValueError("物品不存在")

    monkeypatch.setattr(model_api.three_d_service, "get_model", _boom)
    with pytest.raises(HTTPException) as exc:
        model_api.get_model(404)
    assert exc.value.status_code == 404


def test_get_model_endpoint_passes_through_error(monkeypatch):
    """失败原因必须一路透到前端，否则用户只会看到「failed」三个字母。"""
    monkeypatch.setattr(
        model_api.three_d_service, "get_model",
        lambda item_id: {
            "item_id": item_id, "model_status": "failed", "model_url": None,
            "model_error": "The product is not activated",
        },
    )
    resp = model_api.get_model(5)
    assert resp["data"]["model_error"] == "The product is not activated"


# ============================================================
# 详情接口透出 model_error（前端「为什么失败」的唯一来源）
# ============================================================
class _Settings:
    def __init__(self, upload_dir="/tmp"):
        self.upload_dir = upload_dir
        self.api_prefix = "/api/v1"


def _item_detail(monkeypatch, **overrides):
    row = {
        "id": 9, "title": "沙发", "description": "d",
        "exchange_mode": 1, "price": "0.00", "images": None,
        "panorama_status": "none", "panorama_views": None,
        "model_status": "none", "model_url": None, "model_error": None,
    }
    row.update(overrides)
    monkeypatch.setattr(item_api, "connection", make_connection(FakeCursor(rows=[row])))
    monkeypatch.setattr(item_api, "settings", _Settings())
    monkeypatch.setattr(model_api.three_d_service.settings, "model_3d_enabled", True)
    return item_api.get_item(9)["data"]


def test_item_detail_exposes_model_error_when_failed(monkeypatch):
    data = _item_detail(monkeypatch, model_status="failed",
                        model_error="The product is not activated")
    assert data["model_status"] == "failed"
    assert data["model_error"] == "The product is not activated"
    assert data["model_3d_enabled"] is True


@pytest.mark.parametrize("status", ["none", "generating", "ready"])
def test_item_detail_hides_model_error_unless_failed(monkeypatch, status):
    """非 failed 状态即使列里残留旧错因也不外泄，避免误导下一次排查。"""
    data = _item_detail(monkeypatch, model_status=status, model_error="上一轮的旧错因")
    assert data["model_error"] is None


def test_item_detail_survives_missing_model_error_column(monkeypatch):
    """迁移前的旧行没有 model_error 键，不能抛 KeyError。"""
    row = {
        "id": 9, "title": "沙发", "exchange_mode": 1, "price": "0.00",
        "images": None, "panorama_status": "none", "panorama_views": None,
        "model_status": "failed",
    }
    monkeypatch.setattr(item_api, "connection", make_connection(FakeCursor(rows=[row])))
    monkeypatch.setattr(item_api, "settings", _Settings())
    assert item_api.get_item(9)["data"]["model_error"] is None
