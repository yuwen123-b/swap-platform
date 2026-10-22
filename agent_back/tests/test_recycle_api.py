"""平台回收（二期）单元测试（数据库 mock，不连真实 MySQL）。

覆盖（《变更影响分析》9.1 计划）：
- 估价公式：成色各档取值、越界回落 0 档、结果恒在 [10, 500]
- 提交回收：立即得积分（source=8 + related_id=回收单id）、status=4 也能提交（D3）、
  非本人 403、重复回收拒绝、item 四字段落库
- 取件方式：method=1 地址可空、method=2 地址必填、method 非法 400
- 取消：source=9 退分（不撞 uk_points_log_source）、状态门、非本人 403、item 复位
- 运营入库：1→2 成功、重复入库 400
- 批量销售：正常成交（含 item.recycle_status=3 同步）、状态门、回收商校验、
  金额校验、ids 去重
- 统计：6 字段 + 已取消不计成本 + 负毛利不 clamp + 汇率来自 settings
- 响应外壳：用户端 code:0、管理端 code:200
- order 侧断言：回收流程中的物品不能发起交换（用户补充要求 1）

设计约定与 test_merchant_api.py 一致：服务层用例直接以假游标调用；
接口层用例 monkeypatch 对应模块的 connection 后调用 endpoint 函数。
`KeyedCursor` 按 SQL 片段返回预设结果；`rowcounts` 支持按片段指定 rowcount=0。
"""
from contextlib import contextmanager
from decimal import Decimal

import pytest
from fastapi import HTTPException

from conftest import FakeConn, FakeCursor

from app.api.v1 import item as item_api
from app.api.v1 import order as order_api
from app.api.v1 import recycle as recycle_api
from app.core.config import settings
from app.routers.admin import recycle as admin_recycle_api
from app.schemas.recycle import RecycleSellRequest, RecycleSubmitRequest
from app.services import recycle_service as svc

USER_ID = 7
OTHER_ID = 8
ITEM_ID = 101
RECYCLE_ID = 301
RECYCLER_ID = 4  # 绿源回收站（category='回收'）


# ============================================================
# 假游标 / 假连接工具
# ============================================================
class KeyedCursor(FakeCursor):
    """按 SQL 中出现的片段返回预设结果，不依赖调用顺序。

    `rowcounts` 可按片段指定 UPDATE 的 rowcount（模拟条件更新失败）。
    """

    def __init__(self, results: dict | None = None, rowcounts: dict | None = None,
                 rowcount: int = 1, lastrowid: int = RECYCLE_ID):
        super().__init__(rows=[], rowcount=rowcount, lastrowid=lastrowid)
        self._results = results or {}
        self._rowcounts = rowcounts or {}
        self._current: list = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self.rowcount = 1
        for key, rc in self._rowcounts.items():
            if key in sql:
                self.rowcount = rc
                break
        for key, rows in self._results.items():
            if key in sql:
                self._current = list(rows)
                return
        self._current = []

    def fetchone(self):
        return self._current.pop(0) if self._current else None

    def fetchall(self):
        rows = list(self._current)
        self._current.clear()
        return rows


class SequenceCursor(FakeCursor):
    """fetchone / fetchall 各自按队列返回（stats 一接口连发 5 读 + 2 组 fetchall）。"""

    def __init__(self, ones=(), alls=(), lastrowid: int = 1):
        super().__init__(rows=[], lastrowid=lastrowid)
        self._ones = list(ones)
        self._alls = list(alls)

    def fetchone(self):
        return self._ones.pop(0) if self._ones else None

    def fetchall(self):
        return self._alls.pop(0) if self._alls else []


def _conn(cursor):
    @contextmanager
    def _c():
        yield FakeConn(cursor)
    return _c


def _sqls(cursor) -> list[str]:
    return [sql for sql, _ in cursor.executed]


def _find(cursor, keyword: str):
    for sql, params in cursor.executed:
        if keyword in sql:
            return sql, params
    raise AssertionError(f"未找到包含 {keyword!r} 的 SQL，实际执行：{_sqls(cursor)}")


def _item_row(status: int = 1, recycle_status: int = 0, condition_level: int = 4,
              user_id: int = USER_ID):
    return {
        "id": ITEM_ID,
        "user_id": user_id,
        "title": "九成新台灯",
        "status": status,
        "recycle_status": recycle_status,
        "condition_level": condition_level,
    }


def _recycle_row(status: int = 1, user_id: int = USER_ID, points: int = 220):
    return {
        "id": RECYCLE_ID,
        "user_id": user_id,
        "item_id": ITEM_ID,
        "points_reward": points,
        "status": status,
        "recycle_no": "PR202610160900000001",
    }


# ============================================================
# 估价公式（服务端唯一真源）
# ============================================================
@pytest.mark.parametrize(
    "condition,expected",
    [(0, 10), (1, 25), (2, 60), (3, 120), (4, 220), (5, 350)],
)
def test_estimate_each_condition_tier(condition, expected):
    """成色 0-5 各档取值与常量表一致。"""
    assert svc.estimate_points(condition) == expected


@pytest.mark.parametrize("condition", [-1, 6, 99, None, "abc"])
def test_estimate_invalid_condition_falls_back_to_lowest(condition):
    """越界 / 非法成色一律回落 0 档（最低档），绝不抛异常。"""
    assert svc.estimate_points(condition) == 10


@pytest.mark.parametrize("condition", [-5, 0, 2, 5, 100])
def test_estimate_always_within_bounds(condition):
    """估价恒在 [10, 500]，任何输入都不会越界。"""
    value = svc.estimate_points(condition)
    assert svc.RECYCLE_ESTIMATE_MIN <= value <= svc.RECYCLE_ESTIMATE_MAX


def test_estimate_preview_shape():
    """估价预览响应体：condition_level / estimate_points / min / max。"""
    data = svc.estimate_preview(4)
    assert data == {"condition_level": 4, "estimate_points": 220, "min": 10, "max": 500}


def test_estimate_endpoint_success_shell():
    """GET /recycle/estimate：用户端外壳 code=0。"""
    resp = recycle_api.estimate(condition_level=3)
    assert resp["code"] == 0
    assert resp["data"]["estimate_points"] == 120
    assert resp["data"]["max"] == 500


# ============================================================
# 提交回收
# ============================================================
def _submit(monkeypatch, *, pickup_method=1, pickup_address="", item_row=None,
            user_id=USER_ID, lastrowid=RECYCLE_ID):
    cursor = KeyedCursor(
        results={"FROM item WHERE id=%s LIMIT 1": [item_row or _item_row()],
                 "FROM user WHERE id=%s LIMIT 1": [{"points": 320}]},
        lastrowid=lastrowid,
    )
    monkeypatch.setattr(item_api, "connection", _conn(cursor))
    resp = item_api.submit_recycle(
        ITEM_ID, RecycleSubmitRequest(pickup_method=pickup_method, pickup_address=pickup_address),
        user_id=user_id,
    )
    return cursor, resp


def test_submit_success_awards_points_immediately(monkeypatch):
    """提交回收立即得积分：source=8、related_id=回收单id、余额回读。"""
    cursor, resp = _submit(monkeypatch)

    assert resp["code"] == 0
    data = resp["data"]
    assert data["points_reward"] == 220          # 成色 4 档
    assert data["remaining_points"] == 320
    assert data["recycle_no"].startswith("PR")

    _, params = _find(cursor, "INSERT INTO points_log")
    # (user_id, points, balance, source, related_id, description)
    assert params[0] == USER_ID
    assert params[1] == 220
    assert params[2] == 320
    assert params[3] == 8
    assert params[4] == RECYCLE_ID


def test_submit_creates_recycle_before_awarding(monkeypatch):
    """顺序铁律：先 INSERT 回收单拿 lastrowid，再发分（related_id 不允许为 NULL）。"""
    cursor, _ = _submit(monkeypatch)
    sqls = _sqls(cursor)
    insert_idx = next(i for i, s in enumerate(sqls) if "INSERT INTO platform_recycle" in s)
    award_idx = next(i for i, s in enumerate(sqls) if "UPDATE user SET points" in s)
    assert insert_idx < award_idx, "必须先建回收单再发分，否则 related_id 只能写 NULL"

    _, insert_params = _find(cursor, "INSERT INTO platform_recycle")
    assert insert_params[0].startswith("PR")
    assert insert_params[3] == 220               # points_reward
    assert insert_params[6] == 1                 # status=待取件


def test_submit_writes_item_fields(monkeypatch):
    """item 四字段同步落库：exchange_mode=4 / accept_points / recycle_status=1 / status=2。"""
    cursor, _ = _submit(monkeypatch)
    sql, params = _find(cursor, "UPDATE item SET exchange_mode=4")
    assert "recycle_status=%s" in sql and "status=2" in sql
    # (accept_points, recycle_status, item_id, user_id)
    assert params[0] == 220
    assert params[1] == 1
    assert params[2] == ITEM_ID
    assert params[3] == USER_ID


def test_submit_pending_item_status_4_allowed(monkeypatch):
    """D3 回归：POST /items 落库是 status=4（待审核），发布即回收必须放行。"""
    cursor, resp = _submit(monkeypatch, item_row=_item_row(status=4))
    assert resp["code"] == 0
    assert resp["data"]["points_reward"] == 220


def test_submit_not_owner_403(monkeypatch):
    """非本人物品：403。"""
    with pytest.raises(svc.RecycleError) as exc:
        _submit(monkeypatch, user_id=OTHER_ID, item_row=_item_row(user_id=USER_ID))
    assert exc.value.status_code == 403


def test_submit_duplicate_recycle_rejected(monkeypatch):
    """重复回收拒绝：recycle_status=1 → 400「已在回收流程中」，且不再写库。"""
    cursor = KeyedCursor(
        results={"FROM item WHERE id=%s LIMIT 1": [_item_row(recycle_status=1)]}
    )
    monkeypatch.setattr(item_api, "connection", _conn(cursor))
    with pytest.raises(svc.RecycleError) as exc:
        item_api.submit_recycle(
            ITEM_ID, RecycleSubmitRequest(pickup_method=1), user_id=USER_ID
        )
    assert exc.value.status_code == 400
    assert "已在回收流程中" in exc.value.message
    assert not any("INSERT INTO platform_recycle" in s for s in _sqls(cursor))
    assert not any("UPDATE user SET points" in s for s in _sqls(cursor))


def test_submit_item_already_sold_status_2_rejected(monkeypatch):
    """item.status=2（已下架/已换出）且不在回收流程：400。"""
    cursor = KeyedCursor(
        results={"FROM item WHERE id=%s LIMIT 1": [_item_row(status=2, recycle_status=0)]}
    )
    monkeypatch.setattr(item_api, "connection", _conn(cursor))
    with pytest.raises(svc.RecycleError) as exc:
        item_api.submit_recycle(
            ITEM_ID, RecycleSubmitRequest(pickup_method=1), user_id=USER_ID
        )
    assert exc.value.status_code == 400
    assert "不可回收" in exc.value.message


# ============================================================
# 取件方式
# ============================================================
def test_submit_pickup_to_point_address_optional(monkeypatch):
    """送到回收点（1）：地址可空，落库 NULL。"""
    cursor, resp = _submit(monkeypatch, pickup_method=1, pickup_address="")
    assert resp["code"] == 0
    _, params = _find(cursor, "INSERT INTO platform_recycle")
    assert params[4] == 1
    assert params[5] is None


def test_submit_pickup_door_requires_address(monkeypatch):
    """上门取件（2）：地址必填，缺 → 400 且不写库。"""
    cursor = KeyedCursor()
    monkeypatch.setattr(item_api, "connection", _conn(cursor))
    with pytest.raises(svc.RecycleError) as exc:
        item_api.submit_recycle(
            ITEM_ID, RecycleSubmitRequest(pickup_method=2, pickup_address="  "),
            user_id=USER_ID,
        )
    assert exc.value.status_code == 400
    assert "取件地址" in exc.value.message
    assert cursor.executed == []


def test_submit_pickup_door_address_written(monkeypatch):
    """上门取件带地址：正常落库。"""
    cursor, resp = _submit(
        monkeypatch, pickup_method=2, pickup_address="3 号楼 501 门口"
    )
    assert resp["code"] == 0
    assert resp["data"]["pickup_method_label"] == "上门取件"
    _, params = _find(cursor, "INSERT INTO platform_recycle")
    assert params[4] == 2
    assert params[5] == "3 号楼 501 门口"


def test_submit_pickup_method_invalid_400(monkeypatch):
    """取件方式非法（3）：400。"""
    cursor = KeyedCursor()
    monkeypatch.setattr(item_api, "connection", _conn(cursor))
    with pytest.raises(svc.RecycleError) as exc:
        item_api.submit_recycle(
            ITEM_ID, RecycleSubmitRequest(pickup_method=3), user_id=USER_ID
        )
    assert exc.value.status_code == 400
    assert cursor.executed == []


def test_submit_address_too_long_400(monkeypatch):
    """地址超过 200 字：400。"""
    cursor = KeyedCursor()
    monkeypatch.setattr(item_api, "connection", _conn(cursor))
    with pytest.raises(svc.RecycleError) as exc:
        item_api.submit_recycle(
            ITEM_ID,
            RecycleSubmitRequest(pickup_method=2, pickup_address="址" * 201),
            user_id=USER_ID,
        )
    assert exc.value.status_code == 400


# ============================================================
# 取消回收
# ============================================================
def _cancel(monkeypatch, *, status=1, user_id=USER_ID, recycle_row=None,
            rowcounts=None):
    cursor = KeyedCursor(
        results={"FROM platform_recycle WHERE id=%s LIMIT 1": [recycle_row or _recycle_row(status=status)],
                 "FROM user WHERE id=%s LIMIT 1": [{"points": 420}]},
        rowcounts=rowcounts,
    )
    monkeypatch.setattr(recycle_api, "connection", _conn(cursor))
    resp = recycle_api.cancel_recycle(RECYCLE_ID, user_id=user_id)
    return cursor, resp


def test_cancel_success_refunds_with_source_9(monkeypatch):
    """取消退分必须用 source=9：与发放 source=8 不同，才不撞 uk_points_log_source。"""
    cursor, resp = _cancel(monkeypatch)

    assert resp["code"] == 0
    assert resp["data"]["refund_points"] == 220
    assert resp["data"]["remaining_points"] == 420

    _, params = _find(cursor, "INSERT INTO points_log")
    assert params[3] == 9                          # SOURCE_RECYCLE_CANCEL
    assert params[4] == RECYCLE_ID                 # 同一 related_id（验证不撞唯一索引的前提）
    assert params[1] == 220                        # 正数 = 退回


def test_cancel_resets_item_for_resale(monkeypatch):
    """D6：取消后 item.status 回 1（重新在售）、recycle_status=4（可再次提交）。"""
    cursor, _ = _cancel(monkeypatch)
    sql, params = _find(cursor, "UPDATE item SET recycle_status=")
    assert "status=1" in sql
    assert params[0] == 4
    assert params[1] == ITEM_ID
    _, upd = _find(cursor, "UPDATE platform_recycle SET status=%s WHERE id")
    assert upd[0] == 4


def test_cancel_stocked_rejected(monkeypatch):
    """已入库（status=2）不可取消。"""
    with pytest.raises(svc.RecycleError) as exc:
        _cancel(monkeypatch, status=2)
    assert exc.value.status_code == 400
    assert "无法取消" in exc.value.message


def test_cancel_sold_rejected(monkeypatch):
    """已售出（status=3）不可取消。"""
    with pytest.raises(svc.RecycleError) as exc:
        _cancel(monkeypatch, status=3)
    assert exc.value.status_code == 400


def test_cancel_not_owner_403(monkeypatch):
    """非本人回收单：403。"""
    with pytest.raises(svc.RecycleError) as exc:
        _cancel(monkeypatch, user_id=OTHER_ID)
    assert exc.value.status_code == 403


def test_cancel_missing_404(monkeypatch):
    """回收单不存在：404。"""
    cursor = KeyedCursor(results={"FROM platform_recycle WHERE id=%s LIMIT 1": []})
    monkeypatch.setattr(recycle_api, "connection", _conn(cursor))
    with pytest.raises(svc.RecycleError) as exc:
        recycle_api.cancel_recycle(RECYCLE_ID, user_id=USER_ID)
    assert exc.value.status_code == 404


def test_my_recycles_filters_by_status(monkeypatch):
    """我的回收单：status 筛选进 WHERE，外壳 code=0。"""
    row = {**_recycle_row(), "item_title": "九成新台灯", "item_images": None,
           "user_nickname": "小李"}
    cursor = KeyedCursor(results={
        "COUNT(*) AS total": [{"total": 1}],
        "FROM platform_recycle r": [row],
    })
    monkeypatch.setattr(recycle_api, "connection", _conn(cursor))
    resp = recycle_api.my_recycles(status=1, page=1, size=10, user_id=USER_ID)
    assert resp["code"] == 0
    assert resp["data"]["total"] == 1
    assert resp["data"]["list"][0]["status_label"] == "待取件"
    _, params = _find(cursor, "r.status=%s")
    assert params[0] == USER_ID and params[1] == 1


def test_my_recycles_invalid_status_400(monkeypatch):
    """状态非法（9）：400（接口层直接抛 HTTPException）。"""
    cursor = KeyedCursor()
    monkeypatch.setattr(recycle_api, "connection", _conn(cursor))
    with pytest.raises(HTTPException) as exc:
        recycle_api.my_recycles(status=9, page=1, size=10, user_id=USER_ID)
    assert exc.value.status_code == 400
    assert "回收单状态" in exc.value.detail


# ============================================================
# 运营端：入库
# ============================================================
def test_receive_success(monkeypatch):
    """入库：1→2、写 received_at。"""
    cursor = KeyedCursor(
        results={"FROM platform_recycle WHERE id=%s LIMIT 1": [_recycle_row(status=1)]},
    )
    monkeypatch.setattr(admin_recycle_api, "connection", _conn(cursor))
    resp = admin_recycle_api.receive_recycle(RECYCLE_ID)
    assert resp["code"] == 200
    assert resp["data"]["status"] == 2
    sql, _ = _find(cursor, "UPDATE platform_recycle SET status=%s, received_at=NOW()")
    assert "WHERE id=%s AND status=%s" in sql


def test_receive_twice_rejected(monkeypatch):
    """重复入库：条件更新 rowcount=0 → 400「仅待取件可标记入库」。"""
    cursor = KeyedCursor(
        results={"FROM platform_recycle WHERE id=%s LIMIT 1": [_recycle_row(status=1)]},
        rowcounts={"UPDATE platform_recycle SET status=%s, received_at=NOW()": 0},
    )
    monkeypatch.setattr(admin_recycle_api, "connection", _conn(cursor))
    with pytest.raises(svc.RecycleError) as exc:
        admin_recycle_api.receive_recycle(RECYCLE_ID)
    assert exc.value.status_code == 400


# ============================================================
# 运营端：批量销售
# ============================================================
def _sell_cursor(monkeypatch, *, ids=None, statuses=None, merchant_rows=None,
                 update_rowcount=None):
    """构建批量销售用的假游标。

    - 锁定行数自动与去重后的 ids 对齐（默认全 2 = 已入库）；
    - sold UPDATE 的 rowcount 默认 = 条数（真实 DB 行为）；传 0/1 可模拟并发冲突。
    """
    ids = sorted(set(ids if ids is not None else [RECYCLE_ID, RECYCLE_ID + 1]))
    if statuses is None:
        statuses = [2] * len(ids)
    locked = [_recycle_row(status=s) for s in statuses]
    rowcounts = {"UPDATE platform_recycle SET status=%s, sold_at=NOW()":
                 len(ids) if update_rowcount is None else update_rowcount}
    cursor = KeyedCursor(
        results={
            "FROM merchant WHERE id=%s AND category":
                merchant_rows if merchant_rows is not None
                else [{"id": RECYCLER_ID, "name": "绿源回收站"}],
            "FOR UPDATE": locked,
            "FROM item WHERE id IN": [{"id": ITEM_ID, "title": "九成新台灯"}],
        },
        rowcounts=rowcounts,
        lastrowid=901,
    )
    monkeypatch.setattr(admin_recycle_api, "connection", _conn(cursor))
    return cursor


def _sell_req(amount=66.0, ids=None, recycler_id=RECYCLER_ID):
    return RecycleSellRequest(
        recycler_id=recycler_id,
        recycle_ids=ids if ids is not None else [RECYCLE_ID, RECYCLE_ID + 1],
        total_amount=amount,
    )


def test_sell_success_full_flow(monkeypatch):
    """批量销售：建销售单 → 回收单置 3 + sold_at → **item.recycle_status=3 同步**。"""
    cursor = _sell_cursor(monkeypatch)
    resp = admin_recycle_api.sell_to_recycler(_sell_req())

    assert resp["code"] == 200
    data = resp["data"]
    assert data["sale_no"].startswith("PS")
    assert data["item_count"] == 2
    assert data["recycler_name"] == "绿源回收站"
    assert data["total_amount"] == 66.0

    _, sale_params = _find(cursor, "INSERT INTO platform_sale")
    assert sale_params[1] == RECYCLER_ID
    assert str(sale_params[2]) == "66.00"          # Decimal 量化两位
    assert sale_params[3] == 2

    _, upd_params = _find(cursor, "UPDATE platform_recycle SET status=%s, sold_at=NOW()")
    assert upd_params[0] == 3
    assert upd_params[-1] == 2                     # AND status=2 条件

    _, item_params = _find(cursor, "UPDATE item SET recycle_status=")
    assert item_params[0] == 3                     # 任务书遗漏的同步项

    import json as _json
    _, sale_params2 = _find(cursor, "INSERT INTO platform_sale")
    snapshot = _json.loads(sale_params2[4])
    assert snapshot[0]["points_reward"] == 220
    assert snapshot[0]["item_title"] == "九成新台灯"


def test_sell_concurrent_conflict_rolls_back(monkeypatch):
    """并发冲突：条件更新 rowcount < 条数 → 409（调用方事务回滚）。"""
    _sell_cursor(monkeypatch, update_rowcount=1)      # 2 条，rowcount=1
    with pytest.raises(svc.RecycleError) as exc:
        admin_recycle_api.sell_to_recycler(_sell_req())
    assert exc.value.status_code == 409


def test_sell_not_stocked_rejected_before_any_write(monkeypatch):
    """含非 status=2 的单：400，且不产生任何 INSERT/UPDATE 写库。"""
    cursor = _sell_cursor(monkeypatch, statuses=[2, 1])
    with pytest.raises(svc.RecycleError) as exc:
        admin_recycle_api.sell_to_recycler(_sell_req())
    assert exc.value.status_code == 400
    assert "不在已入库状态" in exc.value.message
    assert not any("INSERT INTO platform_sale" in s for s in _sqls(cursor))
    assert not any("UPDATE platform_recycle SET status=%s, sold_at" in s for s in _sqls(cursor))


def test_sell_recycler_wrong_category_rejected(monkeypatch):
    """回收商 category≠'回收'（或停业）：400。"""
    cursor = _sell_cursor(monkeypatch, merchant_rows=[])
    with pytest.raises(svc.RecycleError) as exc:
        admin_recycle_api.sell_to_recycler(_sell_req())
    assert exc.value.status_code == 400
    assert "回收商" in exc.value.message


def test_sell_amount_must_be_positive(monkeypatch):
    """金额 ≤0：400（写库前拦截）。"""
    cursor = _sell_cursor(monkeypatch)
    with pytest.raises(svc.RecycleError) as exc:
        admin_recycle_api.sell_to_recycler(_sell_req(amount=0))
    assert exc.value.status_code == 400
    with pytest.raises(svc.RecycleError) as exc2:
        admin_recycle_api.sell_to_recycler(_sell_req(amount=-1))
    assert exc2.value.status_code == 400
    assert not any("INSERT INTO platform_sale" in s for s in _sqls(cursor))


def test_sell_amount_over_cap_400(monkeypatch):
    """金额超出 DECIMAL(10,2) 上限：400。"""
    _sell_cursor(monkeypatch)
    with pytest.raises(svc.RecycleError) as exc:
        admin_recycle_api.sell_to_recycler(_sell_req(amount=100_000_000))
    assert exc.value.status_code == 400


def test_sell_empty_ids_400(monkeypatch):
    """ids 为空：400。"""
    _sell_cursor(monkeypatch)
    with pytest.raises(svc.RecycleError) as exc:
        admin_recycle_api.sell_to_recycler(_sell_req(ids=[]))
    assert exc.value.status_code == 400


def test_sell_dedups_and_caps_ids(monkeypatch):
    """ids 去重：重复 id 只卖一次；超 100 条拒绝。"""
    _sell_cursor(monkeypatch, ids=[RECYCLE_ID, RECYCLE_ID + 1])
    resp = admin_recycle_api.sell_to_recycler(
        _sell_req(ids=[RECYCLE_ID, RECYCLE_ID, RECYCLE_ID + 1, RECYCLE_ID + 1])
    )
    assert resp["code"] == 200
    assert resp["data"]["item_count"] == 2

    _sell_cursor(monkeypatch)
    with pytest.raises(svc.RecycleError) as exc:
        admin_recycle_api.sell_to_recycler(
            _sell_req(ids=list(range(1, 102)))
        )
    assert exc.value.status_code == 400


def test_sell_to_money_half_up(monkeypatch):
    """金额 0.155 → Decimal HALF_UP = 0.16（不是 float round 的 0.15）。"""
    cursor = _sell_cursor(monkeypatch, ids=[RECYCLE_ID])
    resp = admin_recycle_api.sell_to_recycler(_sell_req(amount=0.155, ids=[RECYCLE_ID]))
    assert resp["data"]["total_amount"] == 0.16
    _, params = _find(cursor, "INSERT INTO platform_sale")
    assert str(params[2]) == "0.16"


# ============================================================
# 运营端：销售记录 / 回收商下拉
# ============================================================
def test_list_sales_shape(monkeypatch):
    """销售记录：外壳 code=200，明细含快照解析。"""
    row = {
        "id": 901, "sale_no": "PS202610160900000001", "recycler_id": RECYCLER_ID,
        "recycler_name": "绿源回收站", "total_amount": "66.00", "item_count": 1,
        "items_json": '[{"recycle_id": 301, "item_title": "台灯"}]',
        "status": 1, "created_at": None,
    }
    cursor = KeyedCursor(results={
        "COUNT(*) AS total": [{"total": 1}],
        "FROM platform_sale s": [row],
    })
    monkeypatch.setattr(admin_recycle_api, "connection", _conn(cursor))
    resp = admin_recycle_api.list_sales(recycler_id=None, page=1, size=10)
    assert resp["code"] == 200
    assert resp["data"]["list"][0]["recycler_name"] == "绿源回收站"
    assert resp["data"]["list"][0]["items"][0]["item_title"] == "台灯"


def test_list_recyclers_only_recycle_category(monkeypatch):
    """回收商下拉：SQL 强制 category='回收' AND status=1。"""
    cursor = KeyedCursor(results={
        "FROM merchant": [{"id": RECYCLER_ID, "name": "绿源回收站",
                           "contact": "13800000004", "address": "小区南门"}],
    })
    monkeypatch.setattr(admin_recycle_api, "connection", _conn(cursor))
    resp = admin_recycle_api.list_recyclers()
    assert resp["code"] == 200
    assert resp["data"][0]["id"] == RECYCLER_ID
    sql, params = _find(cursor, "FROM merchant")
    assert "category=%s" in sql and "status=1" in sql
    assert params[0] == "回收"


# ============================================================
# 运营端：统计
# ============================================================
def _stats_cursor(monkeypatch, *, points_to_yuan=0.01):
    ones = [
        {"c": 3},                                   # total_received (IN 2,3)
        {"c": 1},                                   # total_sold (=3)
        {"c": 2},                                   # pending_pickup (=1)
        {"p": 1000},                                # total_points_issued
        {"m": Decimal("8.00")},                     # total_revenue
    ]
    alls = [
        [{"status": 1, "c": 2}, {"status": 3, "c": 1}],   # status_distribution
        [{"recycler_id": RECYCLER_ID, "recycler_name": "绿源回收站",
          "amount": Decimal("8.00"), "sales": 1, "items": 1}],
    ]
    cursor = SequenceCursor(ones=ones, alls=alls)
    monkeypatch.setattr(admin_recycle_api, "connection", _conn(cursor))
    monkeypatch.setattr(settings, "merchant_points_to_yuan", points_to_yuan)
    return cursor


def test_stats_six_taskbook_fields(monkeypatch):
    """任务书 6 字段齐备：成本 = 积分 × 汇率（HALF_UP）。"""
    cursor = _stats_cursor(monkeypatch, points_to_yuan=0.01)
    data = admin_recycle_api.recycle_stats()["data"]

    assert data["total_received"] == 3
    assert data["total_sold"] == 1
    assert data["total_points_issued"] == 1000
    assert data["total_revenue"] == 8.0
    assert data["total_cost"] == 10.0               # 1000 × 0.01
    assert data["gross_profit"] == -2.0             # 8 - 10（允许负毛利）


def test_stats_negative_gross_profit_not_clamped(monkeypatch):
    """负毛利不 clamp（库存未售出就是负毛利，真实经营状态）。"""
    _stats_cursor(monkeypatch, points_to_yuan=0.01)
    data = admin_recycle_api.recycle_stats()["data"]
    assert data["gross_profit"] < 0


def test_stats_exchange_rate_from_settings(monkeypatch):
    """汇率复用 settings.merchant_points_to_yuan（与商家结算同源），不硬编码。"""
    _stats_cursor(monkeypatch, points_to_yuan=0.02)
    data = admin_recycle_api.recycle_stats()["data"]
    assert data["points_to_yuan"] == 0.02
    assert data["total_cost"] == 20.0               # 1000 × 0.02


def test_stats_dashboard_extensions(monkeypatch):
    """看板扩展：状态分布 4 项 + 回收商排行 + 待取件量。"""
    _stats_cursor(monkeypatch)
    data = admin_recycle_api.recycle_stats()["data"]

    assert data["pending_pickup"] == 2
    assert [d["status"] for d in data["status_distribution"]] == [1, 2, 3, 4]
    assert data["status_distribution"][2]["count"] == 1
    assert data["top_recyclers"][0]["recycler_name"] == "绿源回收站"
    assert data["top_recyclers"][0]["total_amount"] == 8.0


def test_stats_cancelled_points_excluded_from_cost(monkeypatch):
    """成本口径：total_points_issued 的 SQL 只含 status IN (1,2,3)，排除已取消。"""
    _stats_cursor(monkeypatch)
    admin_recycle_api.recycle_stats()
    # SequenceCursor 不记录 SQL，改用 KeyedCursor 校验 SQL 形状
    cursor = KeyedCursor()
    svc.recycle_stats(cursor)
    sql, params = _find(cursor, "SUM(points_reward)")
    assert "status IN (%s,%s,%s)" in sql
    assert sorted(params) == [1, 2, 3]
    assert 4 not in params


# ============================================================
# 响应外壳
# ============================================================
def test_user_side_shell_code_zero(monkeypatch):
    """用户端回收接口一律 success()（code=0）。"""
    row = {**_recycle_row(), "item_title": "t", "item_images": None, "user_nickname": "n"}
    cursor = KeyedCursor(results={
        "COUNT(*) AS total": [{"total": 0}],
        "FROM platform_recycle r": [row],
    })
    monkeypatch.setattr(recycle_api, "connection", _conn(cursor))
    resp = recycle_api.my_recycles(status=None, page=1, size=10, user_id=USER_ID)
    assert resp["code"] == 0


def test_admin_side_shell_code_200(monkeypatch):
    """管理端回收接口一律 ok()（code=200）。"""
    _sell_cursor(monkeypatch, ids=[RECYCLE_ID])
    resp = admin_recycle_api.sell_to_recycler(_sell_req(ids=[RECYCLE_ID]))
    assert resp["code"] == 200


# ============================================================
# order 侧断言（用户补充要求 1：平台回收不走 order 流程）
# ============================================================
def _order_create(monkeypatch, item_row):
    cursor = KeyedCursor(results={"FROM item WHERE id=%s LIMIT 1": [item_row]})
    monkeypatch.setattr(order_api, "connection", _conn(cursor))
    return cursor


def test_order_rejects_item_in_recycle_flow(monkeypatch):
    """回收流程中的物品（mode=4 + recycle_status IN 1/2/3）不能发起交换。"""
    _order_create(monkeypatch, {
        "id": ITEM_ID, "user_id": OTHER_ID, "status": 1,
        "exchange_mode": 4, "recycle_status": 2, "price": "0.00",
    })
    with pytest.raises(HTTPException) as exc:
        order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID, message=""), user_id=USER_ID)
    assert exc.value.status_code == 400
    assert "平台回收" in exc.value.detail


def test_order_allows_cancelled_recycle_item(monkeypatch):
    """取消回收后（recycle_status=4、status=1）：可通过回收断言，继续走正常交换校验。"""
    _order_create(monkeypatch, {
        "id": ITEM_ID, "user_id": OTHER_ID, "status": 1,
        "exchange_mode": 4, "recycle_status": 4, "price": "0.00",
    })
    # 通过回收断言后，下一步是「重复发起」校验：预置一条进行中订单 → 400（证明已越过回收门）
    cursor = KeyedCursor(results={
        "FROM item WHERE id=%s LIMIT 1": [{
            "id": ITEM_ID, "user_id": OTHER_ID, "status": 1,
            "exchange_mode": 4, "recycle_status": 4, "price": "0.00",
        }],
        "FROM `order` WHERE buyer_id": [{"id": 555}],
    })
    monkeypatch.setattr(order_api, "connection", _conn(cursor))
    with pytest.raises(HTTPException) as exc:
        order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)
    assert exc.value.status_code == 400
    assert "发起过交换" in exc.value.detail


def test_order_normal_item_passes_recycle_guard(monkeypatch):
    """普通物品（mode=1）不受回收断言影响（回归保护）。"""
    cursor = KeyedCursor(results={
        "FROM item WHERE id=%s LIMIT 1": [{
            "id": ITEM_ID, "user_id": OTHER_ID, "status": 1,
            "exchange_mode": 1, "recycle_status": 0, "price": "0.00",
        }],
        "FROM `order` WHERE buyer_id": [{"id": 555}],
    })
    monkeypatch.setattr(order_api, "connection", _conn(cursor))
    with pytest.raises(HTTPException) as exc:
        order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)
    assert exc.value.status_code == 400
    assert "发起过交换" in exc.value.detail         # 已越过回收断言，卡在下一道校验
