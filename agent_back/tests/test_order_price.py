"""发起交换「成交金额」写入 + exchange_type 映射的补充测试（数据库 mock）。

对应需求 1 的订单侧：
- 低价转让（item.exchange_mode=3 → order.exchange_type=1 购买）**必须**把
  item.price 落到 `order.price`；
- 免费送 / 交换（type=3 / 2）**不写金额**——INSERT 列清单保持历史原样，
  既有 test_user_orders.py 的 SQL 形状断言因此不受影响。

与 test_user_orders.py 同约定：不连真实库，只断言 SQL 形状 + 参数。
"""
from decimal import Decimal

import pytest

from conftest import FakeCursor, make_connection

from app.api.v1 import order as order_api
from app.services.order_service import resolve_order_price

USER_ID = 7
SELLER_ID = 8
ITEM_ID = 25

PURCHASE_SQL = (
    "INSERT INTO `order` "
    "(order_no, item_id, buyer_id, seller_id, exchange_type, status, "
    " created_at, price) "
    "VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)"
)


def _patch(monkeypatch, rows=None, lastrowid=99):
    cursor = FakeCursor(rows=rows, rowcount=1, lastrowid=lastrowid)
    monkeypatch.setattr(order_api, "connection", make_connection(cursor))
    return cursor


def _item_row(**overrides):
    row = {"id": ITEM_ID, "user_id": SELLER_ID, "status": 1, "exchange_mode": 3, "price": "88.50"}
    row.update(overrides)
    return row


def _patch_messenger(monkeypatch):
    from test_user_orders import _patch_messenger as patch
    return patch(monkeypatch)


def _order_inserts(cursor):
    return [(sql, params) for sql, params in cursor.executed if sql.startswith("INSERT INTO `order`")]


# ============================================================
# order.price 写入
# ============================================================
def test_create_order_for_sell_writes_item_price(monkeypatch):
    """低价转让：order.price = item.price，且 exchange_type=1（购买）。"""
    _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[_item_row(exchange_mode=3, price="88.50"), None])

    resp = order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    assert resp["code"] == 0
    inserts = _order_inserts(cursor)
    assert len(inserts) == 1
    sql, params = inserts[0]
    assert sql == PURCHASE_SQL
    # order_no, item_id, buyer_id, seller_id, exchange_type, status, price
    assert list(params[1:6]) == [ITEM_ID, USER_ID, SELLER_ID, 1, 1]
    assert Decimal(str(params[6])) == Decimal("88.50")


def test_create_order_for_give_has_no_amount(monkeypatch):
    """免费送：exchange_type=3（赠送），INSERT 列清单里没有 price。"""
    _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[_item_row(exchange_mode=1, price="0.00"), None])

    order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    sql, params = _order_inserts(cursor)[0]
    assert "price" not in sql
    assert list(params[1:6]) == [ITEM_ID, USER_ID, SELLER_ID, 3, 1]


def test_create_order_for_swap_has_no_amount(monkeypatch):
    """交换：exchange_type=2（以物换物），不写金额。"""
    _patch_messenger(monkeypatch)
    cursor = _patch(monkeypatch, rows=[_item_row(exchange_mode=2, price="0.00"), None])

    order_api.create_order(order_api.OrderCreate(item_id=ITEM_ID), user_id=USER_ID)

    sql, params = _order_inserts(cursor)[0]
    assert "price" not in sql
    assert list(params[1:6]) == [ITEM_ID, USER_ID, SELLER_ID, 2, 1]


@pytest.mark.parametrize(
    "item_price,expected",
    [
        (None, Decimal("0.00")),          # 无价（历史脏数据）→ 0，不阻断下单
        ("", Decimal("0.00")),
        ("0", Decimal("0.00")),
        ("-3", Decimal("0.00")),          # 负数按 0 处理，不让脏值入库
        ("abc", Decimal("0.00")),         # 非数字按 0 处理
        ("12.345", Decimal("12.34")),     # 量化到 2 位
        (Decimal("99.90"), Decimal("99.90")),
    ],
)
def test_resolve_order_price_robustness(item_price, expected):
    """resolve_order_price 对脏数据不抛错，购买单按 2 位小数落库。"""
    assert resolve_order_price(1, item_price) == expected


def test_resolve_order_price_zero_for_non_purchase():
    """非购买单（赠送 / 以物换物）一律 0，忽略物品价格。"""
    assert resolve_order_price(2, "500") == Decimal("0.00")
    assert resolve_order_price(3, "500") == Decimal("0.00")
