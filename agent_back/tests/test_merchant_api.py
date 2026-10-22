"""商家端闭环 单元测试（数据库 mock，不连真实 MySQL）。

覆盖：
- 入驻申请：首次 / 待审核重提 / 被拒重提 / 已通过拒绝 / 字段校验
- 店铺信息：未入驻返回 null
- 商品管理：上架（需已通过审核）、改（归属校验）、下架、超长字段
- 用户端：商家列表只出已通过、店铺商品、待审核店铺 404
- 兑换：成功扣分扣库存、积分不足、库存不足、免费商品跳扣分、不能兑自己的店
- 核销：成功、重复核销、过期、码不存在、码不属于本店
- 过期退还：source=7 退分、免费单不退、已处理单跳过
- 结算：佣金换算、幂等、周期格式
- 看板：今日/累计/去重/热销/7 日趋势补点
- 迁移与种子：建表幂等、种子数据幂等

设计约定：
- 服务层函数收 `cursor`、不自开事务，因此大部分用例直接以假游标调用服务层；
  接口层用例则 monkeypatch `merchant.connection` 后直接调用 endpoint 函数。
- `KeyedCursor` 按 SQL 片段返回预设结果，避免依赖 fetchone/fetchall 的调用顺序
  （一个看板接口会连续发 4 条查询，其中 2 条是 fetchall，顺序型假游标会把结果串位）。
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from conftest import FakeConn, FakeCursor, make_connection

from app.api.v1 import merchant as merchant_api
from app.core.config import settings
from app.db import pool
from app.services import merchant_service as svc

USER_ID = 7
MERCHANT_ID = 3
PRODUCT_ID = 55


# ============================================================
# 假游标 / 假连接工具
# ============================================================
class KeyedCursor(FakeCursor):
    """按 SQL 中出现的片段返回预设结果，不依赖调用顺序。"""

    def __init__(self, results: dict | None = None, rowcount: int = 1, lastrowid: int = 1):
        super().__init__(rows=[], rowcount=rowcount, lastrowid=lastrowid)
        self._results = results or {}
        self._current: list = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
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


def _patch_api(monkeypatch, cursor):
    monkeypatch.setattr(merchant_api, "connection", make_connection(cursor))
    return cursor


def _patch_service(monkeypatch, cursors):
    """按「第几次开连接」依次返回不同假游标（过期任务每单一个独立事务）。"""
    queue = list(cursors)

    @contextmanager
    def _conn():
        yield FakeConn(queue.pop(0) if queue else FakeCursor())

    monkeypatch.setattr(svc, "connection", _conn)


def _sqls(cursor) -> list[str]:
    return [sql for sql, _ in cursor.executed]


def _find(cursor, keyword: str):
    for sql, params in cursor.executed:
        if keyword in sql:
            return sql, params
    raise AssertionError(f"未找到包含 {keyword!r} 的 SQL，实际执行：{_sqls(cursor)}")


def _product(points_cost: int = 50, status: int = 1, merchant_status: int = 1, merchant_user_id=None):
    return {
        "id": PRODUCT_ID,
        "merchant_id": MERCHANT_ID,
        "title": "打印券10张",
        "points_cost": points_cost,
        "status": status,
        "merchant_name": "社区打印店",
        "merchant_user_id": merchant_user_id,
        "merchant_status": merchant_status,
    }


def _merchant_row(status: int = 1):
    return {
        "id": MERCHANT_ID,
        "user_id": USER_ID,
        "name": "社区打印店",
        "category": "打印",
        "contact": "13800000001",
        "address": "小区北门",
        "description": "打印复印",
        "logo_url": None,
        "status": status,
        "commission_rate": 5,
        "audit_reason": None,
        "created_at": datetime(2026, 10, 1, 9, 0, 0),
    }


# ============================================================
# 1-5 入驻申请
# ============================================================
def test_apply_creates_merchant(monkeypatch):
    """首次申请：INSERT（status=0）+ 回查，佣金取 .env 默认值。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({
        "FROM merchant WHERE user_id=": [None],          # 尚未入驻
        "FROM merchant WHERE id=": [_merchant_row(0)],   # 回查刚落库的行
    }, lastrowid=MERCHANT_ID))
    resp = merchant_api.apply_merchant(
        merchant_api.MerchantApplyRequest(name="社区打印店", category="打印"), user_id=USER_ID
    )

    assert resp["code"] == 0
    assert resp["message"] == "入驻申请已提交，请等待审核"
    assert resp["data"]["status"] == 0
    insert_sql, insert_params = _find(cursor, "INSERT INTO merchant")
    assert insert_params[0] == USER_ID
    assert insert_params[-2] == 0          # status=0 待审核
    assert insert_params[-1] == "5.00"     # 佣金默认值（元/积分汇率另算）


def test_apply_resubmit_when_rejected(monkeypatch):
    """被拒后重新申请：UPDATE 原行、status 回到 0、清空审核意见，不新增行。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({
        "FROM merchant WHERE user_id=": [_merchant_row(2)],
        "FROM merchant WHERE id=": [_merchant_row(0)],
    }))
    resp = merchant_api.apply_merchant(
        merchant_api.MerchantApplyRequest(name="社区打印店改名"), user_id=USER_ID
    )

    assert resp["message"] == "已重新提交入驻申请，请等待审核"
    update_sql, params = _find(cursor, "UPDATE merchant SET name=")
    assert "audit_reason=NULL" in update_sql
    assert params[-1] == MERCHANT_ID
    assert not any(sql.startswith("INSERT INTO merchant") for sql in _sqls(cursor))


def test_apply_resubmit_only_overwrites_provided_fields(monkeypatch):
    """重提时未传的可选字段保留原值（不会被静默清空成 NULL）。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({
        "FROM merchant WHERE user_id=": [_merchant_row(2)],
        "FROM merchant WHERE id=": [_merchant_row(0)],
    }))
    merchant_api.apply_merchant(
        merchant_api.MerchantApplyRequest(name="改名", contact="13900000000"), user_id=USER_ID
    )

    sql, params = _find(cursor, "UPDATE merchant SET name=")
    assert "category=" not in sql          # 未传 → 不写进 SET，保留原值
    assert "address=" not in sql
    assert "contact=%s" in sql
    assert params == ["改名", 0, "13900000000", MERCHANT_ID]


def test_apply_resubmit_can_clear_field_with_empty_string(monkeypatch):
    """显式传空串 → 落库 NULL（需要清空某一项时可用）。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({
        "FROM merchant WHERE user_id=": [_merchant_row(2)],
        "FROM merchant WHERE id=": [_merchant_row(0)],
    }))
    merchant_api.apply_merchant(
        merchant_api.MerchantApplyRequest(name="改名", address=""), user_id=USER_ID
    )

    sql, params = _find(cursor, "UPDATE merchant SET name=")
    assert "address=%s" in sql
    assert params == ["改名", 0, None, MERCHANT_ID]


def test_apply_when_approved_returns_400(monkeypatch):
    """已通过审核的账号再次申请：400，且不产生任何写入。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [_merchant_row(1)]}))
    with pytest.raises(HTTPException) as exc:
        merchant_api.apply_merchant(merchant_api.MerchantApplyRequest(name="重复申请"), user_id=USER_ID)

    assert exc.value.status_code == 400
    assert "已入驻" in exc.value.detail
    assert len(_sqls(cursor)) == 1


def test_apply_when_closed_returns_400(monkeypatch):
    """已停业店铺：不允许重新申请。"""
    _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [_merchant_row(3)]}))
    with pytest.raises(HTTPException) as exc:
        merchant_api.apply_merchant(merchant_api.MerchantApplyRequest(name="再来一次"), user_id=USER_ID)
    assert exc.value.status_code == 400
    assert "停业" in exc.value.detail


def test_apply_validates_field_length():
    """字段校验在接口层用中文报错，不触碰数据库。"""
    with pytest.raises(HTTPException) as exc:
        merchant_api.apply_merchant(
            merchant_api.MerchantApplyRequest(name="店" * 101), user_id=USER_ID
        )
    assert exc.value.status_code == 400
    assert "店铺名不能超过 100 个字符" in exc.value.detail

    with pytest.raises(HTTPException) as exc2:
        merchant_api.apply_merchant(merchant_api.MerchantApplyRequest(name="   "), user_id=USER_ID)
    assert "店铺名不能为空" in exc2.value.detail


# ============================================================
# 6 店铺信息
# ============================================================
def test_merchant_info_returns_null_when_not_joined(monkeypatch):
    """未入驻：返回 merchant=null 而不是 404（前端据此渲染入驻表单）。"""
    _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [None]}))
    resp = merchant_api.merchant_info(user_id=USER_ID)

    assert resp["code"] == 0
    assert resp["data"]["merchant"] is None
    assert resp["data"]["enabled"] is True


def test_merchant_info_signs_logo(monkeypatch):
    """logo_url 存相对路径，读取时现场补签名（不落库签名，1 小时即过期）。"""
    row = _merchant_row(1)
    row["logo_url"] = "merchant/abc.png"
    _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [row]}))
    resp = merchant_api.merchant_info(user_id=USER_ID)

    logo = resp["data"]["merchant"]["logo_url"]
    assert logo.startswith("/api/v1/static/merchant/abc.png?exp=")
    assert "sig=" in logo


# ============================================================
# 7-10 商品管理
# ============================================================
def test_create_product_requires_approved_merchant(monkeypatch):
    """待审核店铺不能上架商品（403），且不产生 INSERT。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [_merchant_row(0)]}))
    with pytest.raises(svc.MerchantError) as exc:
        merchant_api.create_product(
            merchant_api.MerchantProductCreate(title="打印券", points_cost=50, stock=10),
            user_id=USER_ID,
        )

    assert exc.value.status_code == 403
    assert not any("INSERT INTO merchant_product" in sql for sql in _sqls(cursor))


def test_create_product_success(monkeypatch):
    """已通过审核：INSERT 商品，points_cost/stock 落库，返回上架状态。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({
        "FROM merchant WHERE user_id=": [_merchant_row(1)],
        "FROM merchant_product WHERE id=": [{
            "id": PRODUCT_ID, "merchant_id": MERCHANT_ID, "title": "打印券10张",
            "points_cost": 50, "stock": 10, "sold_count": 0, "status": 1,
            "created_at": datetime(2026, 10, 15, 10, 0, 0),
        }],
    }, lastrowid=PRODUCT_ID))
    resp = merchant_api.create_product(
        merchant_api.MerchantProductCreate(title="打印券10张", points_cost=50, stock=10),
        user_id=USER_ID,
    )

    assert resp["message"] == "商品已上架"
    assert resp["data"]["points_cost"] == 50
    assert resp["data"]["status_label"] == "上架中"
    insert_sql, params = _find(cursor, "INSERT INTO merchant_product")
    assert tuple(params[:2]) == (MERCHANT_ID, "打印券10张")


def test_create_product_rejects_negative_points(monkeypatch):
    """所需积分/库存越界：接口层 400，不触碰数据库。"""
    with pytest.raises(HTTPException) as exc:
        merchant_api.create_product(
            merchant_api.MerchantProductCreate(title="白送", points_cost=-1, stock=10),
            user_id=USER_ID,
        )
    assert "所需积分必须在 0 到" in exc.value.detail


def test_update_product_ownership_enforced(monkeypatch):
    """改商品把归属写进 WHERE：改不到别人的商品时 rowcount=0 → 404。"""
    cursor = _patch_api(monkeypatch, KeyedCursor(
        {"FROM merchant WHERE user_id=": [_merchant_row(1)]}, rowcount=0,
    ))
    with pytest.raises(HTTPException) as exc:
        merchant_api.update_product(
            PRODUCT_ID, merchant_api.MerchantProductUpdate(points_cost=80), user_id=USER_ID
        )

    assert exc.value.status_code == 404
    sql, params = _find(cursor, "UPDATE merchant_product SET points_cost=")
    assert sql.endswith("WHERE id=%s AND merchant_id=%s")
    assert params == [80, PRODUCT_ID, MERCHANT_ID]


def test_update_product_rejects_empty_payload(monkeypatch):
    """没有任何字段要改：直接 400，不连库。"""
    with pytest.raises(HTTPException) as exc:
        merchant_api.update_product(PRODUCT_ID, merchant_api.MerchantProductUpdate(), user_id=USER_ID)
    assert exc.value.detail == "没有需要修改的内容"


def test_offline_product_sets_status_zero(monkeypatch):
    """下架是软下架：置 status=0，不删行。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [_merchant_row(1)]}))
    resp = merchant_api.offline_product(PRODUCT_ID, user_id=USER_ID)

    assert resp["data"] == {"product_id": PRODUCT_ID, "status": 0}
    sql, params = _find(cursor, "UPDATE merchant_product SET status=")
    assert tuple(params) == (0, PRODUCT_ID, MERCHANT_ID)


# ============================================================
# 11-13 用户端浏览
# ============================================================
def test_list_shops_only_approved(monkeypatch):
    """用户端商家列表：WHERE 固定带 status=1，待审核店铺不可见。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({
        "COUNT(*) AS total FROM merchant m": [{"total": 1}],
        "FROM merchant m WHERE": [{
            "id": MERCHANT_ID, "name": "社区打印店", "category": "打印",
            "address": "小区北门", "contact": "138", "description": "打印",
            "logo_url": None, "product_count": 2,
        }],
    }))
    resp = merchant_api.list_shops(category="打印", page=1, size=10)

    assert resp["data"]["total"] == 1
    assert resp["data"]["list"][0]["product_count"] == 2
    sql, params = _find(cursor, "COUNT(*) AS total FROM merchant m")
    assert "m.status=%s" in sql
    assert params == [1, "打印"]


def test_list_shop_products_hides_pending_merchant(monkeypatch):
    """待审核店铺的商品对用户不可见：404。"""
    _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE id=": [_merchant_row(0)]}))
    with pytest.raises(HTTPException) as exc:
        merchant_api.list_shop_products(MERCHANT_ID)
    assert exc.value.status_code == 404


def test_list_shop_products_returns_only_online(monkeypatch):
    """店铺商品只出 status=1（已下架商品不出现）。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({
        "FROM merchant WHERE id=": [_merchant_row(1)],
        "FROM merchant_product WHERE merchant_id=": [{
            "id": PRODUCT_ID, "merchant_id": MERCHANT_ID, "title": "打印券10张",
            "points_cost": 50, "stock": 10, "sold_count": 3, "status": 1, "created_at": None,
        }],
    }))
    resp = merchant_api.list_shop_products(MERCHANT_ID)

    assert resp["data"]["merchant"]["product_count"] == 1
    assert resp["data"]["list"][0]["sold_count"] == 3
    sql, params = _find(cursor, "FROM merchant_product WHERE merchant_id=")
    assert "AND status=%s" in sql
    assert params == (MERCHANT_ID, 1)


# ============================================================
# 14-18 兑换
# ============================================================
def test_redeem_deducts_points_and_stock(monkeypatch):
    """兑换成功：条件扣库存 + 落单 + awards_points(-cost, source=5, related_id=订单id)。"""
    cursor = FakeCursor(
        rows=[_product(50), {"points": 500}, None, {"points": 450}],
        rowcount=1, lastrowid=99,
    )
    result = svc.redeem(cursor, USER_ID, PRODUCT_ID)

    assert result["order_id"] == 99
    assert result["points_cost"] == 50
    assert result["points_balance"] == 450
    assert len(result["code"]) == 6 and result["code"].isdigit()
    assert result["order_no"].startswith("RD")

    stock_sql, stock_params = _find(cursor, "UPDATE merchant_product SET stock=stock-1")
    assert "AND status=%s AND stock>0" in stock_sql
    assert stock_params == (PRODUCT_ID, 1)

    order_sql, order_params = _find(cursor, "INSERT INTO redemption_order")
    assert order_params[1] == USER_ID and order_params[4] == 50

    log_sql, log_params = _find(cursor, "INSERT INTO points_log")
    assert log_params[0] == USER_ID
    assert log_params[1] == -50                        # 扣分
    assert log_params[2] == 450                        # balance 与 user.points 一致
    assert log_params[3] == svc.SOURCE_REDEEM          # source=5 兑换消耗
    assert log_params[4] == 99                         # related_id=订单id（幂等键）


def test_redeem_insufficient_points_blocks_all_writes(monkeypatch):
    """积分不足：400 且**没有任何写入**（不扣库存、不落单、不写流水）。"""
    cursor = FakeCursor(rows=[_product(500), {"points": 100}], rowcount=1, lastrowid=99)
    with pytest.raises(svc.MerchantError) as exc:
        svc.redeem(cursor, USER_ID, PRODUCT_ID)

    assert exc.value.status_code == 400
    assert "积分不足" in exc.value.message
    assert len(cursor.executed) == 2
    assert not any("INSERT INTO" in sql for sql in _sqls(cursor))


def test_redeem_out_of_stock_blocks_points(monkeypatch):
    """库存为 0：条件更新 rowcount=0 → 400，且积分流水未写。"""
    cursor = FakeCursor(rows=[_product(50), {"points": 500}], rowcount=0, lastrowid=99)
    with pytest.raises(svc.MerchantError) as exc:
        svc.redeem(cursor, USER_ID, PRODUCT_ID)

    assert "库存不足" in exc.value.message
    assert not any("INSERT INTO" in sql for sql in _sqls(cursor))
    assert not any("INSERT INTO points_log" == sql for sql in _sqls(cursor))


def test_redeem_free_product_skips_points(monkeypatch):
    """免费商品（points_cost=0）：不查余额、不写积分流水，但仍占库存与落单。"""
    cursor = FakeCursor(rows=[_product(0), None], rowcount=1, lastrowid=7)
    result = svc.redeem(cursor, USER_ID, PRODUCT_ID)

    assert result["points_cost"] == 0
    assert result["points_balance"] is None
    assert not any("FOR UPDATE" in sql for sql in _sqls(cursor))
    assert not any("INSERT INTO points_log" in sql for sql in _sqls(cursor))


def test_redeem_own_shop_rejected(monkeypatch):
    """不能兑换自己店铺的商品（防止刷分/自循环）。"""
    cursor = FakeCursor(rows=[_product(50, merchant_user_id=USER_ID)], rowcount=1)
    with pytest.raises(svc.MerchantError) as exc:
        svc.redeem(cursor, USER_ID, PRODUCT_ID)

    assert exc.value.status_code == 400
    assert "自己店铺" in exc.value.message
    assert len(cursor.executed) == 1


def test_redeem_offline_product_rejected(monkeypatch):
    """商品已下架 / 店铺未通过审核：拒绝兑换。"""
    cursor = FakeCursor(rows=[_product(50, status=0)], rowcount=1)
    with pytest.raises(svc.MerchantError) as exc:
        svc.redeem(cursor, USER_ID, PRODUCT_ID)
    assert "已下架" in exc.value.message

    cursor2 = FakeCursor(rows=[_product(50, merchant_status=0)], rowcount=1)
    with pytest.raises(svc.MerchantError) as exc2:
        svc.redeem(cursor2, USER_ID, PRODUCT_ID)
    assert "暂未开放兑换" in exc2.value.message


# ============================================================
# 19-23 核销
# ============================================================
def test_verify_success(monkeypatch):
    """核销成功：条件更新 + 回读详情（返回用户昵称与商品名给商家确认）。"""
    cursor = FakeCursor(rows=[
        {"id": 99},
        {"order_no": "RD202610151200001234", "points_cost": 50,
         "redeemed_at": datetime(2026, 10, 15, 12, 0, 0),
         "title": "打印券10张", "nickname": "张阿姨"},
    ], rowcount=1)
    result = svc.verify_redemption(cursor, MERCHANT_ID, "123456")

    assert result["success"] is True
    assert result["user_nickname"] == "张阿姨"
    assert result["product_title"] == "打印券10张"
    update_sql, params = _find(cursor, "UPDATE redemption_order SET status=")
    assert "AND status=%s AND expires_at>NOW()" in update_sql
    assert params[0] == svc.REDEMPTION_STATUS_REDEEMED
    assert params[1:] == (99, MERCHANT_ID, svc.REDEMPTION_STATUS_PENDING)


def test_verify_duplicate_returns_clear_message(monkeypatch):
    """重复核销：rowcount=0 且当前状态为已核销 → 明确提示，不再置位。"""
    cursor = FakeCursor(
        rows=[{"id": 99}, {"status": svc.REDEMPTION_STATUS_REDEEMED}], rowcount=0
    )
    with pytest.raises(svc.MerchantError) as exc:
        svc.verify_redemption(cursor, MERCHANT_ID, "123456")

    assert "已使用" in exc.value.message
    assert len(cursor.executed) == 3
    assert "SELECT o.order_no" not in " ".join(_sqls(cursor))


def test_verify_expired_code(monkeypatch):
    """已过期（后台已置 3）：提示已过期。"""
    cursor = FakeCursor(rows=[{"id": 99}, {"status": svc.REDEMPTION_STATUS_EXPIRED}], rowcount=0)
    with pytest.raises(svc.MerchantError) as exc:
        svc.verify_redemption(cursor, MERCHANT_ID, "123456")
    assert "已过期" in exc.value.message


def test_verify_expired_but_not_swept_yet(monkeypatch):
    """后台尚未扫到（status 仍为 1，但 expires_at 已过）：条件未通过 → 同样报已过期。"""
    cursor = FakeCursor(rows=[{"id": 99}, {"status": svc.REDEMPTION_STATUS_PENDING}], rowcount=0)
    with pytest.raises(svc.MerchantError) as exc:
        svc.verify_redemption(cursor, MERCHANT_ID, "123456")
    assert "已过期" in exc.value.message


def test_verify_code_not_found_and_not_own(monkeypatch):
    """码不存在 → 404；码属于别家 → 403。两者都在任何写入之前返回。"""
    cursor = FakeCursor(rows=[None, None], rowcount=0)
    with pytest.raises(svc.MerchantError) as exc:
        svc.verify_redemption(cursor, MERCHANT_ID, "000000")
    assert exc.value.status_code == 404

    cursor2 = FakeCursor(rows=[None, {"merchant_id": 9}], rowcount=0)
    with pytest.raises(svc.MerchantError) as exc2:
        svc.verify_redemption(cursor2, MERCHANT_ID, "111111")
    assert exc2.value.status_code == 403
    assert "不属于本店" in exc2.value.message


# ============================================================
# 24-26 过期退还（source=7）
# ============================================================
def test_expire_redemptions_refunds_with_source_7(monkeypatch):
    """过期单：置 status=3 并原额退还积分，退还流水用 source=7。"""
    find_cursor = FakeCursor(rows=[{"id": 99}])
    work_cursor = FakeCursor(rows=[{"user_id": USER_ID, "points_cost": 50}, {"points": 550}], rowcount=1)
    empty_cursor = FakeCursor(rows=[])
    _patch_service(monkeypatch, [find_cursor, work_cursor, empty_cursor])

    assert svc.expire_redemptions() == 1

    update_sql, update_params = _find(work_cursor, "UPDATE redemption_order SET status=")
    assert "AND status=%s AND expires_at<=%s" in update_sql
    assert update_params[0] == svc.REDEMPTION_STATUS_EXPIRED

    log_sql, log_params = _find(work_cursor, "INSERT INTO points_log")
    assert log_params[1] == 50          # 原额退回（正数）
    assert log_params[3] == 7           # source=7 兑换过期退还
    assert log_params[4] == 99          # related_id=订单id，与 source=5 那条不冲突


def test_expire_redemptions_skips_free_product(monkeypatch):
    """免费单（points_cost=0）过期：只改状态，不写退还流水。"""
    work_cursor = FakeCursor(rows=[{"user_id": USER_ID, "points_cost": 0}], rowcount=1)
    _patch_service(monkeypatch, [FakeCursor(rows=[{"id": 5}]), work_cursor, FakeCursor(rows=[])])

    assert svc.expire_redemptions() == 1
    assert not any("points_log" in sql for sql in _sqls(work_cursor))


def test_expire_redemptions_skips_already_handled(monkeypatch):
    """已被核销/已被处理（条件更新 rowcount=0）：不计入处理数，且不再写流水。"""
    work_cursor = FakeCursor(rows=[{"user_id": USER_ID, "points_cost": 50}], rowcount=0)
    _patch_service(monkeypatch, [FakeCursor(rows=[{"id": 5}]), work_cursor, FakeCursor(rows=[])])

    assert svc.expire_redemptions() == 0
    assert not any("points_log" in sql for sql in _sqls(work_cursor))


def test_expire_redemptions_tolerates_single_failure(monkeypatch):
    """单笔抛异常不影响整批（每单独立事务）。"""
    broken = FakeCursor(rows=[{"user_id": USER_ID, "points_cost": 50}], rowcount=1)

    def _boom(sql, params=None):
        broken.executed.append((sql, params))
        raise RuntimeError("数据库连接中断")

    broken.execute = _boom  # type: ignore[assignment]
    work_cursor = FakeCursor(rows=[{"user_id": USER_ID, "points_cost": 50}], rowcount=1)

    # 第 1 批：[坏单, 好单]；第 2 批：空
    _patch_service(monkeypatch, [
        FakeCursor(rows=[{"id": 1}, {"id": 2}]),
        broken,
        work_cursor,
        FakeCursor(rows=[]),
    ])

    assert svc.expire_redemptions() == 1
    assert any("points_log" in sql for sql in _sqls(work_cursor))


# ============================================================
# 27-30 结算
# ============================================================
def test_calculate_commission_uses_points_to_yuan_rate():
    """佣金 = 积分总额 × 0.01 元/积分 × 佣金比例%。"""
    # 返回值是 Decimal（写 DECIMAL(10,2) 列不丢精度），断言前转 float
    assert float(svc.calculate_commission(1000, 5)) == pytest.approx(0.50)
    assert float(svc.calculate_commission(100, 5)) == pytest.approx(0.05)
    assert float(svc.calculate_commission(123, 5)) == pytest.approx(0.06)   # 0.0615 → 四舍五入
    assert float(svc.calculate_commission(0, 5)) == pytest.approx(0.00)
    assert float(svc.calculate_commission(1000, 0)) == pytest.approx(0.00)


def test_parse_period_rejects_bad_format():
    """周期格式非法直接 400（避免结算到一半才发现）。"""
    with pytest.raises(svc.MerchantError) as exc:
        svc.parse_period("2026-13")
    assert exc.value.status_code == 400
    assert "YYYY-MM" in exc.value.message

    period, start, end = svc.parse_period("2026-12")
    assert period == "2026-12"
    assert start == datetime(2026, 12, 1)
    assert end == datetime(2027, 1, 1)   # 跨年正确进位


def test_settle_merchant_computes_and_inserts(monkeypatch):
    """结算：按 redeemed_at 区间统计已核销单，写入结算行。"""
    cursor = FakeCursor(rows=[
        {"id": MERCHANT_ID, "name": "社区打印店", "commission_rate": 5},
        None,
        {"c": 3, "p": 1000},
    ], rowcount=1)
    result = svc.settle_merchant(cursor, MERCHANT_ID, "2026-10")

    assert result["redemption_count"] == 3
    assert result["points_total"] == 1000
    assert result["commission_amount"] == pytest.approx(0.50)
    assert result["already_settled"] is False

    count_sql, count_params = _find(cursor, "COALESCE(SUM(points_cost), 0)")
    assert "status=%s AND redeemed_at >= %s AND redeemed_at < %s" in count_sql
    assert count_params == (MERCHANT_ID, svc.REDEMPTION_STATUS_REDEEMED,
                            datetime(2026, 10, 1), datetime(2026, 11, 1))
    assert any("INSERT INTO merchant_settlement" in sql for sql in _sqls(cursor))


def test_settle_merchant_is_idempotent(monkeypatch):
    """重复结算同一周期：直接返回原记录，不重算、不写新行。"""
    cursor = FakeCursor(rows=[
        {"id": MERCHANT_ID, "name": "社区打印店", "commission_rate": 5},
        {"id": 8, "redemption_count": 3, "points_total": 1000, "commission_amount": 0.5,
         "status": 1, "settled_at": datetime(2026, 10, 15, 12, 0, 0)},
    ], rowcount=1)
    result = svc.settle_merchant(cursor, MERCHANT_ID, "2026-10")

    assert result["already_settled"] is True
    assert result["commission_amount"] == pytest.approx(0.5)
    assert len(cursor.executed) == 2
    assert not any("INSERT INTO merchant_settlement" in sql for sql in _sqls(cursor))


# ============================================================
# 31-32 看板
# ============================================================
def test_merchant_dashboard_fills_missing_trend_days(monkeypatch):
    """看板：7 个连续日期点（没有核销的日期补 0），热销榜按 sold_count 降序。"""
    today = date.today()
    cursor = KeyedCursor({
        "AND redeemed_at >= %s AND redeemed_at < %s": [{"c": 2}],
        "COUNT(DISTINCT user_id)": [{"c": 10, "u": 4}],
        "FROM merchant_product": [
            {"title": "打印券10张", "sold_count": 5},
            {"title": "复印券20张", "sold_count": 2},
        ],
        "GROUP BY DATE(redeemed_at)": [{"d": today, "c": 2}],
    })
    data = svc.merchant_dashboard(cursor, MERCHANT_ID)

    assert data["today_redemptions"] == 2
    assert data["total_redemptions"] == 10
    assert data["unique_users"] == 4
    assert [p["title"] for p in data["popular_products"]] == ["打印券10张", "复印券20张"]
    assert len(data["trend"]) == 7
    assert data["trend"][-1] == {"date": today.strftime("%Y-%m-%d"), "count": 2}
    assert data["trend"][0]["count"] == 0
    assert data["trend"][-1]["date"] == (
        today.strftime("%Y-%m-%d")
    )
    assert (datetime.strptime(data["trend"][0]["date"], "%Y-%m-%d").date()
            == today - timedelta(days=6))


def test_redemption_trend_platform_wide():
    """平台趋势：merchant_id 为 None 时不加商家过滤条件。"""
    cursor = FakeCursor(rows=[])
    trend = svc.redemption_trend(cursor, days=7, merchant_id=None)

    assert len(trend) == 7
    sql, params = cursor.executed[0]
    assert "merchant_id=%s" not in sql
    assert len(params) == 2


# ============================================================
# 33-34 管理端审核
# ============================================================
def test_audit_requires_reason_when_rejected():
    """拒绝入驻必须填原因（任务书标为可选，这里收紧）。"""
    from app.routers.admin import merchant as admin_merchant

    with pytest.raises(HTTPException) as exc:
        admin_merchant.audit_merchant(MERCHANT_ID, admin_merchant.AuditRequest(approved=False))
    assert exc.value.status_code == 400
    assert "必须填写原因" in exc.value.detail


def test_audit_approve_and_reject(monkeypatch):
    """审核通过 → status=1；拒绝 → status=2 且原因落库。"""
    from app.routers.admin import merchant as admin_merchant

    cursor = _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE id=": [{"id": MERCHANT_ID, "name": "店"}]}))
    monkeypatch.setattr(admin_merchant, "connection", make_connection(cursor))

    resp = admin_merchant.audit_merchant(MERCHANT_ID, admin_merchant.AuditRequest(approved=True))
    assert resp["code"] == 200          # 管理端外壳
    assert resp["data"]["status"] == 1
    assert resp["data"]["audit_reason"] is None

    resp2 = admin_merchant.audit_merchant(
        MERCHANT_ID, admin_merchant.AuditRequest(approved=False, reason="资质材料不全")
    )
    assert resp2["data"]["status"] == 2
    assert resp2["data"]["audit_reason"] == "资质材料不全"
    # 两次审核各写一次，取最后一次的 params
    updates = [params for sql, params in cursor.executed if "UPDATE merchant SET status=" in sql]
    assert updates == [(1, None, MERCHANT_ID), (2, "资质材料不全", MERCHANT_ID)]


# ============================================================
# 35-40 管理端结算预览（只读 · 冲突 C1 的解）
# ============================================================
def _preview_cursor(merchants, settled=None):
    """构造 preview 接口的假游标。

    两条 SQL 的关键片段互不包含，用 KeyedCursor 按片段取值：
      1) 商家聚合（`LEFT JOIN (`）
      2) 本期结算行（`FROM merchant_settlement WHERE period=`）
    """
    return KeyedCursor(
        {
            "LEFT JOIN (": merchants,
            "FROM merchant_settlement WHERE period=": settled or [],
        }
    )


def _preview(monkeypatch, cursor, period="2026-10"):
    from app.routers.admin import merchant as admin_merchant

    monkeypatch.setattr(admin_merchant, "connection", make_connection(cursor))
    return admin_merchant.preview_settlements(period=period)


def test_preview_settlements_computes_pending_numbers(monkeypatch):
    """未结算：算出核销单数 / 积分总额 / 佣金，且口径与 settle_merchant 一致。"""
    cursor = _preview_cursor(
        [
            {
                "merchant_id": 1,
                "name": "社区打印店",
                "commission_rate": 5,
                "redemption_count": 4,
                "points_total": 260,
            }
        ]
    )
    resp = _preview(monkeypatch, cursor)

    assert resp["code"] == 200  # 管理端外壳
    assert resp["data"]["period"] == "2026-10"
    item = resp["data"]["list"][0]
    assert item["merchant_id"] == 1
    assert item["redemption_count"] == 4
    assert item["points_total"] == 260
    # 260 积分 × 0.01 元/积分 × 5% = 0.13 元
    assert item["commission_amount"] == 0.13
    assert item["settled"] is False
    assert item["settled_at"] is None
    assert resp["data"]["pending_merchants"] == 1
    assert resp["data"]["pending_commission"] == 0.13

    # 口径：status=2(已核销) + redeemed_at 左闭右开 + 只取 status=1(已通过) 的商家
    sql, params = _find(cursor, "LEFT JOIN (")
    assert params[0] == 2      # REDEMPTION_STATUS_REDEEMED
    assert params[1] == datetime(2026, 10, 1)
    assert params[2] == datetime(2026, 11, 1)   # 12 月跨年另有用例
    assert params[3] == 1      # MERCHANT_STATUS_APPROVED
    assert "COUNT(*)" in sql and "SUM(o.points_cost)" in sql


def test_preview_settlements_echoes_already_settled_rows(monkeypatch):
    """本期已结算：回显结算表存量数字（而非重算），并计入 settled=True。"""
    cursor = _preview_cursor(
        [
            {
                "merchant_id": 1,
                "name": "社区打印店",
                "commission_rate": 5,
                "redemption_count": 9,   # 聚合口径与存量不同 → 必须用存量
                "points_total": 999,
            }
        ],
        settled=[
            {
                "id": 9,
                "merchant_id": 1,
                "redemption_count": 4,
                "points_total": 260,
                "commission_amount": Decimal("0.13"),
                "status": 1,
                "settled_at": datetime(2026, 10, 20, 10, 0, 0),
            }
        ],
    )
    resp = _preview(monkeypatch, cursor)

    item = resp["data"]["list"][0]
    assert item["settled"] is True
    assert item["redemption_count"] == 4          # 存量，不是聚合的 9
    assert item["points_total"] == 260            # 存量，不是聚合的 999
    assert item["commission_amount"] == 0.13
    assert item["settled_at"] == datetime(2026, 10, 20, 10, 0, 0)
    # 已结算的不计入「待结算」汇总
    assert resp["data"]["pending_merchants"] == 0
    assert resp["data"]["pending_commission"] == 0.0


def test_preview_settlements_pending_summary_excludes_settled(monkeypatch):
    """待结算汇总只算未结算的商家（跨商家混合场景）。"""
    cursor = _preview_cursor(
        [
            {"merchant_id": 1, "name": "A", "commission_rate": 5, "redemption_count": 4, "points_total": 260},
            {"merchant_id": 2, "name": "B", "commission_rate": 5, "redemption_count": 2, "points_total": 100},
        ],
        settled=[
            {
                "id": 1, "merchant_id": 1, "redemption_count": 4, "points_total": 260,
                "commission_amount": Decimal("0.13"), "status": 1,
                "settled_at": datetime(2026, 10, 20, 10, 0, 0),
            }
        ],
    )
    resp = _preview(monkeypatch, cursor)

    assert resp["data"]["total"] == 2
    assert resp["data"]["pending_merchants"] == 1        # 只剩 B
    assert resp["data"]["pending_commission"] == 0.05    # 100 × 0.01 × 5%
    by_id = {item["merchant_id"]: item for item in resp["data"]["list"]}
    assert by_id[1]["settled"] is True
    assert by_id[2]["settled"] is False


def test_preview_settlements_zero_when_no_redemptions(monkeypatch):
    """当期无核销单的商家：三项都是 0，不是 None（前端要直接显示）。"""
    cursor = _preview_cursor(
        [{"merchant_id": 5, "name": "家政服务站", "commission_rate": 5,
          "redemption_count": 0, "points_total": 0}]
    )
    resp = _preview(monkeypatch, cursor)

    item = resp["data"]["list"][0]
    assert item["redemption_count"] == 0
    assert item["points_total"] == 0
    assert item["commission_amount"] == 0.0
    assert item["settled"] is False


def test_preview_settlements_is_read_only(monkeypatch):
    """纯只读：全程只发 SELECT，绝不写任何表（不可逆操作的预览必须零副作用）。"""
    cursor = _preview_cursor(
        [{"merchant_id": 1, "name": "A", "commission_rate": 5,
          "redemption_count": 1, "points_total": 10}]
    )
    _preview(monkeypatch, cursor)

    for sql, _ in cursor.executed:
        upper = sql.strip().upper()
        assert upper.startswith("SELECT"), sql
        for verb in ("INSERT ", "UPDATE ", "DELETE ", "REPLACE ", "ALTER "):
            assert verb not in upper, f"预览接口不该出现写操作：{sql}"


def test_preview_settlements_rejects_bad_period(monkeypatch):
    """周期格式非法 → 400（与服务层 parse_period 同一套报错）。"""
    cursor = _preview_cursor([])
    from app.routers.admin import merchant as admin_merchant

    monkeypatch.setattr(admin_merchant, "connection", make_connection(cursor))
    with pytest.raises(svc.MerchantError) as exc:
        admin_merchant.preview_settlements(period="2026-1")
    assert exc.value.status_code == 400
    assert "YYYY-MM" in exc.value.message
    # 格式校验在发 SQL 之前就失败了
    assert cursor.executed == []


def test_preview_settlements_december_spans_year(monkeypatch):
    """12 月周期：止 = 次年 1 月 1 日（跨年边界）。"""
    cursor = _preview_cursor([])
    resp = _preview(monkeypatch, cursor, period="2026-12")

    _sql, params = _find(cursor, "LEFT JOIN (")
    assert params[1] == datetime(2026, 12, 1)
    assert params[2] == datetime(2027, 1, 1)
    assert resp["data"]["period"] == "2026-12"


# ============================================================
# 幂等迁移与种子数据
# ============================================================
def test_ensure_merchant_tables_creates_tables_and_is_idempotent(monkeypatch):
    """迁移函数：建 5 张表 + 3 个唯一索引，且重复执行仍然成功（幂等）。"""
    # information_schema 存在性判断统一返回 0（列/索引都不存在）→ 会执行 ADD 语句
    cursor = KeyedCursor({"information_schema": [{"c": 0}]}, rowcount=1)
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_merchant_tables()

    sqls = " ".join(_sqls(cursor))
    for table in ("merchant", "merchant_product", "redemption_order",
                  "merchant_settlement", "merchant_stats"):
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in sqls
    assert pool.MERCHANT_USER_UNIQUE_INDEX in sqls
    assert pool.REDEMPTION_CODE_UNIQUE_INDEX in sqls
    assert pool.REDEMPTION_ORDER_NO_UNIQUE_INDEX in sqls

    # 再跑一次不抛异常即算幂等（关键：没有 ADD COLUMN 重复执行导致的 1060）
    pool.ensure_merchant_tables()


def test_ensure_merchant_tables_swallows_failure(monkeypatch):
    """迁移失败只记 ERROR，不阻断服务启动。"""

    class _Boom(KeyedCursor):
        def execute(self, sql, params=None):
            raise RuntimeError("表已损坏")

    monkeypatch.setattr(pool, "connection", make_connection(_Boom({})))
    pool.ensure_merchant_tables()  # 不抛异常即通过


def test_ensure_merchant_seed_skips_when_exists(monkeypatch):
    """种子数据：已存在（按店名 COUNT>0）时整批跳过，绝不重复插、不覆盖管理员改动。"""
    cursor = KeyedCursor({"SELECT COUNT(*) AS c FROM merchant": [{"c": 5}]})
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_merchant_seed()

    assert not any("INSERT INTO merchant" in sql for sql in _sqls(cursor))
    assert len(_sqls(cursor)) == 1


def test_ensure_merchant_seed_inserts_merchants_and_products(monkeypatch):
    """种子数据：空库时插 5 家商家 + 10 个商品，商品用回查的商品 ID 关联。"""
    cursor = KeyedCursor({
        "SELECT COUNT(*) AS c FROM merchant": [{"c": 0}],
        "SELECT id, name FROM merchant WHERE name IN": [
            {"id": 1, "name": "社区打印店"},
            {"id": 2, "name": "24小时便利店"},
            {"id": 3, "name": "美发工作室"},
            {"id": 4, "name": "绿源回收站"},
            {"id": 5, "name": "家政服务站"},
        ],
    })
    monkeypatch.setattr(pool, "connection", make_connection(cursor))

    pool.ensure_merchant_seed()

    merchant_sql, merchant_params = _find(cursor, "INSERT INTO merchant (")
    assert merchant_params.count("5.00") == 5          # 佣金取 .env 默认值
    assert merchant_sql.count(", 1, %s)") == 5         # status=1 已通过审核（写在 SQL 字面量里）

    product_sql, product_params = _find(cursor, "INSERT INTO merchant_product")
    assert product_params.count(1) == 2                # 社区打印店 2 个商品
    assert 0 in product_params                         # 免费券（旧家电估价券）
    assert len(product_params) % 5 == 0
    assert len(product_params) // 5 == 10


# ============================================================
# 38 端到端串起来：兑换 → 核销 → 结算
# ============================================================
def test_full_loop_redeem_verify_settle(monkeypatch):
    """闭环冒烟：兑换（扣分清零）→ 核销（置已核销）→ 结算（算佣金）。"""
    # 1. 兑换：500 分 → 450 分
    redeem_cursor = FakeCursor(rows=[_product(50), {"points": 500}, None, {"points": 450}],
                               rowcount=1, lastrowid=99)
    order = svc.redeem(redeem_cursor, USER_ID, PRODUCT_ID)
    assert order["points_balance"] == 450

    # 2. 核销
    verify_cursor = FakeCursor(rows=[
        {"id": 99},
        {"order_no": order["order_no"], "points_cost": 50,
         "redeemed_at": datetime(2026, 10, 15, 12, 0, 0), "title": "打印券10张",
         "nickname": "张阿姨"},
    ], rowcount=1)
    verified = svc.verify_redemption(verify_cursor, MERCHANT_ID, order["code"])
    assert verified["success"] is True

    # 3. 结算
    settle_cursor = FakeCursor(rows=[
        {"id": MERCHANT_ID, "name": "社区打印店", "commission_rate": 5},
        None,
        {"c": 1, "p": 50},
    ], rowcount=1)
    settlement = svc.settle_merchant(settle_cursor, MERCHANT_ID, "2026-10")
    assert settlement["redemption_count"] == 1
    assert settlement["points_total"] == 50
    assert settlement["commission_amount"] == pytest.approx(0.03)  # 50×0.01×5% = 0.025 → 0.03


# ============================================================
# 39-44 店铺资料修改（B1：PUT /merchant/info）
# ============================================================
def test_update_info_only_overwrites_provided_fields(monkeypatch):
    """只改联系方式：SET 里绝不能出现没传的字段（否则会被静默清空成 NULL）。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({
        "FROM merchant WHERE user_id=": [_merchant_row(1)],
        "FROM merchant WHERE id=": [_merchant_row(1)],
    }))
    resp = merchant_api.update_merchant_info(
        merchant_api.MerchantInfoUpdate(contact="13900000000"), user_id=USER_ID
    )

    assert resp["code"] == 0
    assert resp["message"] == "店铺资料已保存"
    sql, params = _find(cursor, "UPDATE merchant SET")
    assert sql == "UPDATE merchant SET contact=%s WHERE id=%s"
    assert params == ["13900000000", MERCHANT_ID]
    for key in ("name", "category", "address", "description", "logo_url"):
        assert f"{key}=" not in sql


def test_update_info_can_clear_field_with_empty_string(monkeypatch):
    """显式传空串 → 落库 NULL（需要清空某一项时用）。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({
        "FROM merchant WHERE user_id=": [_merchant_row(1)],
        "FROM merchant WHERE id=": [_merchant_row(1)],
    }))
    merchant_api.update_merchant_info(
        merchant_api.MerchantInfoUpdate(address="", description="  "), user_id=USER_ID
    )

    sql, params = _find(cursor, "UPDATE merchant SET")
    assert sql == "UPDATE merchant SET address=%s, description=%s WHERE id=%s"
    assert params == [None, None, MERCHANT_ID]


def test_update_info_rejects_empty_payload_and_skips_db(monkeypatch):
    """一个字段都没传：400 且完全不连库。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [_merchant_row(1)]}))
    with pytest.raises(HTTPException) as exc:
        merchant_api.update_merchant_info(merchant_api.MerchantInfoUpdate(), user_id=USER_ID)

    assert exc.value.detail == "没有需要修改的内容"
    assert _sqls(cursor) == []


def test_update_info_validates_name_length(monkeypatch):
    """店铺名校验在接口层用中文报错，不触碰数据库。"""
    with pytest.raises(HTTPException) as exc:
        merchant_api.update_merchant_info(
            merchant_api.MerchantInfoUpdate(name="店" * 101), user_id=USER_ID
        )
    assert exc.value.status_code == 400
    assert "店铺名不能超过 100 个字符" in exc.value.detail


def test_update_info_rejected_or_closed_not_editable(monkeypatch):
    """「已拒绝 / 已停业」都不能改资料：要走重新入驻流程，而不是偷偷改字段。"""
    for status, keyword in ((2, "已被拒绝"), (3, "已停业")):
        cursor = _patch_api(monkeypatch, KeyedCursor({
            "FROM merchant WHERE user_id=": [_merchant_row(status)],
        }))
        with pytest.raises(HTTPException) as exc:
            merchant_api.update_merchant_info(
                merchant_api.MerchantInfoUpdate(contact="139"), user_id=USER_ID
            )
        assert exc.value.status_code == 400
        assert keyword in exc.value.detail
        # 状态不允许时不能有任何 UPDATE
        assert not any(sql.startswith("UPDATE merchant SET") for sql in _sqls(cursor))


def test_update_info_when_not_merchant_404(monkeypatch):
    """未入驻账号调资料接口：404（身份来自 merchant.user_id 反查）。"""
    _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [None]}))
    with pytest.raises(svc.MerchantError) as exc:
        merchant_api.update_merchant_info(merchant_api.MerchantInfoUpdate(contact="139"), user_id=USER_ID)
    assert exc.value.status_code == 404


# ============================================================
# 45-47 商品重新上架（B2：PUT /merchant/products/{id}/online）
# ============================================================
def test_online_product_sets_status_one(monkeypatch):
    """重新上架与下架完全对称：置 status=1，归属写进 WHERE。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [_merchant_row(1)]}))
    resp = merchant_api.online_product(PRODUCT_ID, user_id=USER_ID)

    assert resp["data"] == {"product_id": PRODUCT_ID, "status": 1}
    assert resp["message"] == "商品已重新上架"
    sql, params = _find(cursor, "UPDATE merchant_product SET status=")
    assert sql.endswith("WHERE id=%s AND merchant_id=%s")
    assert tuple(params) == (1, PRODUCT_ID, MERCHANT_ID)


def test_online_product_404_when_not_owned(monkeypatch):
    """归属不符 → rowcount=0 → 404（改不到别人的商品）。"""
    _patch_api(monkeypatch, KeyedCursor(
        {"FROM merchant WHERE user_id=": [_merchant_row(1)]}, rowcount=0,
    ))
    with pytest.raises(HTTPException) as exc:
        merchant_api.online_product(PRODUCT_ID, user_id=USER_ID)
    assert exc.value.status_code == 404


def test_online_product_requires_approved_merchant(monkeypatch):
    """待审核店铺不能上架（403），且不产生 UPDATE。"""
    cursor = _patch_api(monkeypatch, KeyedCursor({"FROM merchant WHERE user_id=": [_merchant_row(0)]}))
    with pytest.raises(svc.MerchantError) as exc:
        merchant_api.online_product(PRODUCT_ID, user_id=USER_ID)

    assert exc.value.status_code == 403
    assert not any("UPDATE merchant_product" in sql for sql in _sqls(cursor))


# ============================================================
# 48-51 结算自查（B4：GET /merchant/settlement/summary）
# ============================================================
def _settlement_cursor(monkeypatch, order_row: dict, settle_row: dict):
    return _patch_api(monkeypatch, KeyedCursor({
        "FROM merchant WHERE user_id=": [_merchant_row(1)],
        "FROM redemption_order": [order_row],
        "FROM merchant_settlement": [settle_row],
    }))


def test_settlement_summary_computes_amounts(monkeypatch):
    """应得 / 佣金 / 实得 / 已结算 / 待结算五项一次算清，且都是「应得口径」。"""
    yuan = float(settings.merchant_points_to_yuan)
    cursor = _settlement_cursor(
        monkeypatch,
        order_row={"c": 8, "p": 800},
        settle_row={"c": 1, "p": 300, "m": 0.15, "t": datetime(2026, 10, 1, 9, 0, 0)},
    )
    resp = merchant_api.settlement_summary(user_id=USER_ID)
    data = resp["data"]

    assert data["redemption_count"] == 8
    assert data["points_total"] == 800
    assert data["gross_amount"] == pytest.approx(800 * yuan)
    assert data["commission_amount"] == pytest.approx(float(svc.calculate_commission(800, 5)))
    assert data["net_amount"] == pytest.approx(800 * yuan - float(svc.calculate_commission(800, 5)))
    assert data["settled_points"] == 300
    assert data["settled_amount"] == pytest.approx(300 * yuan)
    assert data["settled_commission"] == pytest.approx(0.15)
    # 待结算 = 应得 − 已结算（同为应得口径，商家可直接相减对账）
    assert data["pending_amount"] == pytest.approx(800 * yuan - 300 * yuan)
    assert data["settled_count"] == 1
    assert data["last_settled_at"] == datetime(2026, 10, 1, 9, 0, 0)
    # merchant_settlement 的查询必须带 status=1，不能把「待结算」批次算进来
    sql, params = _find(cursor, "FROM merchant_settlement")
    assert "status=%s" in sql
    assert params == (MERCHANT_ID, 1)


def test_settlement_summary_zero_when_no_redemptions(monkeypatch):
    """新店没有任何核销：全部为 0，不出现 None / NaN。"""
    _settlement_cursor(monkeypatch, order_row={"c": 0, "p": 0}, settle_row={"c": 0, "p": 0, "m": 0, "t": None})
    data = merchant_api.settlement_summary(user_id=USER_ID)["data"]

    assert data["redemption_count"] == 0
    assert data["points_total"] == 0
    assert data["gross_amount"] == 0.0
    assert data["commission_amount"] == 0.0
    assert data["net_amount"] == 0.0
    assert data["settled_amount"] == 0.0
    assert data["pending_amount"] == 0.0
    assert data["last_settled_at"] is None


def test_settlement_summary_pending_never_negative(monkeypatch):
    """费率/汇率被下调过时，已结算金额可能超过按当前汇率算的应得 → 夹紧到 0，不出现负数。"""
    _settlement_cursor(
        monkeypatch,
        order_row={"c": 1, "p": 300},
        settle_row={"c": 1, "p": 500, "m": 0.25, "t": datetime(2026, 10, 1, 9, 0, 0)},
    )
    data = merchant_api.settlement_summary(user_id=USER_ID)["data"]
    assert data["pending_amount"] == 0.0


def test_to_money_rounds_half_up_and_defaults_zero():
    """金额一律两位小数、四舍五入；非法值归 0（写 DECIMAL(10,2) 前统一口径）。"""
    assert svc.to_money("0.005") == Decimal("0.01")
    assert svc.to_money("1.004") == Decimal("1.00")
    assert svc.to_money(None) == Decimal("0.00")
    assert svc.to_money("abc") == Decimal("0.00")
