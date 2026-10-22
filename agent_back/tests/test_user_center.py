"""个人中心第二 / 三 / 四区接口单元测试（我的物品 / 碳积分，数据库 mock，不连真实 MySQL）。

覆盖：
- 我的物品：分页、状态筛选、非法状态、images JSON 解析、状态标签映射、参数夹紧
- 下架：成功、非本人、物品不存在、状态不允许、并发下状态已变化
- 碳积分汇总：LV1 边界 / LV2 中段 / LV4 满级 / NULL 列兜底
- 积分明细：字段与来源标签、limit 夹紧、limit 非法
- 社区排名：COUNT 子查询口径、未设置社区时不做全站排名
"""
import pytest
from fastapi import HTTPException

from conftest import FakeCursor, make_connection, stub_image_signer

from app.api.v1 import user_center

USER_ID = 7


def _patch(monkeypatch, rows=None, rowcount=1):
    stub_image_signer(monkeypatch)  # 封面签名换成可读桩（见 conftest 说明）
    cursor = FakeCursor(rows=rows, rowcount=rowcount)
    monkeypatch.setattr(user_center, "connection", make_connection(cursor))
    return cursor


# ============================================================
# 我的物品：列表
# ============================================================
def test_list_my_items_basic_pagination(monkeypatch):
    """列表只查自己的物品，且带分页；默认第 1 页 10 条。"""
    cursor = _patch(monkeypatch, rows=[
        {"total": 2},
        {"id": 11, "title": "儿童自行车", "images": '["/api/v1/static/items/a.jpg?sig=x"]',
         "status": 1, "created_at": None},
        {"id": 10, "title": "旧书架", "images": None, "status": 2, "created_at": None},
    ])
    resp = user_center.list_my_items(status=None, page=1, size=10, user_id=USER_ID)

    assert resp["code"] == 0
    data = resp["data"]
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["size"] == 10
    assert [row["id"] for row in data["list"]] == [11, 10]

    count_sql, count_params = cursor.executed[0]
    assert count_sql == "SELECT COUNT(*) AS total FROM item WHERE user_id=%s"
    assert list(count_params) == [USER_ID]

    list_sql, list_params = cursor.executed[1]
    assert "FROM item WHERE user_id=%s ORDER BY id DESC" in list_sql
    assert list(list_params) == [USER_ID, 10, 0]


def test_list_my_items_status_filter(monkeypatch):
    """传 status 时追加状态条件，OFFSET 按页数计算。"""
    cursor = _patch(monkeypatch, rows=[
        {"total": 1},
        {"id": 3, "title": "台灯", "images": None, "status": 2, "created_at": None},
    ])
    resp = user_center.list_my_items(status=2, page=2, size=5, user_id=USER_ID)

    assert resp["data"]["total"] == 1
    count_sql, count_params = cursor.executed[0]
    assert "user_id=%s AND status=%s" in count_sql
    assert list(count_params) == [USER_ID, 2]
    # 第 2 页、每页 5 条 -> OFFSET 5
    assert list(cursor.executed[1][1]) == [USER_ID, 2, 5, 5]


def test_list_my_items_rejects_invalid_status(monkeypatch):
    """status 只允许 1/2/3/4，非法值在函数体内拦掉并给中文提示。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_center.list_my_items(status=9, page=1, size=10, user_id=USER_ID)
    assert exc.value.status_code == 400
    assert "status 取值不合法" in exc.value.detail
    assert cursor.executed == []


def test_list_my_items_parses_images_and_maps_status_labels(monkeypatch):
    """item.images 是 JSON 字符串，需安全解析；status 映射为中文标签。"""
    cursor = _patch(monkeypatch, rows=[
        {"total": 6},
        {"id": 1, "title": "a", "images": '["/a.jpg","/b.jpg"]', "status": 1, "created_at": None},
        {"id": 2, "title": "b", "images": ["/c.jpg"], "status": 2, "created_at": None},
        {"id": 3, "title": "c", "images": "not-json", "status": 3, "created_at": None},
        {"id": 4, "title": "d", "images": None, "status": 4, "created_at": None},
        {"id": 5, "title": "e", "images": "[]", "status": 1, "created_at": None},
        {"id": 6, "title": "f", "images": "/raw.jpg", "status": 2, "created_at": None},
    ])
    items = user_center.list_my_items(status=None, page=1, size=10, user_id=USER_ID)["data"]["list"]

    # JSON 字符串与已解析列表都取第一张；脏数据/空数组/None 一律降级为 None
    assert [row["cover"] for row in items] == ["/sign?a.jpg", "/sign?c.jpg", None, None, None, "/sign?raw.jpg"]
    assert [row["status_label"] for row in items] == [
        "在售", "已下架", "审核未通过", "审核中", "在售", "已下架",
    ]


def test_list_my_items_clamps_size_and_page(monkeypatch):
    """分页参数越界时夹紧（不报错）：size 上限 50，page 最小 1。"""
    cursor = _patch(monkeypatch, rows=[{"total": 0}])
    data = user_center.list_my_items(status=None, page=0, size=999, user_id=USER_ID)["data"]

    assert data["page"] == 1
    assert data["size"] == user_center.ITEM_LIST_MAX_SIZE
    assert list(cursor.executed[1][1]) == [USER_ID, user_center.ITEM_LIST_MAX_SIZE, 0]


# ============================================================
# 我的物品：下架
# ============================================================
def test_remove_my_item_success(monkeypatch):
    """下架自己的在售物品：status -> 2，SQL 带归属与状态双重条件。"""
    cursor = _patch(monkeypatch, rows=[{"id": 3, "user_id": USER_ID, "status": 1}])
    resp = user_center.remove_my_item(3, user_id=USER_ID)

    assert resp["message"] == "物品已下架"
    assert resp["data"] == {"id": 3, "status": 2, "status_label": "已下架"}

    update_sql, update_params = cursor.executed[1]
    assert update_sql == (
        "UPDATE item SET status=%s WHERE id=%s AND user_id=%s AND status IN (%s, %s)"
    )
    assert list(update_params) == [2, 3, USER_ID, 1, 4]


def test_remove_my_item_not_owned_returns_404_without_update(monkeypatch):
    """他人物品统一 404，且不下发任何 UPDATE（避免越权与 id 枚举）。"""
    cursor = _patch(monkeypatch, rows=[{"id": 3, "user_id": 8, "status": 1}])
    with pytest.raises(HTTPException) as exc:
        user_center.remove_my_item(3, user_id=USER_ID)

    assert exc.value.status_code == 404
    assert exc.value.detail == "物品不存在"
    assert len(cursor.executed) == 1


def test_remove_my_item_missing_returns_404(monkeypatch):
    """物品不存在时同样走 404 分支。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_center.remove_my_item(999, user_id=USER_ID)

    assert exc.value.status_code == 404
    assert len(cursor.executed) == 1


def test_remove_my_item_wrong_status_rejected(monkeypatch):
    """已下架(2) / 审核未通过(3) 不可再次下架。"""
    cursor = _patch(monkeypatch, rows=[{"id": 3, "user_id": USER_ID, "status": 2}])
    with pytest.raises(HTTPException) as exc:
        user_center.remove_my_item(3, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert "仅可下架" in exc.value.detail
    assert len(cursor.executed) == 1


def test_remove_my_item_concurrent_change_returns_400(monkeypatch):
    """检查通过后、写入前状态被并发改动（rowcount=0）时提示刷新重试。"""
    cursor = _patch(monkeypatch, rows=[{"id": 3, "user_id": USER_ID, "status": 1}], rowcount=0)
    with pytest.raises(HTTPException) as exc:
        user_center.remove_my_item(3, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert "请刷新后重试" in exc.value.detail


# ============================================================
# 碳积分汇总
# ============================================================
def _summary(monkeypatch, points, carbon_total=3.5, exchange_count=2):
    _patch(monkeypatch, rows=[{
        "points": points,
        "carbon_total": carbon_total,
        "exchange_count": exchange_count,
    }])
    return user_center.carbon_summary(USER_ID)["data"]


def test_carbon_summary_lv1_boundary(monkeypatch):
    """0 分落在 LV1，距 LV2 差 101 分，进度 0%。"""
    data = _summary(monkeypatch, 0)
    assert data["total_points"] == 0
    assert data["level"] == 1
    assert data["level_label"] == "LV1"
    assert data["next_level"] == "LV2"
    assert data["next_level_gap"] == 101
    assert data["progress_percent"] == 0


def test_carbon_summary_lv2_mid(monkeypatch):
    """130 分落在 LV2（101-500），距 LV3 差 371 分，进度 7%。"""
    data = _summary(monkeypatch, 130)
    assert data["level"] == 2
    assert data["next_level"] == "LV3"
    assert data["next_level_gap"] == 371
    assert data["progress_percent"] == 7
    # 碳减排量与交换次数是独立口径，原样透传
    assert data["carbon_total"] == 3.5
    assert data["exchange_count"] == 2


def test_carbon_summary_max_level(monkeypatch):
    """满级（>=1000）时无下一级，进度 100%。"""
    data = _summary(monkeypatch, 1500)
    assert data["level"] == 4
    assert data["next_level"] is None
    assert data["next_level_gap"] == 0
    assert data["progress_percent"] == 100


def test_carbon_summary_handles_null_columns(monkeypatch):
    """存量数据可能为 NULL，全部兜底为 0，不能抛异常。"""
    data = _summary(monkeypatch, None, carbon_total=None, exchange_count=None)
    assert data["total_points"] == 0
    assert data["carbon_total"] == 0.0
    assert data["exchange_count"] == 0
    assert data["level"] == 1


# ============================================================
# 积分明细
# ============================================================
def test_carbon_logs_returns_entries_with_source_label(monkeypatch):
    """明细按 id 倒序，source 转中文；未知 source 显示「其他」。"""
    cursor = _patch(monkeypatch, rows=[
        {"id": 9, "points": 20, "balance": 120, "source": 1, "related_id": 5,
         "description": "发布物品奖励：旧书", "created_at": None},
        {"id": 8, "points": -30, "balance": 100, "source": 5, "related_id": None,
         "description": "兑换消耗", "created_at": None},
        {"id": 7, "points": 10, "balance": 130, "source": 99, "related_id": None,
         "description": None, "created_at": None},
    ])
    data = user_center.carbon_logs(limit=10, user_id=USER_ID)["data"]

    assert data["limit"] == 10
    assert [row["source_label"] for row in data["list"]] == ["发布物品", "兑换消耗", "其他"]
    assert data["list"][1]["points"] == -30
    assert data["list"][0]["balance"] == 120

    sql, params = cursor.executed[0]
    assert "FROM points_log WHERE user_id=%s ORDER BY id DESC LIMIT %s" in sql
    assert list(params) == [USER_ID, 10]


def test_carbon_logs_limit_clamped_to_max(monkeypatch):
    """limit 超过上限时夹到 50，而不是报错。"""
    cursor = _patch(monkeypatch, rows=[])
    data = user_center.carbon_logs(limit=999, user_id=USER_ID)["data"]

    assert data["limit"] == user_center.CARBON_LOG_MAX_LIMIT
    assert data["list"] == []
    assert list(cursor.executed[0][1]) == [USER_ID, user_center.CARBON_LOG_MAX_LIMIT]


def test_carbon_logs_rejects_limit_below_one(monkeypatch):
    """limit < 1 属无意义请求，直接 400 且不触库。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_center.carbon_logs(limit=0, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert "limit 至少为 1" in exc.value.detail
    assert cursor.executed == []


# ============================================================
# 社区排名
# ============================================================
def test_carbon_rank_counts_higher_points(monkeypatch):
    """名次 = 同社区积分严格高于自己的人数 + 1；全程不用窗口函数。"""
    cursor = _patch(monkeypatch, rows=[
        {"community": "阳光小区", "points": 130},
        {"total": 12},
        {"higher": 3},
    ])
    data = user_center.carbon_rank(USER_ID)["data"]

    assert data == {"rank": 4, "total": 12, "community": "阳光小区"}
    rank_sql, rank_params = cursor.executed[2]
    assert "community=%s AND points > %s" in rank_sql
    assert list(rank_params) == ["阳光小区", 130]
    # 规避 MySQL 5.7：所有下发的 SQL 都不得出现窗口函数
    for sql, _ in cursor.executed:
        compact = sql.upper().replace(" ", "")
        assert "OVER(" not in compact
        assert "RANK()" not in compact


def test_carbon_rank_without_community_returns_none(monkeypatch):
    """未设置社区（NULL / 空白）时不做全站排名，避免口径误导。"""
    cursor = _patch(monkeypatch, rows=[{"community": "   ", "points": 130}])
    resp = user_center.carbon_rank(USER_ID)

    assert resp["data"] == {"rank": None, "total": 0, "community": None}
    assert resp["message"] == "未设置所在社区，暂无排名"
    assert len(cursor.executed) == 1
