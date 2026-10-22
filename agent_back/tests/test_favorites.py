"""我的收藏 单元测试（数据库 mock，不连真实 MySQL）。

覆盖：
- 收藏 / 取消收藏：新增、重复收藏（幂等）、取消、未收藏取消、物品不存在
- 收藏列表：分页外壳、LEFT JOIN 取物品字段、物品已删除的降级展示、参数夹紧
- 是否已收藏：已收藏 / 未收藏
- 迁移：ensure_personal_center_tables 建表建索引、幂等跳过、失败不阻断启动

设计约定：favorite 表复用既有表并通过 uk_user_item(user_id, item_id) 唯一索引
保证幂等；应用层同时用 INSERT IGNORE 兜底，重复点击不产生重复行。
"""
import pymysql
import pytest
from fastapi import HTTPException

from conftest import FakeCursor, make_connection, stub_image_signer

from app.api.v1 import favorite
from app.db import pool

USER_ID = 7
ITEM_ID = 55


def _patch(monkeypatch, rows=None, rowcount=1):
    stub_image_signer(monkeypatch)  # 封面签名换成可读桩（见 conftest 说明）
    cursor = FakeCursor(rows=rows, rowcount=rowcount)
    monkeypatch.setattr(favorite, "connection", make_connection(cursor))
    return cursor


def _sql_list(cursor):
    return [sql for sql, _ in cursor.executed]


# ============================================================
# 收藏 / 取消收藏
# ============================================================
def test_add_favorite_creates_row(monkeypatch):
    """首次收藏：校验物品存在后 INSERT IGNORE，created=True。"""
    cursor = _patch(monkeypatch, rows=[{"id": ITEM_ID}], rowcount=1)
    resp = favorite.add_favorite(ITEM_ID, user_id=USER_ID)

    assert resp["code"] == 0
    assert resp["message"] == "收藏成功"
    assert resp["data"] == {"item_id": ITEM_ID, "favorited": True, "created": True}

    sqls = _sql_list(cursor)
    assert sqls[0] == "SELECT id FROM item WHERE id=%s LIMIT 1"
    insert_sql, insert_params = cursor.executed[1]
    assert insert_sql == "INSERT IGNORE INTO favorite (user_id, item_id) VALUES (%s, %s)"
    assert list(insert_params) == [USER_ID, ITEM_ID]


def test_add_favorite_is_idempotent_when_already_exists(monkeypatch):
    """重复收藏：INSERT IGNORE 命中唯一索引后 rowcount=0，返回已收藏而非报错。"""
    cursor = _patch(monkeypatch, rows=[{"id": ITEM_ID}], rowcount=0)
    resp = favorite.add_favorite(ITEM_ID, user_id=USER_ID)

    assert resp["data"] == {"item_id": ITEM_ID, "favorited": True, "created": False}
    assert resp["message"] == "你已收藏过该物品"
    # 仍然只有一条 INSERT，没有额外 UPDATE/补偿逻辑
    assert len(_sql_list(cursor)) == 2


def test_add_favorite_missing_item_returns_404(monkeypatch):
    """物品不存在：404 且不下发任何写入。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        favorite.add_favorite(999, user_id=USER_ID)

    assert exc.value.status_code == 404
    assert exc.value.detail == "物品不存在"
    assert _sql_list(cursor) == ["SELECT id FROM item WHERE id=%s LIMIT 1"]


def test_remove_favorite_deletes_own_row(monkeypatch):
    """取消收藏：DELETE 条件必须同时带 user_id 与 item_id，避免删他人收藏。"""
    cursor = _patch(monkeypatch, rows=[], rowcount=1)
    resp = favorite.remove_favorite(ITEM_ID, user_id=USER_ID)

    assert resp["message"] == "已取消收藏"
    assert resp["data"] == {"item_id": ITEM_ID, "favorited": False, "removed": True}

    sql, params = cursor.executed[0]
    assert sql == "DELETE FROM favorite WHERE user_id=%s AND item_id=%s"
    assert list(params) == [USER_ID, ITEM_ID]


def test_remove_favorite_without_row_is_still_success(monkeypatch):
    """未收藏时取消：幂等返回成功，仅 removed=False。"""
    _patch(monkeypatch, rows=[], rowcount=0)
    resp = favorite.remove_favorite(ITEM_ID, user_id=USER_ID)

    assert resp["data"]["removed"] is False
    assert resp["message"] == "尚未收藏该物品"


# ============================================================
# 收藏列表
# ============================================================
def test_list_favorites_returns_items_with_item_fields(monkeypatch):
    """列表用 LEFT JOIN 取物品字段，按 favorite.id 倒序。"""
    cursor = _patch(monkeypatch, rows=[
        {"total": 2},
        {"favorite_id": 9, "favorited_at": None, "item_id_raw": 55,
         "title": "复古胶片相机", "images": '["/api/v1/static/items/a.jpg?sig=x"]', "status": 1},
        {"favorite_id": 8, "favorited_at": None, "item_id_raw": 40,
         "title": "旧书架", "images": None, "status": 2},
    ])
    data = favorite.list_favorites(page=1, size=10, user_id=USER_ID)["data"]

    assert data["total"] == 2
    assert data["page"] == 1
    assert data["size"] == 10
    assert [row["favorite_id"] for row in data["list"]] == [9, 8]
    # id 取 item.id（供前端跳详情），不是 favorite.id
    assert [row["id"] for row in data["list"]] == [55, 40]
    assert data["list"][0]["cover"] == "/sign?items/a.jpg"
    assert [row["status_label"] for row in data["list"]] == ["在售", "已下架"]

    count_sql, count_params = cursor.executed[0]
    assert count_sql == "SELECT COUNT(*) AS total FROM favorite WHERE user_id=%s"
    assert list(count_params) == [USER_ID]

    list_sql, list_params = cursor.executed[1]
    assert "LEFT JOIN item i ON f.item_id = i.id" in list_sql
    assert "WHERE f.user_id=%s ORDER BY f.id DESC" in list_sql
    assert list(list_params) == [USER_ID, 10, 0]


def test_list_favorites_marks_deleted_item(monkeypatch):
    """物品被删除（LEFT JOIN 取不到 item）时给出「物品已不存在」，不误报成某个状态。"""
    _patch(monkeypatch, rows=[
        {"total": 1},
        {"favorite_id": 3, "favorited_at": None, "item_id_raw": None,
         "title": None, "images": None, "status": None},
    ])
    row = favorite.list_favorites(page=1, size=10, user_id=USER_ID)["data"]["list"][0]

    assert row["id"] == 0
    assert row["title"] == ""
    assert row["cover"] is None
    assert row["status_label"] == favorite.MISSING_ITEM_LABEL


def test_list_favorites_clamps_pagination(monkeypatch):
    """分页参数越界时夹紧：size 上限 50，page 最小 1。"""
    cursor = _patch(monkeypatch, rows=[{"total": 0}])
    data = favorite.list_favorites(page=0, size=999, user_id=USER_ID)["data"]

    assert data["page"] == 1
    assert data["size"] == favorite.FAVORITE_LIST_MAX_SIZE
    assert list(cursor.executed[1][1]) == [USER_ID, favorite.FAVORITE_LIST_MAX_SIZE, 0]


def test_list_favorites_parses_dirty_images_safely(monkeypatch):
    """item.images 脏数据（非 JSON / 空数组 / 裸路径）不得让列表 500。"""
    _patch(monkeypatch, rows=[
        {"total": 3},
        {"favorite_id": 3, "favorited_at": None, "item_id_raw": 1,
         "title": "a", "images": "not-json", "status": 1},
        {"favorite_id": 2, "favorited_at": None, "item_id_raw": 2,
         "title": "b", "images": "[]", "status": 1},
        {"favorite_id": 1, "favorited_at": None, "item_id_raw": 3,
         "title": "c", "images": "/raw.jpg", "status": 1},
    ])
    rows = favorite.list_favorites(page=1, size=10, user_id=USER_ID)["data"]["list"]

    assert [row["cover"] for row in rows] == [None, None, "/sign?raw.jpg"]


# ============================================================
# 是否已收藏
# ============================================================
def test_check_favorite_true(monkeypatch):
    """已收藏时 favorited=True（详情页据此渲染实心心形）。"""
    cursor = _patch(monkeypatch, rows=[{"ok": 1}])
    resp = favorite.check_favorite(ITEM_ID, user_id=USER_ID)

    assert resp["data"] == {"item_id": ITEM_ID, "favorited": True}
    assert list(cursor.executed[0][1]) == [USER_ID, ITEM_ID]


def test_check_favorite_false(monkeypatch):
    """未收藏时 favorited=False，且不因此报 404（纯查询无副作用）。"""
    _patch(monkeypatch, rows=[])
    assert favorite.check_favorite(ITEM_ID, user_id=USER_ID)["data"]["favorited"] is False


# ============================================================
# 迁移：ensure_personal_center_tables
# ============================================================
def test_ensure_personal_center_tables_creates_indexes_when_absent(monkeypatch):
    """索引不存在时建 uk_user_item 与 idx_user_created，两个键名与列序必须精确。"""
    cursor = FakeCursor(rows=[{"c": 0}, {"c": 0}])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_personal_center_tables()

    sqls = _sql_list(cursor)
    assert any(s.startswith("CREATE TABLE IF NOT EXISTS `favorite`") for s in sqls)
    alters = [s for s in sqls if s.startswith("ALTER TABLE")]
    assert len(alters) == 2
    assert pool.FAVORITE_UNIQUE_INDEX in alters[0]
    assert "(user_id, item_id)" in alters[0]
    assert pool.FAVORITE_USER_CREATED_INDEX in alters[1]
    assert "(user_id, created_at)" in alters[1]


def test_ensure_personal_center_tables_is_idempotent(monkeypatch):
    """索引已存在时不产生任何 ALTER（ALTER 非幂等，重复执行会报 Duplicate key name）。"""
    cursor = FakeCursor(rows=[{"c": 1}, {"c": 1}])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_personal_center_tables()

    assert not any(sql.startswith("ALTER TABLE") for sql in _sql_list(cursor))


def test_ensure_personal_center_tables_does_not_block_startup(monkeypatch):
    """存量有重复收藏导致建唯一索引失败时只告警，不能阻断后端启动。"""

    class FailingAlterCursor(FakeCursor):
        def execute(self, sql, params=None):
            if sql.startswith("ALTER TABLE"):
                raise pymysql.err.IntegrityError(1062, "Duplicate entry")
            return super().execute(sql, params)

    cursor = FailingAlterCursor(rows=[{"c": 0}, {"c": 0}])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_personal_center_tables()  # 不抛异常即通过
