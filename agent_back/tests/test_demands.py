"""我想要的（需求）单元测试（数据库 mock，不连真实 MySQL）。

覆盖：
- 发布：写入 status=1、标题必填 / 长度校验、可选字段空白归一为 None
- 我的需求列表：分页外壳、状态筛选、非法状态、参数夹紧
- 编辑：仅本人、仅「进行中」、只更新传入字段、空 body 拒绝
- 撤销（1→3）/ 完成（1→2）：状态流转与非法流转
- 公开需求墙：只返回进行中、只 SELECT 昵称与楼栋（无手机号）、
  登录时排除自己的需求、未登录时展示全部、limit 夹紧、category 过滤
- 迁移：ensure_demand_table 建表 + 两个索引、幂等跳过、失败不阻断启动

设计约定：公开墙与个人需求走**两个不同的 router**（路径分别是 /demands 与 /user/demands），
否则同路径同 method 会互相覆盖。
"""
import pymysql
import pytest
from fastapi import HTTPException

from conftest import FakeCursor, make_connection

from app.api.v1 import demand
from app.db import pool

USER_ID = 7
OTHER_USER_ID = 8
DEMAND_ID = 21


def _patch(monkeypatch, rows=None, rowcount=1, lastrowid=1):
    cursor = FakeCursor(rows=rows, rowcount=rowcount, lastrowid=lastrowid)
    monkeypatch.setattr(demand, "connection", make_connection(cursor))
    return cursor


def _sql_list(cursor):
    return [sql for sql, _ in cursor.executed]


def _demand_row(**overrides):
    row = {"user_id": USER_ID, "status": 1}
    row.update(overrides)
    return row


# ============================================================
# 发布
# ============================================================
def test_create_demand_inserts_ongoing(monkeypatch):
    """发布：写入 status=1，返回新 id 与状态标签。"""
    cursor = _patch(monkeypatch, rows=[], lastrowid=42)
    resp = demand.create_demand(
        demand.DemandCreate(title="想要一辆儿童自行车", description="九成新即可", category="运动"),
        user_id=USER_ID,
    )

    assert resp["code"] == 0
    assert resp["message"] == "需求发布成功"
    assert resp["data"] == {
        "id": 42,
        "title": "想要一辆儿童自行车",
        "status": demand.STATUS_ONGOING,
        "status_label": "进行中",
    }

    sql, params = cursor.executed[0]
    assert sql.startswith("INSERT INTO swap_demand")
    assert list(params) == [USER_ID, "想要一辆儿童自行车", "九成新即可", "运动", demand.STATUS_ONGOING]


def test_create_demand_normalizes_blank_optionals(monkeypatch):
    """描述 / 类别为空白串时归一为 NULL，避免库里出现空字符串语义。"""
    cursor = _patch(monkeypatch, rows=[], lastrowid=7)
    demand.create_demand(
        demand.DemandCreate(title="  求购绘本  ", description="   ", category=""),
        user_id=USER_ID,
    )

    _, params = cursor.executed[0]
    # 标题首尾空白被 strip；描述与类别变 None
    assert list(params) == [USER_ID, "求购绘本", None, None, demand.STATUS_ONGOING]


def test_create_demand_rejects_blank_title(monkeypatch):
    """标题必填：全空白 -> 400 且不下发 INSERT。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        demand.create_demand(demand.DemandCreate(title="   "), user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "请填写需求标题"
    assert cursor.executed == []


def test_create_demand_rejects_overlong_title(monkeypatch):
    """标题超过 100 字（对应 VARCHAR(100)）-> 400 中文提示。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        demand.create_demand(demand.DemandCreate(title="啊" * (demand.MAX_TITLE_LEN + 1)), user_id=USER_ID)

    assert exc.value.status_code == 400
    assert str(demand.MAX_TITLE_LEN) in exc.value.detail
    assert cursor.executed == []


def test_create_demand_rejects_overlong_category(monkeypatch):
    """期望类别超过 50 字（对应 VARCHAR(50)）-> 400。"""
    _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        demand.create_demand(
            demand.DemandCreate(title="标题", category="类" * (demand.MAX_CATEGORY_LEN + 1)),
            user_id=USER_ID,
        )
    assert exc.value.status_code == 400


# ============================================================
# 我的需求列表
# ============================================================
def test_list_my_demands_returns_pagination_shell(monkeypatch):
    """列表：COUNT + 明细，条件恒带 user_id，无状态筛选时不追加条件。"""
    cursor = _patch(monkeypatch, rows=[
        {"total": 2},
        {"id": 2, "title": "求购绘本", "description": None, "category": "图书",
         "status": 1, "created_at": None, "updated_at": None},
        {"id": 1, "title": "想要自行车", "description": "九成新", "category": "运动",
         "status": 3, "created_at": None, "updated_at": None},
    ])
    # 直连函数时必须显式传全部参数：FastAPI 的 Query(default) 只在其依赖注入时才会解析成默认值
    data = demand.list_my_demands(status=None, page=1, size=10, user_id=USER_ID)["data"]

    assert data["total"] == 2
    assert data["page"] == 1
    assert data["size"] == 10
    assert [row["id"] for row in data["list"]] == [2, 1]
    assert [row["status_label"] for row in data["list"]] == ["进行中", "已撤销"]

    count_sql, count_params = cursor.executed[0]
    assert count_sql == "SELECT COUNT(*) AS total FROM swap_demand WHERE user_id=%s"
    assert list(count_params) == [USER_ID]

    list_sql, list_params = cursor.executed[1]
    assert "FROM swap_demand WHERE user_id=%s ORDER BY id DESC LIMIT %s OFFSET %s" in list_sql
    assert list(list_params) == [USER_ID, 10, 0]


def test_list_my_demands_filters_by_status(monkeypatch):
    """状态筛选会追加 status 条件。"""
    cursor = _patch(monkeypatch, rows=[{"total": 0}])
    demand.list_my_demands(status=2, page=1, size=10, user_id=USER_ID)

    count_sql, count_params = cursor.executed[0]
    assert "user_id=%s AND status=%s" in count_sql
    assert list(count_params) == [USER_ID, 2]


def test_list_my_demands_rejects_invalid_status(monkeypatch):
    """只支持 1/2/3，其它值直接 400，避免拼出无意义查询。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        demand.list_my_demands(status=9, page=1, size=10, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "不支持的需求状态"
    assert cursor.executed == []


def test_list_my_demands_clamps_pagination(monkeypatch):
    """分页越界夹紧：page 最小 1，size 上限 50。"""
    cursor = _patch(monkeypatch, rows=[{"total": 0}])
    data = demand.list_my_demands(status=None, page=0, size=999, user_id=USER_ID)["data"]

    assert data["page"] == 1
    assert data["size"] == demand.DEMAND_LIST_MAX_SIZE
    assert list(cursor.executed[1][1]) == [USER_ID, demand.DEMAND_LIST_MAX_SIZE, 0]


# ============================================================
# 编辑 / 撤销 / 完成
# ============================================================
def test_update_demand_updates_only_provided_fields(monkeypatch):
    """只更新传入的字段，未传字段不出现在 SET 子句里。"""
    cursor = _patch(monkeypatch, rows=[_demand_row()])
    resp = demand.update_demand(DEMAND_ID, demand.DemandUpdate(title="改后的标题"), user_id=USER_ID)

    assert resp["message"] == "需求已更新"
    update_sql, update_params = cursor.executed[1]
    assert update_sql == "UPDATE swap_demand SET title=%s WHERE id=%s AND user_id=%s"
    assert list(update_params) == ["改后的标题", DEMAND_ID, USER_ID]


def test_update_demand_rejects_non_owner(monkeypatch):
    """非本人：404（与「不存在」同码，避免枚举他人需求）。"""
    cursor = _patch(monkeypatch, rows=[_demand_row(user_id=OTHER_USER_ID)])
    with pytest.raises(HTTPException) as exc:
        demand.update_demand(DEMAND_ID, demand.DemandUpdate(title="hack"), user_id=USER_ID)

    assert exc.value.status_code == 404
    assert exc.value.detail == "需求不存在"
    assert len(cursor.executed) == 1  # 只有查询，没有 UPDATE


def test_update_demand_rejects_non_ongoing(monkeypatch):
    """已完成 / 已撤销的需求不可编辑（保证终态语义稳定）。"""
    _patch(monkeypatch, rows=[_demand_row(status=demand.STATUS_DONE)])
    with pytest.raises(HTTPException) as exc:
        demand.update_demand(DEMAND_ID, demand.DemandUpdate(title="x"), user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "只有进行中的需求可以编辑"


def test_update_demand_requires_at_least_one_field(monkeypatch):
    """空 body 编辑 -> 400，不产生空 SET 的非法 SQL。"""
    _patch(monkeypatch, rows=[_demand_row()])
    with pytest.raises(HTTPException) as exc:
        demand.update_demand(DEMAND_ID, demand.DemandUpdate(), user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "没有需要修改的内容"


def test_cancel_demand_transitions_to_cancelled(monkeypatch):
    """撤销：1 -> 3。"""
    cursor = _patch(monkeypatch, rows=[_demand_row()])
    resp = demand.cancel_demand(DEMAND_ID, user_id=USER_ID)

    assert resp["message"] == "需求已撤销"
    assert resp["data"] == {"id": DEMAND_ID, "status": demand.STATUS_CANCELLED, "status_label": "已撤销"}

    sql, params = cursor.executed[1]
    assert sql == "UPDATE swap_demand SET status=%s WHERE id=%s AND user_id=%s"
    assert list(params) == [demand.STATUS_CANCELLED, DEMAND_ID, USER_ID]


def test_complete_demand_transitions_to_done(monkeypatch):
    """完成：1 -> 2。"""
    cursor = _patch(monkeypatch, rows=[_demand_row()])
    resp = demand.complete_demand(DEMAND_ID, user_id=USER_ID)

    assert resp["message"] == "已标记为完成"
    assert resp["data"]["status"] == demand.STATUS_DONE
    assert list(cursor.executed[1][1]) == [demand.STATUS_DONE, DEMAND_ID, USER_ID]


def test_complete_demand_rejects_already_done(monkeypatch):
    """终态不可再次流转（幂等由前端禁按钮 + 这里的状态校验双重保证）。"""
    _patch(monkeypatch, rows=[_demand_row(status=demand.STATUS_CANCELLED)])
    with pytest.raises(HTTPException) as exc:
        demand.complete_demand(DEMAND_ID, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "只有进行中的需求可以标记完成"


# ============================================================
# 公开需求墙
# ============================================================
def test_wall_returns_only_ongoing_and_public_fields(monkeypatch):
    """公开墙：SQL 只取 id/user_id/title/category/created_at + 昵称/楼栋，绝不查手机号。"""
    cursor = _patch(monkeypatch, rows=[
        {"id": 5, "user_id": OTHER_USER_ID, "title": "求购绘本", "category": "图书",
         "created_at": None, "nickname": "刘洋", "building": "3 栋"},
    ])
    data = demand.list_demand_wall(limit=6, category=None, viewer_id=None)["data"]

    sql, params = cursor.executed[0]
    assert "u.nickname" in sql and "u.building" in sql
    # 隐私：不得出现 phone / email / contact / password 等字段
    lowered = sql.lower()
    for forbidden in ("phone", "email", "contact", "password", "real_name", "id_card"):
        assert forbidden not in lowered
    assert "d.status=%s" in sql
    assert "JOIN user u ON d.user_id = u.id" in sql
    assert list(params) == [demand.STATUS_ONGOING, 6]

    assert data["list"][0]["nickname"] == "刘洋"
    assert data["list"][0]["building"] == "3 栋"
    assert data["list"][0]["user_id"] == OTHER_USER_ID
    # 返回体字段集合固定，没有多余隐私字段被带出
    assert set(data["list"][0].keys()) == {
        "id", "user_id", "title", "category", "nickname", "building", "created_at",
    }


def test_wall_excludes_viewer_own_demands_when_logged_in(monkeypatch):
    """登录后排除自己的需求（避免自己看到自己的）。"""
    cursor = _patch(monkeypatch, rows=[])
    demand.list_demand_wall(limit=6, category=None, viewer_id=USER_ID)

    sql, params = cursor.executed[0]
    assert "d.user_id<>%s" in sql
    assert list(params) == [demand.STATUS_ONGOING, USER_ID, 6]


def test_wall_shows_all_when_anonymous(monkeypatch):
    """未登录（viewer_id=None）时无「自己」概念，不追加排除条件。"""
    cursor = _patch(monkeypatch, rows=[])
    demand.list_demand_wall(limit=6, category=None, viewer_id=None)

    sql, params = cursor.executed[0]
    assert "user_id<>" not in sql
    assert list(params) == [demand.STATUS_ONGOING, 6]


def test_wall_clamps_limit(monkeypatch):
    """limit 越界夹紧：上限 20、下限 1。"""
    cursor = _patch(monkeypatch, rows=[])
    demand.list_demand_wall(limit=999, category=None, viewer_id=None)
    assert list(cursor.executed[0][1]) == [demand.STATUS_ONGOING, demand.WALL_MAX_LIMIT]

    cursor2 = _patch(monkeypatch, rows=[])
    demand.list_demand_wall(limit=0, category=None, viewer_id=None)
    assert list(cursor2.executed[0][1]) == [demand.STATUS_ONGOING, 1]


def test_wall_filters_by_category(monkeypatch):
    """category 非空时追加筛选条件并 strip。"""
    cursor = _patch(monkeypatch, rows=[])
    demand.list_demand_wall(limit=6, category="  图书  ", viewer_id=None)

    sql, params = cursor.executed[0]
    assert "d.category=%s" in sql
    assert list(params) == [demand.STATUS_ONGOING, "图书", 6]


def test_wall_falls_back_nickname_when_missing(monkeypatch):
    """昵称缺失时回落到「社区邻居」，不返回空串或 null 给前端。"""
    _patch(monkeypatch, rows=[
        {"id": 5, "user_id": OTHER_USER_ID, "title": "求购绘本", "category": None,
         "created_at": None, "nickname": "   ", "building": None},
    ])
    row = demand.list_demand_wall(limit=6, category=None, viewer_id=None)["data"]["list"][0]

    assert row["nickname"] == "社区邻居"
    assert row["building"] is None


# ============================================================
# 迁移：ensure_demand_table
# ============================================================
def test_ensure_demand_table_creates_indexes_when_absent(monkeypatch):
    """索引不存在时建 idx_user_status 与 idx_status_created，键名与列序必须精确。"""
    cursor = FakeCursor(rows=[{"c": 0}, {"c": 0}])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_demand_table()

    sqls = _sql_list(cursor)
    assert any(s.startswith("CREATE TABLE IF NOT EXISTS `swap_demand`") for s in sqls)
    alters = [s for s in sqls if s.startswith("ALTER TABLE")]
    assert len(alters) == 2
    assert pool.DEMAND_USER_STATUS_INDEX in alters[0]
    assert "(user_id, status)" in alters[0]
    assert pool.DEMAND_STATUS_CREATED_INDEX in alters[1]
    assert "(status, created_at)" in alters[1]


def test_ensure_demand_table_is_idempotent(monkeypatch):
    """索引已存在时不产生任何 ALTER（ALTER 非幂等，重复执行会报 Duplicate key name）。"""
    cursor = FakeCursor(rows=[{"c": 1}, {"c": 1}])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_demand_table()

    assert not any(sql.startswith("ALTER TABLE") for sql in _sql_list(cursor))


def test_ensure_demand_table_does_not_block_startup(monkeypatch):
    """建表失败时只告警，不能阻断后端启动。"""

    class FailingCursor(FakeCursor):
        def execute(self, sql, params=None):
            if sql.startswith("CREATE TABLE"):
                raise pymysql.err.OperationalError(1050, "Table already exists")
            return super().execute(sql, params)

    cursor = FailingCursor(rows=[{"c": 0}, {"c": 0}])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_demand_table()  # 不抛异常即通过
