"""item API 单元测试：get_item 的 panorama 字段整形。"""
import json
import pytest
from conftest import FakeCursor, make_connection
from app.api.v1 import item as item_api


def _patch_db(monkeypatch, rows):
    cursor = FakeCursor(rows=rows)
    monkeypatch.setattr("app.api.v1.item.connection", make_connection(cursor))
    return cursor


def test_get_item_panorama_ready(monkeypatch):
    """ready 状态：panorama_views 为 dict（从 JSON 解析出的 views 子对象）。"""
    views_json = json.dumps({"views": {"front": "/f.jpg", "left": "/l.jpg"}, "fallback": False})
    _patch_db(monkeypatch, [{
        "id": 1, "title": "Test", "description": "Desc",
        "panorama_status": "ready", "panorama_views": views_json,
    }])
    result = item_api.get_item(1)
    assert result["code"] == 0
    assert result["data"]["panorama_status"] == "ready"
    assert result["data"]["panorama_views"]["front"] == "/f.jpg"


def test_get_item_panorama_generating(monkeypatch):
    """generating 状态：panorama_views 为 None。"""
    _patch_db(monkeypatch, [{
        "id": 2, "title": "Test", "description": "Desc",
        "panorama_status": "generating", "panorama_views": None,
    }])
    result = item_api.get_item(2)
    assert result["data"]["panorama_status"] == "generating"
    assert result["data"]["panorama_views"] is None


def test_get_item_panorama_bad_json(monkeypatch):
    """坏 JSON：panorama_views 静默降级为 None。"""
    _patch_db(monkeypatch, [{
        "id": 3, "title": "Test", "description": "Desc",
        "panorama_status": "ready", "panorama_views": "not-valid-json",
    }])
    result = item_api.get_item(3)
    assert result["data"]["panorama_status"] == "ready"
    assert result["data"]["panorama_views"] is None
