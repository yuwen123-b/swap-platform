"""admin 侧积分挂载点测试。

admin 目录此前没有任何测试，本文件补齐本轮新增的两个积分发放挂载点：
- admin/item.py  audit_item      ：审核通过发发布奖励（source=1）
- admin/order.py update_order_status：首次完成交换发交换奖励（source=2）+ 累加交换次数/碳减排量
- admin/points.py adjust_points ：管理员调整积分时补写 balance

重点验证两个安全属性：
① 幂等 —— 重复审核 / 重复置为「已完成」都不得重复发分（防刷分）
② 去重 —— 买家与卖家为同一用户时只结算一次（防同一账号双倍奖励）

另覆盖本轮新增的数据库级闸门：
③ points_log 唯一索引 uk_points_log_source(source, related_id, user_id)
   —— 迁移幂等，且命中重复时 award_points 抛 PointsAwardError（可读提示），
      由调用方事务整体回滚
"""
import pymysql
import pytest
from fastapi import HTTPException

from conftest import FakeCursor, make_connection

from app.db import pool
from app.routers.admin import item as admin_item
from app.routers.admin import order as admin_order
from app.routers.admin import points as admin_points
from app.services import points_service


def _patch(monkeypatch, module, rows=None, rowcount=1):
    cursor = FakeCursor(rows=rows, rowcount=rowcount)
    monkeypatch.setattr(module, "connection", make_connection(cursor))
    return cursor


def _sql_list(cursor):
    return [sql for sql, _ in cursor.executed]


def _log_inserts(cursor):
    """取出所有 points_log 写入参数，顺序即实际执行顺序。"""
    return [params for sql, params in cursor.executed if sql.startswith("INSERT INTO points_log")]


def _stat_updates(cursor):
    return [
        params for sql, params in cursor.executed
        if sql.startswith("UPDATE user SET exchange_count=COALESCE")
    ]


# ============================================================
# 审核通过 -> 发布奖励（source=1）
# ============================================================
def test_audit_approve_awards_publish_points(monkeypatch):
    """审核通过：上架 + 按 sys_config 的 points_publish 发分，balance 为回读余额。"""
    cursor = _patch(monkeypatch, admin_item, rows=[
        {"id": 5, "user_id": 7, "title": "旧书", "status": 4},  # SELECT item
        {"config_value": "20"},                                 # SELECT sys_config
        {"points": 120},                                        # SELECT points（回读）
    ])
    resp = admin_item.audit_item(5, admin_item.AuditRequest(approved=True))

    assert resp["message"] == "审核通过，物品已上架"
    assert _sql_list(cursor)[1] == "UPDATE item SET status=1, reject_reason=NULL WHERE id=%s"

    inserts = _log_inserts(cursor)
    assert len(inserts) == 1
    # (user_id, points, balance, source, related_id, description)
    assert list(inserts[0]) == [7, 20, 120, 1, 5, "发布物品奖励：旧书"]

    # 顺序要求：UPDATE user.points 必须在回读之前，回读必须在 INSERT 之前
    sqls = _sql_list(cursor)
    assert sqls.index("UPDATE user SET points=points+%s WHERE id=%s") < sqls.index(
        "SELECT points FROM user WHERE id=%s LIMIT 1"
    )
    assert sqls.index("SELECT points FROM user WHERE id=%s LIMIT 1") < len(sqls) - 1


def test_audit_reject_does_not_award(monkeypatch):
    """审核拒绝不发分，且不写任何流水。"""
    cursor = _patch(monkeypatch, admin_item, rows=[
        {"id": 5, "user_id": 7, "title": "旧书", "status": 4},
    ])
    resp = admin_item.audit_item(5, admin_item.AuditRequest(approved=False, reason="图片不清晰"))

    assert resp["message"] == "已拒绝该物品上架"
    assert _log_inserts(cursor) == []
    assert not any("points=points" in sql for sql in _sql_list(cursor))


def test_audit_approve_is_idempotent_via_status_guard(monkeypatch):
    """已通过的物品再次审核直接 400，天然幂等，不会重复发分。"""
    cursor = _patch(monkeypatch, admin_item, rows=[
        {"id": 5, "user_id": 7, "title": "旧书", "status": 1},
    ])
    with pytest.raises(HTTPException) as exc:
        admin_item.audit_item(5, admin_item.AuditRequest(approved=True))

    assert exc.value.status_code == 400
    assert "不在待审核状态" in exc.value.detail
    assert len(cursor.executed) == 1


def test_audit_approve_missing_item_404(monkeypatch):
    """物品不存在时 404，不触发放分。"""
    cursor = _patch(monkeypatch, admin_item, rows=[])
    with pytest.raises(HTTPException) as exc:
        admin_item.audit_item(5, admin_item.AuditRequest(approved=True))

    assert exc.value.status_code == 404
    assert len(cursor.executed) == 1


# ============================================================
# 交换完成 -> 交换奖励（source=2）
# ============================================================
def test_order_complete_awards_both_sides(monkeypatch):
    """首次置为已完成(3)：买卖双方各发一次分，并各累加交换次数与碳减排量。"""
    cursor = _patch(monkeypatch, admin_order, rows=[
        {"status": 2, "buyer_id": 7, "seller_id": 8},  # SELECT order
        {"config_value": "50"},                        # points_exchange
        {"config_value": "5.0"},                       # carbon_per_exchange
        {"points": 150},                               # 卖家余额回读
        {"points": 130},                               # 买家余额回读
    ])
    resp = admin_order.update_order_status(9, admin_order.OrderStatusUpdate(status=3))

    assert resp["message"] == "订单状态已更新"
    inserts = _log_inserts(cursor)
    assert len(inserts) == 2
    assert list(inserts[0]) == [8, 50, 150, 2, 9, "完成交换奖励（作为卖家）"]
    assert list(inserts[1]) == [7, 50, 130, 2, 9, "完成交换奖励（作为买家）"]

    stats = _stat_updates(cursor)
    assert [list(params) for params in stats] == [[5.0, 8], [5.0, 7]]


def test_order_complete_self_exchange_awards_once(monkeypatch):
    """买家 == 卖家（脏数据）时只结算一次，避免同一账号被双倍奖励。"""
    cursor = _patch(monkeypatch, admin_order, rows=[
        {"status": 2, "buyer_id": 7, "seller_id": 7},
        {"config_value": "50"},
        {"config_value": "5.0"},
        {"points": 150},
    ])
    admin_order.update_order_status(9, admin_order.OrderStatusUpdate(status=3))

    inserts = _log_inserts(cursor)
    assert len(inserts) == 1
    assert list(inserts[0]) == [7, 50, 150, 2, 9, "完成交换奖励"]
    assert len(_stat_updates(cursor)) == 1


def test_order_complete_repeated_put_does_not_double_award(monkeypatch):
    """订单已是已完成，再次 PUT status=3 不重复发分（防刷分）。"""
    cursor = _patch(monkeypatch, admin_order, rows=[
        {"status": 3, "buyer_id": 7, "seller_id": 8},
    ])
    admin_order.update_order_status(9, admin_order.OrderStatusUpdate(status=3))

    assert _log_inserts(cursor) == []
    assert _stat_updates(cursor) == []
    assert not any("points=points" in sql for sql in _sql_list(cursor))
    # 状态更新本身仍然执行
    assert any("completed_at=NOW()" in sql for sql in _sql_list(cursor))


def test_order_status_non_complete_does_not_award(monkeypatch):
    """改为非完成态（如 4=已取消）不发分。"""
    cursor = _patch(monkeypatch, admin_order, rows=[
        {"status": 1, "buyer_id": 7, "seller_id": 8},
    ])
    admin_order.update_order_status(9, admin_order.OrderStatusUpdate(status=4))

    assert _log_inserts(cursor) == []
    sql, params = cursor.executed[1]
    assert sql == "UPDATE `order` SET status=%s WHERE id=%s"
    assert list(params) == [4, 9]


def test_order_status_missing_order_404(monkeypatch):
    """订单不存在时 404，不触发放分。"""
    cursor = _patch(monkeypatch, admin_order, rows=[])
    with pytest.raises(HTTPException) as exc:
        admin_order.update_order_status(9, admin_order.OrderStatusUpdate(status=3))

    assert exc.value.status_code == 404
    assert len(cursor.executed) == 1


# ============================================================
# 管理员调整积分 -> 补写 balance
# ============================================================
def test_admin_points_adjust_writes_balance(monkeypatch):
    """管理员调整积分时，points_log.balance 必须写入调整后的余额（原实现漏写恒为 0）。"""
    cursor = _patch(monkeypatch, admin_points, rows=[
        {"id": 7, "points": 100},  # 用户存在性检查
        {"points": 130},           # award_points 回读余额
    ])
    resp = admin_points.adjust_points(
        admin_points.PointsAdjust(user_id=7, points=30, reason="活动奖励"),
        {"admin_id": 1},
    )

    assert resp["message"] == "积分调整成功"
    inserts = _log_inserts(cursor)
    assert len(inserts) == 1
    # related_id 固定为 None（不是 admin_id）：points_log 唯一索引
    # uk_points_log_source(source, related_id, user_id) 是「同一笔业务不重复发放」的闸门，
    # 而管理员调整每次都是独立事件；MySQL 唯一索引不约束 NULL，
    # 写 NULL 才能让同一管理员对同一用户反复调整（否则第二次会撞唯一键）。
    assert list(inserts[0]) == [7, 30, 130, 4, None, "[管理员调整] 活动奖励"]


def test_admin_points_adjust_missing_user_404(monkeypatch):
    """用户不存在时 404，不写流水。"""
    cursor = _patch(monkeypatch, admin_points, rows=[])
    with pytest.raises(HTTPException) as exc:
        admin_points.adjust_points(
            admin_points.PointsAdjust(user_id=999, points=30, reason="活动奖励"),
            {"admin_id": 1},
        )

    assert exc.value.status_code == 404
    assert _log_inserts(cursor) == []


# ============================================================
# 规则读取兜底（points_service）
# ============================================================
def test_get_int_rule_falls_back_on_missing_or_invalid(monkeypatch):
    """规则缺失 / 非数字 / 0 / 负数 一律回落默认值；正常值以 DB 为准。"""
    assert points_service.get_int_rule(FakeCursor(rows=[]), "points_publish", 20) == 20
    assert points_service.get_int_rule(
        FakeCursor(rows=[{"config_value": "abc"}]), "points_publish", 20
    ) == 20
    # 配成 0 属典型误配（会让奖励静默失效），按默认处理
    assert points_service.get_int_rule(
        FakeCursor(rows=[{"config_value": "0"}]), "points_publish", 20
    ) == 20
    assert points_service.get_int_rule(
        FakeCursor(rows=[{"config_value": "-5"}]), "points_publish", 20
    ) == 20
    assert points_service.get_int_rule(
        FakeCursor(rows=[{"config_value": "35"}]), "points_publish", 20
    ) == 35


def test_get_float_rule_zero_falls_back_to_default(monkeypatch):
    """碳减排量系数为 0 时回落默认值，避免永不累加。"""
    assert points_service.get_float_rule(
        FakeCursor(rows=[{"config_value": "0"}]), "carbon_per_exchange", 5.0
    ) == 5.0
    assert points_service.get_float_rule(
        FakeCursor(rows=[{"config_value": "2.5"}]), "carbon_per_exchange", 5.0
    ) == 2.5


def test_read_config_failure_falls_back(monkeypatch):
    """sys_config 不可用（抛异常）时不应阻断主流程，回落默认值。"""

    class BoomCursor(FakeCursor):
        def execute(self, sql, params=None):
            raise RuntimeError("sys_config 不可用")

    assert points_service.get_int_rule(BoomCursor(), "points_publish", 20) == 20
    assert points_service.get_float_rule(BoomCursor(), "carbon_per_exchange", 5.0) == 5.0


def test_award_points_skips_zero_delta():
    """变动值为 0 时不产生任何写入，避免噪音流水。"""
    cursor = FakeCursor(rows=[])
    assert points_service.award_points(cursor, 7, 0, source=4) is None
    assert cursor.executed == []


def test_bump_exchange_stats_uses_coalesce():
    """累加交换统计时必须用 COALESCE，否则 NULL + 1 仍是 NULL，统计永远为 0。"""
    cursor = FakeCursor(rows=[])
    points_service.bump_exchange_stats(cursor, 7, 5.0)

    sql, params = cursor.executed[0]
    assert "COALESCE(exchange_count, 0)" in sql
    assert "COALESCE(carbon_total, 0)" in sql
    assert list(params) == [5.0, 7]


# ============================================================
# points_log 唯一索引：迁移幂等 + 失败语义
# ============================================================
def _dup_cursor(rows):
    """构造在 INSERT points_log 时模拟唯一键冲突的假游标。"""

    class DupCursor(FakeCursor):
        def execute(self, sql, params=None):
            if sql.startswith("INSERT INTO points_log"):
                raise pymysql.err.IntegrityError(
                    1062, "Duplicate entry '2-9-7' for key 'points_log.uk_points_log_source'"
                )
            return super().execute(sql, params)

    return DupCursor(rows=rows)


def test_ensure_points_log_columns_adds_balance_and_widens_description(monkeypatch):
    """线上老表缺 balance、description 只有 100：迁移必须补列并放宽宽度。

    这正是 `GET /user/carbon/logs` 500 的根因——
    1054 Unknown column 'balance' in 'field list'（查询与发分写入同时挂）。
    """
    cursor = FakeCursor(rows=[
        {"c": 0},                # balance 不存在 -> ADD COLUMN
        {"t": "varchar(100)"},   # description 宽度不足 -> MODIFY
    ])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_points_log_columns()

    sqls = [sql for sql, _ in cursor.executed]
    assert any(s.startswith("ALTER TABLE points_log ADD COLUMN balance") for s in sqls)
    assert any(s.startswith("ALTER TABLE points_log MODIFY COLUMN description VARCHAR(255)") for s in sqls)


def test_ensure_points_log_columns_is_idempotent(monkeypatch):
    """列已存在且宽度达标时不产生任何 ALTER（ALTER 非幂等，重复执行会失败）。"""
    cursor = FakeCursor(rows=[
        {"c": 1},                # balance 已存在
        {"t": "varchar(255)"},   # description 已达标
    ])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_points_log_columns()

    assert not any(sql.startswith("ALTER TABLE") for sql, _ in cursor.executed)


def test_ensure_points_log_unique_index_creates_when_absent(monkeypatch):
    """索引不存在时执行 ALTER，键名与列序严格为 (source, related_id, user_id)。"""
    cursor = FakeCursor(rows=[{"c": 0}])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_points_log_unique_index()

    ddl = [sql for sql, _ in cursor.executed if sql.startswith("ALTER TABLE")]
    assert len(ddl) == 1
    assert pool.POINTS_LOG_UNIQUE_INDEX in ddl[0]
    assert "(source, related_id, user_id)" in ddl[0]


def test_ensure_points_log_unique_index_skips_when_present(monkeypatch):
    """索引已存在时不再执行 ALTER（幂等，避免第二次启动 Duplicate key name）。"""
    cursor = FakeCursor(rows=[{"c": 1}])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_points_log_unique_index()

    assert not any(sql.startswith("ALTER TABLE") for sql, _ in cursor.executed)


def test_ensure_points_log_unique_index_does_not_block_startup(monkeypatch):
    """存量有重复行导致建索引失败时只告警，不能阻断后端启动。"""

    class FailingAlterCursor(FakeCursor):
        def execute(self, sql, params=None):
            if sql.startswith("ALTER TABLE"):
                raise pymysql.err.IntegrityError(1062, "Duplicate entry")
            return super().execute(sql, params)

    cursor = FailingAlterCursor(rows=[{"c": 0}])
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_points_log_unique_index()  # 不抛异常即通过


def test_award_points_duplicate_log_raises_clear_error():
    """命中唯一索引时抛 PointsAwardError，提示里带上用户 / 来源 / 关联业务。"""
    cursor = _dup_cursor(rows=[{"points": 150}])

    with pytest.raises(points_service.PointsAwardError) as exc:
        points_service.award_points(
            cursor, 7, 50, source=2, related_id=9, description="完成交换奖励"
        )

    message = str(exc.value)
    assert "已存在" in message
    assert "source=2" in message
    assert "related_id=9" in message
    # 回读发生在 UPDATE 之后：说明余额加分与流水的顺序未被破坏
    sqls = [sql for sql, _ in cursor.executed]
    assert sqls.index("UPDATE user SET points=points+%s WHERE id=%s") < sqls.index(
        "SELECT points FROM user WHERE id=%s LIMIT 1"
    )


def test_award_points_reraises_non_duplicate_error():
    """非唯一键冲突的数据库错误原样抛出，不伪装成业务冲突（避免误报 409）。"""

    class NonDupCursor(FakeCursor):
        def execute(self, sql, params=None):
            if sql.startswith("INSERT INTO points_log"):
                raise pymysql.err.IntegrityError(1048, "Column 'balance' cannot be null")
            return super().execute(sql, params)

    with pytest.raises(pymysql.err.IntegrityError):
        points_service.award_points(NonDupCursor(rows=[{"points": 10}]), 7, 5, source=1, related_id=3)


def test_order_complete_points_conflict_propagates(monkeypatch):
    """交换发分撞唯一键时异常必须冒泡出路由，交由 with connection() 整体回滚。"""
    cursor = _dup_cursor(rows=[
        {"status": 2, "buyer_id": 7, "seller_id": 8},
        {"config_value": "50"},
        {"config_value": "5.0"},
        {"points": 150},
    ])
    monkeypatch.setattr(admin_order, "connection", make_connection(cursor))

    with pytest.raises(points_service.PointsAwardError):
        admin_order.update_order_status(9, admin_order.OrderStatusUpdate(status=3))


# ============================================================
# 事务语义：pool.connection 在异常时回滚、正常时提交
# ============================================================
class _TxProbeConn:
    """记录 commit / rollback 的假连接，用于验证 pool.connection 的事务语义。"""

    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def connection(self):
        return self._conn


def test_connection_rolls_back_when_points_conflict(monkeypatch):
    """唯一键冲突 → 整笔事务回滚（user.points 与 points_log 一起撤销，不留半截脏账）。"""
    conn = _TxProbeConn(_dup_cursor(rows=[{"points": 150}]))
    monkeypatch.setattr(pool, "get_pool", lambda: _FakePool(conn))

    with pytest.raises(points_service.PointsAwardError):
        with pool.connection() as c:
            with c.cursor() as cur:
                points_service.award_points(cur, 7, 50, source=2, related_id=9)

    assert conn.rolled_back is True
    assert conn.committed is False


def test_connection_commits_when_award_succeeds(monkeypatch):
    """正常发放 → 由 pool.connection 统一提交，points_service 自己不开事务。"""
    conn = _TxProbeConn(FakeCursor(rows=[{"points": 150}]))
    monkeypatch.setattr(pool, "get_pool", lambda: _FakePool(conn))

    with pool.connection() as c:
        with c.cursor() as cur:
            balance = points_service.award_points(cur, 7, 50, source=1, related_id=3)

    assert balance == 150
    assert conn.committed is True
    assert conn.rolled_back is False
