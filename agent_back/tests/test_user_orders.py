"""我的交换（用户侧订单接口）单元测试（数据库 mock，不连真实 MySQL）。

覆盖：
- 发起交换：成功 / 不带留言不发私信 / 带留言时**订单提交后**才发私信 /
  自己的物品 400 / 已下架 400 / 物品不存在 404 / 重复进行中 400 / 留言超长 400
- 健壮性：订单号撞唯一索引重试、非唯一键完整性错误原样抛出、
  私信失败只记 warning 且不影响下单结果
- 列表：role=buyer/seller/all 的 WHERE 与参数、非法 role 400、非法 status 400、
  对方昵称口径（买家视角 / 卖家视角）、物品已删除降级、图片取首图
- 详情：第三方 403、不存在 404、时间线（无状态历史表 → 由状态+时间戳推导）、
  消息记录按升序返回
- 确认（1→2）：卖家成功 / 非卖家 403 / 状态不符 400 / 条件更新 rowcount=0 400
- 完成（2→3）：双方各发一次分 + 累加统计 + **物品置为已下架** + completed_at；
  自换单只发一次；非双方 403；状态不符 400；rowcount=0 400
- 取消（1/2→4）：成功 / 终态 400 / 非双方 403
- 端点契约：`exchange_type` 按 `item.exchange_mode` 正确映射；
  管理端与用户侧共用同一个发奖函数（上移后没有出现两份实现）

设计约定：本模块刻意**不**在单元测试里连真实库——所有 SQL 走 conftest 的 FakeCursor，
断言集中在「SQL 形状 + 参数 + 返回结构」三件事上；
真实库端到端验证另在交付说明的《验证清单》中列出。
"""
import logging
from datetime import datetime

import pymysql
import pytest
from fastapi import HTTPException

from conftest import FakeConn, FakeCursor, make_connection, stub_image_signer, stub_image_signer

from app.api.v1 import order as order_api
from app.routers.admin import order as admin_order
from app.services import order_service

# 固定 ID：7 买家 / 8 卖家 / 9 订单 / 25 物品
USER_ID = 7
SELLER_ID = 8
OUTSIDER_ID = 99
ORDER_ID = 9
ITEM_ID = 25


# ============================================================
# 工具
# ============================================================
def _patch(monkeypatch, rows=None, rowcount=1, lastrowid=99):
    stub_image_signer(monkeypatch)  # 封面签名换成可读桩（见 conftest 说明）
    cursor = FakeCursor(rows=rows, rowcount=rowcount, lastrowid=lastrowid)
    monkeypatch.setattr(order_api, "connection", make_connection(cursor))
    return cursor


class _Messenger:
    """私信服务替身：记录调用参数，可配置为抛错。"""

    def __init__(self, error=None):
        self.calls: list[dict] = []
        self.error = error

    def send_message(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return 1


def _patch_messenger(monkeypatch, error=None) -> _Messenger:
    messenger = _Messenger(error=error)
    monkeypatch.setattr(order_api, "message_service", messenger)
    return messenger


def _item_row(**overrides):
    row = {"id": ITEM_ID, "user_id": SELLER_ID, "status": 1, "exchange_mode": 2}
    row.update(overrides)
    return row


def _order_row(**overrides):
    row = {"id": ORDER_ID, "order_no": "SW202610131200001234", "item_id": ITEM_ID,
           "buyer_id": USER_ID, "seller_id": SELLER_ID, "status": 1}
    row.update(overrides)
    return row


def _list_row(**overrides):
    row = {
        "order_id": ORDER_ID,
        "order_no": "SW202610131200001234",
        "status": 2,
        "created_at": None,
        "completed_at": None,
        "buyer_id": USER_ID,
        "seller_id": SELLER_ID,
        "item_id": ITEM_ID,
        "item_title": "九成新绘本套装",
        "item_images": '["/items/a.jpg", "/items/b.jpg"]',
        "buyer_nickname": "买家小张",
        "seller_nickname": "卖家老王",
    }
    row.update(overrides)
    return row


def _detail_row(**overrides):
    row = {
        "id": ORDER_ID,
        "order_no": "SW202610131200001234",
        "item_id": ITEM_ID,
        "buyer_id": USER_ID,
        "seller_id": SELLER_ID,
        "status": 3,
        "created_at": datetime(2026, 10, 13, 12, 0, 0),
        "completed_at": datetime(2026, 10, 13, 18, 30, 0),
        "item_title": "九成新绘本套装",
        "item_images": '["/items/a.jpg"]',
        "item_status": 2,
        "item_exchange_mode": 2,
        "buyer_nickname": "买家小张",
        "buyer_avatar": None,
        "seller_nickname": "卖家老王",
        "seller_avatar": "/avatars/s.png",
    }
    row.update(overrides)
    return row


def _order_inserts(cursor):
    return [(sql, params) for sql, params in cursor.executed if sql.startswith("INSERT INTO `order`")]


def _log_inserts(cursor):
    return [params for sql, params in cursor.executed if sql.startswith("INSERT INTO points_log")]


def _stat_updates(cursor):
    return [
        params
        for sql, params in cursor.executed
        if sql.startswith("UPDATE user SET exchange_count=COALESCE")
    ]


def _sql_list(cursor):
    return [sql for sql, _ in cursor.executed]


# ============================================================
# 发起交换
# ============================================================
def test_create_order_success(monkeypatch):
    """发起成功：返回 order_id/order_no，INSERT 列清单不含 updated_at / message。"""
    _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[_item_row()])

    resp = order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    assert resp["code"] == 0
    assert resp["message"] == "交换请求已发送，等待对方确认"
    assert resp["data"]["order_id"] == 99

    inserts = _order_inserts(cursor)
    assert len(inserts) == 1
    sql, params = inserts[0]
    # 真实库 `order` 表没有 updated_at / message 列，列清单里绝不能出现
    assert "updated_at" not in sql
    assert "message" not in sql
    assert sql == (
        "INSERT INTO `order` "
        "(order_no, item_id, buyer_id, seller_id, exchange_type, status, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, NOW())"
    )
    order_no = params[0]
    assert order_no.startswith("SW")
    assert len(order_no) == 20
    assert order_no[2:16].isdigit()
    assert order_no[16:].isdigit()
    assert resp["data"]["order_no"] == order_no
    # item_id / buyer_id / seller_id / exchange_mode=2→exchange_type=2 / status=1
    assert list(params[1:]) == [ITEM_ID, USER_ID, SELLER_ID, 2, 1]


def test_create_order_without_message_skips_private_message(monkeypatch):
    """留言为空 / 全空白时不发私信。"""
    messenger = _patch_messenger(monkeypatch)
    # 每次发起会消耗两行：SELECT item 的结果 + 重复订单检查的结果（None=无进行中订单）
    _patch(monkeypatch, rows=[_item_row(), None, _item_row(), None])

    order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)
    order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID, message="   "), user_id=USER_ID)

    assert messenger.calls == []


def test_create_order_sends_message_after_order_committed(monkeypatch):
    """带留言：私信发生在订单事务**提交之后**（两次独立连接），参数正确。"""
    cursor = FakeCursor(rows=[_item_row()], lastrowid=88)
    conn = FakeConn(cursor)

    from contextlib import contextmanager

    @contextmanager
    def _conn():
        # 与 app.db.pool.connection 同构：正常退出时 commit，异常时 rollback
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr(order_api, "connection", _conn)

    seen = {}

    def fake_send(**kwargs):
        seen["committed"] = conn.committed
        seen["kwargs"] = kwargs
        return 1

    monkeypatch.setattr(order_api.message_service, "send_message", fake_send)

    resp = order_api.create_order(
        order_api.OrderCreate(item_id=ITEM_ID, message="  想要这台相机，周末方便面交  "),
        user_id=USER_ID,
    )

    assert resp["code"] == 0
    # 私信被调用时订单事务已 commit
    assert seen["committed"] is True
    assert seen["kwargs"] == {
        "sender_id": USER_ID,
        "receiver_id": SELLER_ID,
        "content": "想要这台相机，周末方便面交",
        "item_id": ITEM_ID,
    }


def test_create_order_own_item_400(monkeypatch):
    """不能交换自己的物品：400 且不写订单。"""
    messenger = _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[_item_row(user_id=USER_ID)])

    with pytest.raises(HTTPException) as exc:
        order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "不能交换自己的物品"
    assert _order_inserts(cursor) == []
    assert messenger.calls == []


def test_create_order_off_shelf_item_400(monkeypatch):
    """物品已下架：400。"""
    _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[_item_row(status=2)])

    with pytest.raises(HTTPException) as exc:
        order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "该物品已下架或已被交换"
    assert _order_inserts(cursor) == []


def test_create_order_missing_item_404(monkeypatch):
    """物品不存在：404。"""
    _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[])

    with pytest.raises(HTTPException) as exc:
        order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    assert exc.value.status_code == 404
    assert exc.value.detail == "物品不存在"
    assert cursor.executed and len(cursor.executed) == 1


def test_create_order_duplicate_ongoing_400(monkeypatch):
    """已有进行中订单（status 1/2）时不允许重复发起，且 SQL 确实按 1、2 过滤。"""
    messenger = _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[_item_row(), {"id": 3}])

    with pytest.raises(HTTPException) as exc:
        order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    assert exc.value.status_code == 400
    assert "发起过交换请求" in exc.value.detail
    dup_sql, dup_params = cursor.executed[1]
    assert "status IN (%s,%s)" in dup_sql
    assert list(dup_params) == [USER_ID, ITEM_ID, 1, 2]
    assert _order_inserts(cursor) == []
    assert messenger.calls == []


def test_create_order_rejects_overlong_message_400(monkeypatch):
    """留言超过 200 字：400，且不下发任何 SQL。"""
    _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[_item_row()])

    with pytest.raises(HTTPException) as exc:
        order_api.create_order(
            order_api.OrderCreate(item_id=ITEM_ID, message="字" * 201), user_id=USER_ID
        )

    assert exc.value.status_code == 400
    assert "留言不能超过" in exc.value.detail
    assert cursor.executed == []


# ============================================================
# 发起交换：健壮性
# ============================================================
class _DuplicateOnceCursor(FakeCursor):
    """第一次 INSERT INTO `order` 抛唯一键冲突（1062），之后正常执行。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_insert_attempts = 0

    def execute(self, sql, params=None):
        if sql.startswith("INSERT INTO `order`"):
            self.order_insert_attempts += 1
            if self.order_insert_attempts == 1:
                raise pymysql.err.IntegrityError(1062, "Duplicate entry 'x' for key 'uk_order_no'")
        super().execute(sql, params)


def test_create_order_retries_on_order_no_collision(monkeypatch):
    """订单号撞唯一索引时重新生成并重试，最终成功。"""
    _patch_messenger(monkeypatch)
    cursor = _DuplicateOnceCursor(rows=[_item_row()], lastrowid=77)
    monkeypatch.setattr(order_api, "connection", make_connection(cursor))

    resp = order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    assert resp["code"] == 0
    assert cursor.order_insert_attempts == 2
    assert len(_order_inserts(cursor)) == 1


class _NonUniqueIntegrityCursor(FakeCursor):
    """抛非唯一键的完整性错误（如非空约束 1048）——属于真实表结构问题，必须原样抛出。"""

    def execute(self, sql, params=None):
        if sql.startswith("INSERT INTO `order`"):
            raise pymysql.err.IntegrityError(1048, "Column 'order_no' cannot be null")
        super().execute(sql, params)


def test_create_order_does_not_swallow_non_unique_integrity_error(monkeypatch):
    """非 1062 的 IntegrityError 原样抛出，不伪装成「订单号重复」重试。"""
    _patch_messenger(monkeypatch)
    cursor = _NonUniqueIntegrityCursor(rows=[_item_row()])
    monkeypatch.setattr(order_api, "connection", make_connection(cursor))

    with pytest.raises(pymysql.err.IntegrityError):
        order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    # 失败的 INSERT 在 super().execute 之前就抛了，因此没有任何成功的订单写入，
    # 说明确实没有把它当成「订单号重复」而重试第二次
    assert _order_inserts(cursor) == []
    assert all("INSERT INTO `order`" not in sql for sql in _sql_list(cursor))


def test_create_order_message_failure_does_not_fail_order(monkeypatch, caplog):
    """私信失败：订单仍成功，仅记一条 warning（不回滚、无补偿）。"""
    _patch_messenger(monkeypatch, error=RuntimeError("私信服务不可用"))
    cursor = _patch(monkeypatch, rows=[_item_row()])

    with caplog.at_level(logging.WARNING):
        resp = order_api.create_order(
            order_api.OrderCreate(item_id=ITEM_ID, message="你好"), user_id=USER_ID
        )

    assert resp["code"] == 0
    assert len(_order_inserts(cursor)) == 1
    assert "已创建，但私信发送失败" in caplog.text


# ============================================================
# 端点契约：exchange_type 映射 / 发奖函数共用
# ============================================================
@pytest.mark.parametrize(
    "exchange_mode,expected",
    [
        (1, 3),   # 赠送 -> 赠送
        (2, 2),   # 交换 -> 以物换物
        (3, 1),   # 低价转让 -> 购买
        (None, 2),  # NULL 兜底：以物换物
        (99, 2),    # 未知值兜底：以物换物
    ],
)
def test_create_order_maps_exchange_type(monkeypatch, exchange_mode, expected):
    """`item.exchange_mode` -> `order.exchange_type` 必须显式映射（枚举含义不同）。"""
    _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[_item_row(exchange_mode=exchange_mode)])

    order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    _, params = _order_inserts(cursor)[0]
    assert params[4] == expected
    assert order_api.EXCHANGE_TYPE_BY_MODE == {1: 3, 2: 2, 3: 1}


def test_admin_and_user_share_one_reward_function():
    """发奖逻辑只存在一份：admin/order.py 引用 services 层的实现（防止两套规则漂移）。"""
    assert admin_order.reward_exchange_completion is order_service.reward_exchange_completion


def test_generate_order_no_format():
    """订单号形态：SW + yyyyMMddHHmmss + 4 位随机，共 20 字符。"""
    order_no = order_service.generate_order_no(datetime(2026, 10, 13, 19, 5, 3))
    assert order_no[:2] == "SW"
    assert order_no[2:16] == "20261013190503"
    assert len(order_no) == 20
    assert order_no[16:].isdigit()


# ============================================================
# 列表
# ============================================================
def test_list_orders_role_buyer_filter(monkeypatch):
    """role=buyer：只查 buyer_id（参数顺序：user_id + LIMIT/OFFSET）。"""
    cursor = _patch(monkeypatch, rows=[{"total": 0}])

    resp = order_api.list_orders(role="buyer", status=None, page=1, size=10, user_id=USER_ID)

    assert resp["data"] == {"total": 0, "page": 1, "size": 10, "list": []}
    count_sql, count_params = cursor.executed[0]
    assert count_sql.endswith("WHERE o.buyer_id=%s")
    assert list(count_params) == [USER_ID]
    assert list(cursor.executed[1][1]) == [USER_ID, 10, 0]


def test_list_orders_role_seller_filter(monkeypatch):
    """role=seller：只查 seller_id。"""
    cursor = _patch(monkeypatch, rows=[{"total": 1}, _list_row()])

    order_api.list_orders(role="seller", status=None, page=2, size=3, user_id=SELLER_ID)

    count_sql, count_params = cursor.executed[0]
    assert count_sql.endswith("WHERE o.seller_id=%s")
    assert list(count_params) == [SELLER_ID]
    # 第 2 页、每页 3 条 -> OFFSET 3
    assert list(cursor.executed[1][1]) == [SELLER_ID, 3, 3]


def test_list_orders_role_all_and_status_filter(monkeypatch):
    """role=all：buyer OR seller 双参数；status 追加到条件与参数尾部。"""
    cursor = _patch(monkeypatch, rows=[{"total": 1}, _list_row()])

    order_api.list_orders(role="all", status=3, page=1, size=10, user_id=USER_ID)

    count_sql, count_params = cursor.executed[0]
    assert "(o.buyer_id=%s OR o.seller_id=%s)" in count_sql
    assert "o.status=%s" in count_sql
    assert list(count_params) == [USER_ID, USER_ID, 3]
    assert list(cursor.executed[1][1]) == [USER_ID, USER_ID, 3, 10, 0]


def test_list_orders_illegal_role_400(monkeypatch):
    """role 非法：400 明确中文提示。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        order_api.list_orders(role="admin", status=None, page=1, size=10, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "role 只能是 buyer / seller / all"
    assert cursor.executed == []


def test_list_orders_illegal_status_400(monkeypatch):
    """status 非法（不在 1-5）：400。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        order_api.list_orders(role="all", status=9, page=1, size=10, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "不支持的订单状态"
    assert cursor.executed == []


def test_list_orders_item_fields_buyer_view(monkeypatch):
    """买家视角：对方是卖家，物品取首图，状态标签来自常量表。"""
    _patch(monkeypatch, rows=[{"total": 1}, _list_row()])

    resp = order_api.list_orders(role="buyer", status=None, page=1, size=10, user_id=USER_ID)
    item = resp["data"]["list"][0]

    assert item["viewer_role"] == "buyer"
    assert item["other_user_id"] == SELLER_ID
    assert item["other_nickname"] == "卖家老王"
    assert item["item_title"] == "九成新绘本套装"
    assert item["item_image"] == "/sign?items/a.jpg"
    assert item["status"] == 2
    assert item["status_label"] == "交换中"


def test_list_orders_item_fields_seller_view(monkeypatch):
    """卖家视角：对方是买家（同一笔订单，viewer 不同则「对方」相反）。"""
    _patch(monkeypatch, rows=[{"total": 1}, _list_row()])

    resp = order_api.list_orders(role="seller", status=None, page=1, size=10, user_id=SELLER_ID)
    item = resp["data"]["list"][0]

    assert item["viewer_role"] == "seller"
    assert item["other_user_id"] == USER_ID
    assert item["other_nickname"] == "买家小张"


def test_list_orders_deleted_item_degrades(monkeypatch):
    """物品已被删除（LEFT JOIN 取不到 title）：展示「物品已不存在」，无图不报错。"""
    _patch(monkeypatch, rows=[{"total": 1}, _list_row(item_title=None, item_images=None)])

    resp = order_api.list_orders(role="buyer", status=None, page=1, size=10, user_id=USER_ID)
    item = resp["data"]["list"][0]

    assert item["item_title"] == "物品已不存在"
    assert item["item_image"] is None
    # order.item_id 是 NOT NULL，仍可用于展示 / 跳转
    assert item["item_id"] == ITEM_ID


def test_list_orders_nickname_fallback(monkeypatch):
    """对方昵称为空（用户被删）时给出可读兜底，不渲染 null。"""
    _patch(monkeypatch, rows=[{"total": 1}, _list_row(seller_nickname=None)])

    resp = order_api.list_orders(role="buyer", status=None, page=1, size=10, user_id=USER_ID)

    assert resp["data"]["list"][0]["other_nickname"] == f"用户{SELLER_ID}"


def test_list_orders_clamps_pagination(monkeypatch):
    """分页参数越界被夹紧（不报 422，避免英文报错透出）。"""
    cursor = _patch(monkeypatch, rows=[{"total": 0}])

    resp = order_api.list_orders(role="all", status=None, page=0, size=999, user_id=USER_ID)

    assert resp["data"]["page"] == 1
    assert resp["data"]["size"] == 50
    assert list(cursor.executed[1][1])[-2:] == [50, 0]


# ============================================================
# 详情
# ============================================================
def test_order_detail_forbidden_for_outsider(monkeypatch):
    """第三方查看订单：403。"""
    cursor = _patch(monkeypatch, rows=[_detail_row()])

    with pytest.raises(HTTPException) as exc:
        order_api.get_order_detail(ORDER_ID, user_id=OUTSIDER_ID)

    assert exc.value.status_code == 403
    assert exc.value.detail == "无权查看该订单"
    # 未越权读取私信
    assert len(cursor.executed) == 1


def test_order_detail_missing_404(monkeypatch):
    """订单不存在：404。"""
    _patch(monkeypatch, rows=[])

    with pytest.raises(HTTPException) as exc:
        order_api.get_order_detail(ORDER_ID, user_id=USER_ID)

    assert exc.value.status_code == 404
    assert exc.value.detail == "订单不存在"


def test_order_detail_returns_timeline_and_messages(monkeypatch):
    """详情：时间线由「状态 + 时间戳」推导（无状态历史表），消息按时间升序。"""
    # 私信 SQL 是 ORDER BY id DESC，这里按该顺序提供，断言输出被反转回升序
    rows = [
        _detail_row(),
        {"id": 22, "sender_id": SELLER_ID, "content": "周末可以", "created_at": None,
         "sender_nickname": "卖家老王"},
        {"id": 21, "sender_id": USER_ID, "content": "在吗？", "created_at": None,
         "sender_nickname": "买家小张"},
    ]
    cursor = _patch(monkeypatch, rows=rows)

    resp = order_api.get_order_detail(ORDER_ID, user_id=USER_ID)
    data = resp["data"]

    assert data["status"] == 3
    assert data["status_label"] == "已完成"
    assert data["viewer_role"] == "buyer"
    assert data["buyer"]["nickname"] == "买家小张"
    assert data["seller"]["nickname"] == "卖家老王"
    assert data["item"]["title"] == "九成新绘本套装"
    assert data["item"]["cover"] == "/sign?items/a.jpg"
    assert data["item"]["status_label"] == "已下架"

    assert [node["status"] for node in data["timeline"]] == [1, 2, 3]
    # 首节点（待确认）有创建时间；完成节点有 completed_at；中间态无时间戳
    assert data["timeline"][0]["at"] is not None
    assert data["timeline"][1]["at"] is None
    assert data["timeline"][2]["at"] is not None
    assert [m["id"] for m in data["messages"]] == [21, 22]

    msg_sql, msg_params = cursor.executed[1]
    assert "ORDER BY pm.id DESC" in msg_sql
    assert list(msg_params)[:5] == [ITEM_ID, USER_ID, SELLER_ID, SELLER_ID, USER_ID]


def test_order_detail_cancelled_timeline(monkeypatch):
    """已取消订单的时间线：待确认 → 交换中 → 已取消（无完成节点）。"""
    _patch(monkeypatch, rows=[_detail_row(status=4, completed_at=None)])

    resp = order_api.get_order_detail(ORDER_ID, user_id=SELLER_ID)
    data = resp["data"]

    assert data["viewer_role"] == "seller"
    assert [node["status_label"] for node in data["timeline"]] == ["待确认", "交换中", "已取消"]


# ============================================================
# 确认交换（1 -> 2）
# ============================================================
def test_confirm_order_by_seller_ok(monkeypatch):
    """卖家确认：条件更新 1→2。"""
    cursor = _patch(monkeypatch, rows=[_order_row()])

    resp = order_api.confirm_order(ORDER_ID, user_id=SELLER_ID)

    assert resp["message"] == "已确认交换，请及时完成交接"
    assert resp["data"] == {"order_id": ORDER_ID, "status": 2, "status_label": "交换中"}
    sql, params = cursor.executed[1]
    assert sql == "UPDATE `order` SET status=%s WHERE id=%s AND status=%s"
    assert list(params) == [2, ORDER_ID, 1]


def test_confirm_order_by_non_seller_403(monkeypatch):
    """买家不能替卖家确认：403。"""
    cursor = _patch(monkeypatch, rows=[_order_row()])

    with pytest.raises(HTTPException) as exc:
        order_api.confirm_order(ORDER_ID, user_id=USER_ID)

    assert exc.value.status_code == 403
    assert exc.value.detail == "只有物品发布者可以确认交换"
    assert len(cursor.executed) == 1


def test_confirm_order_wrong_status_400(monkeypatch):
    """状态不是「待确认」时不能确认：400。"""
    cursor = _patch(monkeypatch, rows=[_order_row(status=2)])

    with pytest.raises(HTTPException) as exc:
        order_api.confirm_order(ORDER_ID, user_id=SELLER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "只有待确认的订单可以确认交换"
    assert len(cursor.executed) == 1


def test_confirm_order_state_changed_400(monkeypatch):
    """条件更新 rowcount=0（并发下已被改）：400 明确提示刷新。"""
    _patch(monkeypatch, rows=[_order_row()], rowcount=0)

    with pytest.raises(HTTPException) as exc:
        order_api.confirm_order(ORDER_ID, user_id=SELLER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "订单状态已变更，请刷新后重试"


# ============================================================
# 完成交换（2 -> 3）
# ============================================================
def test_complete_order_awards_both_sides_and_off_shelves_item(monkeypatch):
    """首次完成：双方各发一次分 + 累加统计 + 物品置为已下架 + 写 completed_at。"""
    cursor = _patch(monkeypatch, rows=[
        _order_row(status=2),          # SELECT order
        {"config_value": "50"},        # points_exchange
        {"config_value": "5.0"},       # carbon_per_exchange
        {"points": 150},               # 卖家余额回读
        {"points": 130},               # 买家余额回读
    ])

    resp = order_api.complete_order(ORDER_ID, user_id=USER_ID)

    assert resp["data"]["status"] == 3
    assert resp["data"]["points_awarded"] == 50
    assert resp["data"]["carbon_added"] == 5.0

    sqls = _sql_list(cursor)
    # ① 订单条件更新：带 AND status=2（并发防重）
    order_sql, order_params = cursor.executed[1]
    assert order_sql == "UPDATE `order` SET status=%s, completed_at=NOW() WHERE id=%s AND status=%s"
    assert list(order_params) == [3, ORDER_ID, 2]
    # ② 物品下架
    item_sql, item_params = cursor.executed[2]
    assert item_sql == "UPDATE item SET status=%s WHERE id=%s AND status=%s"
    assert list(item_params) == [2, ITEM_ID, 1]
    # ③ 双方各发一次分（卖家在前）+ 各累加一次统计
    assert [list(p) for p in _log_inserts(cursor)] == [
        [SELLER_ID, 50, 150, 2, ORDER_ID, "完成交换奖励（作为卖家）"],
        [USER_ID, 50, 130, 2, ORDER_ID, "完成交换奖励（作为买家）"],
    ]
    assert [list(p) for p in _stat_updates(cursor)] == [[5.0, SELLER_ID], [5.0, USER_ID]]
    assert "UPDATE item SET status=%s WHERE id=%s AND status=%s" in sqls


def test_complete_order_self_exchange_awards_once(monkeypatch):
    """买家==卖家（脏数据）时只结算一次，避免同一账号双倍奖励。"""
    cursor = _patch(monkeypatch, rows=[
        _order_row(status=2, seller_id=USER_ID),
        {"config_value": "50"},
        {"config_value": "5.0"},
        {"points": 150},
    ])

    resp = order_api.complete_order(ORDER_ID, user_id=USER_ID)

    assert resp["data"]["points_awarded"] == 50
    assert len(_log_inserts(cursor)) == 1
    assert len(_stat_updates(cursor)) == 1
    assert list(_log_inserts(cursor)[0]) == [USER_ID, 50, 150, 2, ORDER_ID, "完成交换奖励"]


def test_complete_order_by_outsider_403(monkeypatch):
    """非订单双方不能完成：403。"""
    cursor = _patch(monkeypatch, rows=[_order_row(status=2)])

    with pytest.raises(HTTPException) as exc:
        order_api.complete_order(ORDER_ID, user_id=OUTSIDER_ID)

    assert exc.value.status_code == 403
    assert exc.value.detail == "无权操作该订单"
    assert len(cursor.executed) == 1


def test_complete_order_wrong_status_400(monkeypatch):
    """状态不是「交换中」不能完成：400，且不发分、不下架物品。"""
    cursor = _patch(monkeypatch, rows=[_order_row(status=1)])

    with pytest.raises(HTTPException) as exc:
        order_api.complete_order(ORDER_ID, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "只有交换中的订单可以完成"
    assert len(cursor.executed) == 1
    assert _log_inserts(cursor) == []


def test_complete_order_state_conflict_400(monkeypatch):
    """并发下状态已被另一方改掉（rowcount=0）：400，且不发分、不下架物品。"""
    cursor = _patch(monkeypatch, rows=[_order_row(status=2)], rowcount=0)

    with pytest.raises(HTTPException) as exc:
        order_api.complete_order(ORDER_ID, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "订单状态已变更，请刷新后重试"
    # 只执行了 SELECT order + 条件 UPDATE order
    assert len(cursor.executed) == 2
    assert _log_inserts(cursor) == []
    assert all(not sql.startswith("UPDATE item") for sql in _sql_list(cursor))


# ============================================================
# 取消（1 / 2 -> 4）
# ============================================================
def test_cancel_order_from_pending_ok(monkeypatch):
    """取消：1→4，条件更新覆盖 1/2 两种前置态。"""
    cursor = _patch(monkeypatch, rows=[_order_row(status=1)])

    resp = order_api.cancel_order(ORDER_ID, user_id=USER_ID)

    assert resp["message"] == "订单已取消"
    assert resp["data"]["status"] == 4
    sql, params = cursor.executed[1]
    assert sql == "UPDATE `order` SET status=%s WHERE id=%s AND status IN (%s,%s)"
    assert list(params) == [4, ORDER_ID, 1, 2]


def test_cancel_order_from_ongoing_ok(monkeypatch):
    """交换中也能取消。"""
    cursor = _patch(monkeypatch, rows=[_order_row(status=2)])

    resp = order_api.cancel_order(ORDER_ID, user_id=SELLER_ID)

    assert resp["data"]["status_label"] == "已取消"
    assert list(cursor.executed[1][1]) == [4, ORDER_ID, 1, 2]


def test_cancel_order_finished_400(monkeypatch):
    """已完成 / 已取消 / 争议中都不能再取消：400。"""
    cursor = _patch(monkeypatch, rows=[_order_row(status=3)])

    with pytest.raises(HTTPException) as exc:
        order_api.cancel_order(ORDER_ID, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "该订单已结束，无法取消"
    assert len(cursor.executed) == 1


def test_cancel_order_by_outsider_403(monkeypatch):
    """非订单双方不能取消：403。"""
    cursor = _patch(monkeypatch, rows=[_order_row(status=1)])

    with pytest.raises(HTTPException) as exc:
        order_api.cancel_order(ORDER_ID, user_id=OUTSIDER_ID)

    assert exc.value.status_code == 403
    assert exc.value.detail == "无权操作该订单"
    assert len(cursor.executed) == 1


def test_cancel_order_state_changed_400(monkeypatch):
    """条件更新 rowcount=0：400。"""
    _patch(monkeypatch, rows=[_order_row(status=1)], rowcount=0)

    with pytest.raises(HTTPException) as exc:
        order_api.cancel_order(ORDER_ID, user_id=USER_ID)

    assert exc.value.status_code == 400
    assert exc.value.detail == "订单状态已变更，请刷新后重试"
