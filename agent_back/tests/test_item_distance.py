"""item API「离我最近」（距离排序）单元测试。

覆盖范围：
- 未登录且未传参照坐标            -> 400 + 明确中文提示
- 已登录但未保存位置              -> 200 + need_location 引导（不是错误）
- 坐标为 0,0 占位                 -> 视为未设置
- 已登录且已保存位置              -> 按距离升序；未公开位置的物品排在末尾且不带 distance_km
- 查看自己的物品                  -> 不受 user.location_public 限制
- 显式 latitude/longitude 参数    -> 直接生效，且不再回查 user 表
- 不支持的排序方式                -> 400

DB 用 conftest 的 FakeCursor 假连接，不连真实 MySQL。
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from conftest import FakeCursor, make_connection

from app.api.v1 import item as item_api


def _patch_db(monkeypatch, rows):
    cursor = FakeCursor(rows=rows)
    monkeypatch.setattr("app.api.v1.item.connection", make_connection(cursor))
    return cursor


def _item(item_id, owner_id, owner_lat, owner_lng, public, item_lat=None, item_lng=None):
    """构造一行「含所有者坐标」的物品查询结果。"""
    return {
        "id": item_id,
        "user_id": owner_id,
        "title": f"物品{item_id}",
        "images": None,
        "status": 1,
        "latitude": item_lat,
        "longitude": item_lng,
        "owner_latitude": Decimal(owner_lat),
        "owner_longitude": Decimal(owner_lng),
        "owner_location_public": public,
    }


def test_distance_sort_requires_login_when_no_coords(monkeypatch):
    """未登录且未传坐标：无法确定参照点，返回 400 + 明确提示。

    注意：直接调用时 viewer_id 需显式传 None（否则拿到的是 Depends 默认对象，
    与 HTTP 请求下 FastAPI 解析出的 None 不等价）。
    """
    _patch_db(monkeypatch, [])
    with pytest.raises(HTTPException) as exc:
        item_api.list_items(sort_by="distance", page=1, size=12, viewer_id=None)
    assert exc.value.status_code == 400
    assert "设置您的位置" in exc.value.detail


def test_distance_sort_prompts_when_location_not_set(monkeypatch):
    """已登录但库里没有坐标：不报错，返回 need_location 引导。"""
    _patch_db(monkeypatch, [{"latitude": None, "longitude": None}])
    result = item_api.list_items(sort_by="distance", page=1, size=12, viewer_id=18)
    assert result["code"] == 0
    assert result["data"]["need_location"] is True
    assert result["data"]["items"] == []
    assert "设置您的位置" in result["message"]


def test_zero_coordinates_treated_as_unset(monkeypatch):
    """0,0 是「未设置」的占位值，不应被当成真实坐标。"""
    _patch_db(monkeypatch, [{"latitude": 0, "longitude": 0}])
    result = item_api.list_items(sort_by="distance", page=1, size=12, viewer_id=7)
    assert result["data"]["need_location"] is True


def test_distance_sort_orders_by_distance_and_applies_privacy(monkeypatch):
    """按距离升序；所有者未公开位置的物品排在末尾且不返回 distance_km。"""
    rows = [
        # 第 1 次查询：登录用户已保存的坐标
        {"latitude": Decimal("37.5000000"), "longitude": Decimal("111.1000000")},
        # 第 2 次查询：物品列表（item 自身无坐标，回退到所有者坐标）
        _item(1, 2, "37.5100000", "111.1000000", public=1),   # 近
        _item(2, 3, "38.5000000", "112.0000000", public=1),   # 远
        _item(3, 4, "37.5100000", "111.1000000", public=0),   # 未公开 -> 不参与排序
    ]
    _patch_db(monkeypatch, rows)

    result = item_api.list_items(sort_by="distance", page=1, size=12, viewer_id=5)
    data = result["data"]

    assert data["distance_sorted"] is True
    assert data["nearby_count"] == 2
    assert [it["id"] for it in data["items"]] == [1, 2, 3]
    assert data["items"][0]["distance_km"] < data["items"][1]["distance_km"]
    assert data["items"][2].get("distance_km") is None
    assert "need_location" not in data


def test_distance_sort_includes_own_items_even_when_not_public(monkeypatch):
    """查看者自己的物品始终可见（不受其 location_public 影响）。"""
    rows = [
        {"latitude": Decimal("37.5000000"), "longitude": Decimal("111.1000000")},
        _item(9, 5, "37.5000000", "111.1000000", public=0),
    ]
    _patch_db(monkeypatch, rows)

    result = item_api.list_items(sort_by="distance", page=1, size=12, viewer_id=5)
    assert result["data"]["nearby_count"] == 1
    assert result["data"]["items"][0]["id"] == 9
    assert result["data"]["items"][0]["distance_km"] == 0.0


def test_distance_sort_with_explicit_coords_skips_user_lookup(monkeypatch):
    """显式传坐标时不回查 user 表；未登录时仅公开位置的所有者参与排序。"""
    cursor = _patch_db(monkeypatch, [
        _item(1, 2, "37.5100000", "111.1000000", public=1),
        _item(2, 3, "37.5100000", "111.1000000", public=0),
    ])

    result = item_api.list_items(
        sort_by="distance", page=1, size=12, latitude=37.5, longitude=111.1, viewer_id=None,
    )
    assert result["data"]["nearby_count"] == 1
    assert [it["id"] for it in result["data"]["items"]] == [1, 2]
    # 只执行了 1 条 SQL（物品查询），没有查 user 表的坐标
    assert len(cursor.executed) == 1


def test_item_coordinates_take_priority_over_owner(monkeypatch):
    """物品自身坐标优先于所有者坐标。"""
    rows = [
        _item(1, 2, "38.5000000", "112.0000000", public=1,
              item_lat=Decimal("37.5000000"), item_lng=Decimal("111.1000000")),
    ]
    _patch_db(monkeypatch, rows)

    result = item_api.list_items(
        sort_by="distance", page=1, size=12, latitude=37.5, longitude=111.1, viewer_id=None,
    )
    assert result["data"]["items"][0]["distance_km"] == 0.0


def test_unsupported_sort_still_rejected(monkeypatch):
    """距离之外的白名单仍生效：非法排序值返回 400。"""
    _patch_db(monkeypatch, [])
    with pytest.raises(HTTPException) as exc:
        item_api.list_items(sort_by="hack", page=1, size=12)
    assert exc.value.status_code == 400
