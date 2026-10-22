"""平台管理端 · 平台回收（挂载于 `/api/admin/recycle`）。

6 个接口：回收单列表 / 标记入库 / 批量销售 / 销售记录 / 运营数据 / 回收商下拉。

权限沿用 `app/routers/admin/deps.py`（与 admin/merchant.py 完全同口径）：
- 读（list / sales / stats / recyclers）：role 1 超管、2 运营、3 审核员
- 写（receive / sell）：role 1、2

响应外壳用管理端的 `ok()`（`{code:200, message, data}`），
**不用**用户侧的 `success()`（`code:0`）——两套契约刻意不混用。

「平台库存」页不新增接口：= `GET /list?status=2`。
本模块**不受** `MERCHANT_ENABLED` 开关影响（与 admin/merchant.py 的既定立场一致）；
`merchant` 表全程只读（回收商 = category='回收' 且 status=1 的商家）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role
from app.schemas.recycle import RecycleSellRequest
from app.services import recycle_service

logger = logging.getLogger(__name__)

router = APIRouter()

read_roles = require_role([1, 2, 3])
write_roles = require_role([1, 2])

LIST_DEFAULT_SIZE = 10
LIST_MAX_SIZE = 100


def _clamp(value: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


def _page_params(page: int, size: int) -> tuple[int, int]:
    return _clamp(page, 1, 10 ** 6), _clamp(size, 1, LIST_MAX_SIZE)


def _optional_status(status: int | None) -> int | None:
    if status is None or status == "":
        return None
    if status not in (1, 2, 3, 4):
        raise HTTPException(400, "回收单状态只能是 1=待取件 / 2=已入库 / 3=已售出 / 4=已取消")
    return int(status)


@router.get("/list", dependencies=[Depends(read_roles)])
def list_recycles(
    status: int | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=LIST_DEFAULT_SIZE),
):
    """回收单列表（含「平台库存」= status=2 的过滤口径），JOIN 物品与用户。"""
    status_value = _optional_status(status)
    page_v, size_v = _page_params(page, size)

    conditions = ["1=1"]
    params: list = []
    if status_value is not None:
        conditions.append("r.status=%s")
        params.append(status_value)
    where = " AND ".join(conditions)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM platform_recycle r WHERE {where}", params
            )
            total = recycle_service.as_int((cursor.fetchone() or {}).get("total"))
            cursor.execute(
                f"""SELECT r.*, i.title AS item_title, i.images AS item_images,
                           u.nickname AS user_nickname
                    FROM platform_recycle r
                    LEFT JOIN item i ON r.item_id = i.id
                    LEFT JOIN user u ON r.user_id = u.id
                    WHERE {where}
                    ORDER BY r.id DESC LIMIT %s OFFSET %s""",
                params + [size_v, (page_v - 1) * size_v],
            )
            rows = cursor.fetchall()

    items = []
    for row in rows:
        data = recycle_service.to_recycle_item(row)
        data["item_image"] = recycle_service.parse_first_image(row.get("item_images"))
        items.append(data)

    return ok({"total": total, "page": page_v, "size": size_v, "list": items})


@router.put("/{recycle_id}/receive", dependencies=[Depends(write_roles)])
def receive_recycle(recycle_id: int):
    """标记已入库：仅待取件（1→2），写 received_at，同步 item.recycle_status=2。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            result = recycle_service.receive_recycle(cursor, recycle_id)
    return ok(result, "已标记入库")


@router.post("/sell", dependencies=[Depends(write_roles)])
def sell_to_recycler(req: RecycleSellRequest):
    """批量把已入库物品卖给回收商（单事务，见 recycle_service 并发铁律）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            result = recycle_service.sell_to_recycler(
                cursor, req.recycler_id, req.recycle_ids, req.total_amount
            )
    return ok(result, "出售成功")


@router.get("/sales", dependencies=[Depends(read_roles)])
def list_sales(
    recycler_id: int | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=LIST_DEFAULT_SIZE),
):
    """销售记录列表（运营端「销售记录」菜单的数据源）。"""
    page_v, size_v = _page_params(page, size)
    with connection() as conn:
        with conn.cursor() as cursor:
            data = recycle_service.list_sales(cursor, recycler_id, page_v, size_v)
    return ok(data)


@router.get("/stats", dependencies=[Depends(read_roles)])
def recycle_stats():
    """平台回收运营数据：任务书 6 字段 + 看板扩展（状态分布 / 回收商排行 / 待取件量）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            data = recycle_service.recycle_stats(cursor)
    return ok(data)


@router.get("/recyclers", dependencies=[Depends(read_roles)])
def list_recyclers():
    """回收商下拉数据源：merchant.category='回收' 且 status=1（merchant 只读）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, contact, address FROM merchant "
                "WHERE category=%s AND status=1 ORDER BY id ASC",
                ("回收",),
            )
            rows = cursor.fetchall()
    return ok([
        {
            "id": recycle_service.as_int(r.get("id")),
            "name": r.get("name") or "",
            "contact": r.get("contact"),
            "address": r.get("address"),
        }
        for r in rows
    ])
