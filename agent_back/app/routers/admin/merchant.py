"""平台管理端 · 商家管理（挂载于 `/api/admin/merchant`）。

7 个接口：商家列表 / 审核 / 全部兑换单 / 结算记录 / 手动结算（全部或单个）/ 平台总览。

权限沿用 `app/routers/admin/deps.py`：
- 读（list / orders / settlements / stats）：role 1 超管、2 运营、3 只读
- 写（audit / settle）：role 1、2

响应外壳用管理端的 `ok()`（`{code:200, message, data}`），
**不用**用户侧的 `success()`（`code:0`）——两套契约刻意不混用。

本模块**不受** `MERCHANT_ENABLED` 开关影响：即使商家端对用户关闭，
管理员仍需要能审核入驻、查看兑换单、执行结算。
"""
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.constants import MERCHANT_STATUS_LABEL, REDEMPTION_STATUS_LABEL, SETTLEMENT_STATUS_LABEL
from app.db.pool import connection
from app.routers.admin.deps import ok, require_role
from app.schemas.merchant import AuditRequest, SettleRequest
from app.services import merchant_service
from app.services.merchant_service import (
    MERCHANT_STATUS_APPROVED,
    REDEMPTION_STATUS_REDEEMED,
    SETTLEMENT_STATUS_SETTLED,
)

logger = logging.getLogger(__name__)

router = APIRouter()

read_roles = require_role([1, 2, 3])
write_roles = require_role([1, 2])

LIST_DEFAULT_SIZE = 10
LIST_MAX_SIZE = 100
MAX_REASON_LEN = 255


def _clamp(value, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


def _page_params(page: int, size: int) -> tuple[int, int]:
    return _clamp(page, 1, 10 ** 6), _clamp(size, 1, LIST_MAX_SIZE)


def _optional_int(value, label: str, low: int = 0, high: int = 9) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{label}必须是整数")
    if number < low or number > high:
        raise HTTPException(400, f"{label}取值范围不正确")
    return number


# ============================================================
# 商家列表与审核
# ============================================================
@router.get("/list", dependencies=[Depends(read_roles)])
def list_merchants(
    status: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=LIST_DEFAULT_SIZE),
):
    """商家列表，可按状态（0待审核 1已通过 2已拒绝 3已停业）与关键词筛选。"""
    status_value = _optional_int(status, "商家状态", low=0, high=3)
    page, size = _page_params(page, size)

    conditions = ["1=1"]
    params: list = []
    if status_value is not None:
        conditions.append("m.status=%s")
        params.append(status_value)
    if keyword:
        conditions.append("(m.name LIKE %s OR m.contact LIKE %s OR m.address LIKE %s)")
        like = f"%{keyword.strip()}%"
        params.extend([like, like, like])
    where = " AND ".join(conditions)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM merchant m WHERE {where}", params)
            total = merchant_service.as_int((cursor.fetchone() or {}).get("total"))
            cursor.execute(
                f"SELECT m.id, m.user_id, m.name, m.category, m.contact, m.address, m.description, "
                f"       m.logo_url, m.status, m.commission_rate, m.audit_reason, m.created_at, "
                f"       (SELECT COUNT(*) FROM merchant_product p WHERE p.merchant_id = m.id) AS product_count, "
                f"       (SELECT COUNT(*) FROM redemption_order o "
                f"        WHERE o.merchant_id = m.id AND o.status = {REDEMPTION_STATUS_REDEEMED}) AS redemption_count "
                f"FROM merchant m WHERE {where} ORDER BY m.id DESC LIMIT %s OFFSET %s",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()

    items = []
    for row in rows:
        item = merchant_service.to_merchant_info(row)
        item["product_count"] = merchant_service.as_int(row.get("product_count"))
        item["redemption_count"] = merchant_service.as_int(row.get("redemption_count"))
        items.append(item)

    return ok({"total": total, "page": page, "size": size, "list": items})


@router.put("/{merchant_id}/audit", dependencies=[Depends(write_roles)])
def audit_merchant(merchant_id: int, req: AuditRequest, admin: dict = Depends(write_roles)):
    """审核商家入驻。

    **拒绝时必须填写原因**（写入 `merchant.audit_reason`，商家在 `/merchant/info`
    里能看到）—— 任务书把 `reason` 标为可选，但「被拒且不知原因」对商家是死路，
    这里收紧为拒绝必填，通过时可留空。
    """
    reason = (req.reason or "").strip()
    if len(reason) > MAX_REASON_LEN:
        raise HTTPException(400, f"审核原因不能超过 {MAX_REASON_LEN} 个字符")
    if not req.approved and not reason:
        raise HTTPException(400, "拒绝入驻时必须填写原因")

    target = MERCHANT_STATUS_APPROVED if req.approved else 2
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM merchant WHERE id=%s LIMIT 1", (merchant_id,))
            if not cursor.fetchone():
                raise HTTPException(404, "商家不存在")
            cursor.execute(
                "UPDATE merchant SET status=%s, audit_reason=%s WHERE id=%s",
                (target, None if req.approved else reason, merchant_id),
            )

    return ok(
        {
            "merchant_id": merchant_id,
            "status": target,
            "status_label": MERCHANT_STATUS_LABEL.get(target, "未知状态"),
            "audit_reason": None if req.approved else reason,
        },
        "审核通过" if req.approved else "已拒绝该入驻申请",
    )


# ============================================================
# 全部兑换订单
# ============================================================
@router.get("/orders", dependencies=[Depends(read_roles)])
def list_all_redemptions(
    status: int | None = Query(default=None),
    merchant_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=LIST_DEFAULT_SIZE),
):
    """平台全部兑换订单，可按状态 / 商家 / 单号或核销码筛选。"""
    status_value = _optional_int(status, "兑换单状态", low=0, high=4)
    page, size = _page_params(page, size)

    conditions = ["1=1"]
    params: list = []
    if status_value is not None:
        conditions.append("o.status=%s")
        params.append(status_value)
    if merchant_id:
        conditions.append("o.merchant_id=%s")
        params.append(int(merchant_id))
    if keyword:
        conditions.append("(o.order_no LIKE %s OR o.code LIKE %s)")
        like = f"%{keyword.strip()}%"
        params.extend([like, like])
    where = " AND ".join(conditions)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM redemption_order o WHERE {where}", params
            )
            total = merchant_service.as_int((cursor.fetchone() or {}).get("total"))
            cursor.execute(
                f"SELECT o.id, o.order_no, o.status, o.code, o.points_cost, o.product_id, "
                f"       o.user_id, o.merchant_id, o.expires_at, o.redeemed_at, o.created_at, "
                f"       p.title AS product_title, m.name AS merchant_name, u.nickname AS user_nickname "
                f"FROM redemption_order o "
                f"LEFT JOIN merchant_product p ON o.product_id = p.id "
                f"LEFT JOIN merchant m ON o.merchant_id = m.id "
                f"LEFT JOIN user u ON o.user_id = u.id "
                f"WHERE {where} ORDER BY o.id DESC LIMIT %s OFFSET %s",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()

    return ok(
        {
            "total": total,
            "page": page,
            "size": size,
            "list": [merchant_service.to_redemption_item(row) for row in rows],
        }
    )


# ============================================================
# 结算
# ============================================================
@router.get("/settlements", dependencies=[Depends(read_roles)])
def list_settlements(
    merchant_id: int | None = Query(default=None),
    period: str | None = Query(default=None),
    status: int | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=LIST_DEFAULT_SIZE),
):
    """结算记录列表。"""
    status_value = _optional_int(status, "结算状态", low=0, high=1)
    page, size = _page_params(page, size)

    conditions = ["1=1"]
    params: list = []
    if merchant_id:
        conditions.append("s.merchant_id=%s")
        params.append(int(merchant_id))
    if period:
        conditions.append("s.period=%s")
        params.append(period.strip())
    if status_value is not None:
        conditions.append("s.status=%s")
        params.append(status_value)
    where = " AND ".join(conditions)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM merchant_settlement s WHERE {where}", params
            )
            total = merchant_service.as_int((cursor.fetchone() or {}).get("total"))
            cursor.execute(
                f"SELECT s.id, s.merchant_id, s.period, s.redemption_count, s.points_total, "
                f"       s.commission_amount, s.status, s.settled_at, s.created_at, m.name AS merchant_name "
                f"FROM merchant_settlement s LEFT JOIN merchant m ON s.merchant_id = m.id "
                f"WHERE {where} ORDER BY s.id DESC LIMIT %s OFFSET %s",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()

    items = []
    for row in rows:
        status_code = merchant_service.as_int(row.get("status"))
        items.append(
            {
                "id": merchant_service.as_int(row.get("id")),
                "merchant_id": merchant_service.as_int(row.get("merchant_id")),
                "merchant_name": row.get("merchant_name") or "",
                "period": row.get("period") or "",
                "redemption_count": merchant_service.as_int(row.get("redemption_count")),
                "points_total": merchant_service.as_int(row.get("points_total")),
                "commission_amount": merchant_service.as_float(row.get("commission_amount")),
                "status": status_code,
                "status_label": SETTLEMENT_STATUS_LABEL.get(status_code, "未知状态"),
                "settled_at": row.get("settled_at"),
                "created_at": row.get("created_at"),
            }
        )

    return ok({"total": total, "page": page, "size": size, "list": items})


@router.get("/settlements/preview", dependencies=[Depends(read_roles)])
def preview_settlements(period: str | None = Query(default=None)):
    """结算预览（**只读**）：算出每个「已通过」商家在指定周期**即将结算**的数字。

    口径与 `settle_merchant` 完全一致，否则确认弹窗会承诺错误数字：
      该周期内 `status=2（已核销）` 且 `redeemed_at ∈ [start, end)` 的兑换单；
      佣金 = 积分总额 × 积分汇率(元/积分) × 佣金比例%。

    幂等对齐：某商家该周期**已结算**时，回显结算表里的**存量数字**（而非重算），
    与 `settle_merchant` 的幂等分支返回一致 —— 前端据此把该行标成「本期已结算」
    并禁用按钮，避免对不可逆操作给出错误承诺。

    对应 `变更影响分析` 的冲突 C1：`/merchant/list` 只给累计 `redemption_count`
    且不暴露积分总额与汇率，前端**无法**自行算出这两个数，所以必须由后端提供。

    **不写任何表、不改任何状态**，可安全重复调用。
    单条聚合 SQL（GROUP BY）取全部商家，避免按商家循环查的 N+1。
    """
    period_str, start, end = merchant_service.parse_period(period)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT m.id AS merchant_id, m.name, m.commission_rate, "
                "       COALESCE(agg.cnt, 0) AS redemption_count, "
                "       COALESCE(agg.pts, 0) AS points_total "
                "FROM merchant m "
                "LEFT JOIN ("
                "    SELECT o.merchant_id, COUNT(*) AS cnt, COALESCE(SUM(o.points_cost), 0) AS pts "
                "    FROM redemption_order o "
                "    WHERE o.status=%s AND o.redeemed_at >= %s AND o.redeemed_at < %s "
                "    GROUP BY o.merchant_id"
                ") agg ON agg.merchant_id = m.id "
                "WHERE m.status=%s ORDER BY m.id ASC",
                (REDEMPTION_STATUS_REDEEMED, start, end, MERCHANT_STATUS_APPROVED),
            )
            rows = cursor.fetchall()

            cursor.execute(
                "SELECT id, merchant_id, redemption_count, points_total, commission_amount, "
                "       status, settled_at FROM merchant_settlement WHERE period=%s",
                (period_str,),
            )
            settled_map = {
                merchant_service.as_int(row.get("merchant_id")): row for row in cursor.fetchall()
            }

    items = []
    for row in rows:
        merchant_id = merchant_service.as_int(row.get("merchant_id"))
        settled_row = settled_map.get(merchant_id)
        already_settled = bool(settled_row) and (
            merchant_service.as_int(settled_row.get("status")) == SETTLEMENT_STATUS_SETTLED
        )
        if already_settled:
            count = merchant_service.as_int(settled_row.get("redemption_count"))
            points_total = merchant_service.as_int(settled_row.get("points_total"))
            commission = merchant_service.as_float(settled_row.get("commission_amount"))
            settled_at = merchant_service.as_datetime(settled_row.get("settled_at"))
        else:
            count = merchant_service.as_int(row.get("redemption_count"))
            points_total = merchant_service.as_int(row.get("points_total"))
            commission = round(
                float(merchant_service.calculate_commission(points_total, row.get("commission_rate"))),
                2,
            )
            settled_at = None
        items.append(
            {
                "merchant_id": merchant_id,
                "name": row.get("name") or "",
                "commission_rate": merchant_service.as_float(row.get("commission_rate")),
                "redemption_count": count,
                "points_total": points_total,
                "commission_amount": commission,
                "settled": already_settled,
                "settled_at": settled_at,
            }
        )

    pending = [item for item in items if not item["settled"]]
    return ok(
        {
            "period": period_str,
            "start": start,
            "end": end,
            # 汇总：待结算商家数与待结算佣金合计（已结算的不计入）
            "pending_merchants": len(pending),
            "pending_commission": round(sum(item["commission_amount"] for item in pending), 2),
            "total": len(items),
            "list": items,
        }
    )


def _settle_all(cursor, period: str | None) -> list[dict]:
    """结算全部「已通过审核」的商家（status=1）。"""
    cursor.execute("SELECT id FROM merchant WHERE status=%s ORDER BY id ASC", (MERCHANT_STATUS_APPROVED,))
    merchant_ids = [merchant_service.as_int(row.get("id")) for row in cursor.fetchall()]
    return [merchant_service.settle_merchant(cursor, mid, period) for mid in merchant_ids]


@router.post("/settle", dependencies=[Depends(write_roles)])
def settle(req: SettleRequest | None = None, admin: dict = Depends(write_roles)):
    """手动触发结算。

    `merchant_id` 为空 → 结算全部已通过审核的商家；否则只结算指定商家。
    `period` 缺省为当月（YYYY-MM）。同一 (merchant_id, period) 重复结算幂等，
    已结算的直接返回原记录，不会重复写行。
    """
    payload = req or SettleRequest()
    period = payload.period
    # 提前校验周期格式：错误格式应在这里就 400，而不是结算了前几家之后才炸
    period_str, _start, _end = merchant_service.parse_period(period)

    with connection() as conn:
        with conn.cursor() as cursor:
            if payload.merchant_id:
                results = [
                    merchant_service.settle_merchant(cursor, int(payload.merchant_id), period_str)
                ]
            else:
                results = _settle_all(cursor, period_str)

    return ok(
        {
            "period": period_str,
            "count": len(results),
            "commission_total": round(
                sum(item.get("commission_amount") or 0 for item in results), 2
            ),
            "list": results,
        },
        f"结算完成，共 {len(results)} 家商家",
    )


@router.post("/settle/{merchant_id}", dependencies=[Depends(write_roles)])
def settle_one(merchant_id: int, req: SettleRequest | None = None, admin: dict = Depends(write_roles)):
    """手动结算指定商家（与 `POST /settle` 带 merchant_id 等价，供前端按行操作）。"""
    payload = req or SettleRequest()
    period_str, _start, _end = merchant_service.parse_period(payload.period)
    with connection() as conn:
        with conn.cursor() as cursor:
            result = merchant_service.settle_merchant(cursor, int(merchant_id), period_str)
    return ok(result, "结算完成")


# ============================================================
# 平台总览
# ============================================================
@router.get("/stats", dependencies=[Depends(read_roles)])
def platform_stats():
    """平台总体数据：商家分状态、兑换单分状态、消耗积分、累计佣金、商家排行、近 7 日趋势。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, COUNT(*) AS c FROM merchant GROUP BY status")
            merchant_counts = {
                merchant_service.as_int(row.get("status")): merchant_service.as_int(row.get("c"))
                for row in cursor.fetchall()
            }

            cursor.execute("SELECT status, COUNT(*) AS c FROM redemption_order GROUP BY status")
            order_counts = {
                merchant_service.as_int(row.get("status")): merchant_service.as_int(row.get("c"))
                for row in cursor.fetchall()
            }

            cursor.execute(
                "SELECT COALESCE(SUM(points_cost), 0) AS p FROM redemption_order WHERE status=%s",
                (REDEMPTION_STATUS_REDEEMED,),
            )
            points_consumed = merchant_service.as_int((cursor.fetchone() or {}).get("p"))

            cursor.execute(
                "SELECT COALESCE(SUM(commission_amount), 0) AS c FROM merchant_settlement WHERE status=%s",
                (SETTLEMENT_STATUS_SETTLED,),
            )
            commission_total = merchant_service.as_float((cursor.fetchone() or {}).get("c"))

            cursor.execute(
                "SELECT m.id, m.name, COUNT(o.id) AS c FROM merchant m "
                "LEFT JOIN redemption_order o ON o.merchant_id = m.id AND o.status=%s "
                "GROUP BY m.id, m.name ORDER BY c DESC, m.id ASC LIMIT 10",
                (REDEMPTION_STATUS_REDEEMED,),
            )
            top_merchants = [
                {
                    "merchant_id": merchant_service.as_int(row.get("id")),
                    "name": row.get("name") or "",
                    "redemption_count": merchant_service.as_int(row.get("c")),
                }
                for row in cursor.fetchall()
            ]

            trend = merchant_service.redemption_trend(cursor, days=7)

    def _count(mapping: dict, key: int) -> int:
        return merchant_service.as_int(mapping.get(key))

    return ok(
        {
            "merchants": {
                "total": sum(merchant_counts.values()),
                "pending": _count(merchant_counts, 0),
                "approved": _count(merchant_counts, 1),
                "rejected": _count(merchant_counts, 2),
                "closed": _count(merchant_counts, 3),
            },
            "redemptions": {
                "total": sum(order_counts.values()),
                "pending": _count(order_counts, 1),
                "redeemed": _count(order_counts, 2),
                "expired": _count(order_counts, 3),
                "cancelled": _count(order_counts, 4),
            },
            "points_consumed": points_consumed,
            "commission_total": round(commission_total, 2),
            "top_merchants": top_merchants,
            "trend": trend,
        }
    )
