import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role
# 交换完成奖励（发分 + 累加交换次数/碳减排量）已上移到 services 层，
# 与用户侧 `PUT /api/orders/{id}/complete` 共用同一份实现，避免两套规则漂移。
# 本文件原有的 `_reward_exchange_completion` 已删除，行为保持不变。
from app.services.order_service import reward_exchange_completion

logger = logging.getLogger(__name__)

router = APIRouter()

read_roles = require_role([1, 2, 3])
write_roles = require_role([1, 2])


class OrderStatusUpdate(BaseModel):
    # 1=待确认 2=交换中 3=已完成 4=已取消 5=争议中
    status: int = Field(ge=1, le=5)


@router.get("/orders", dependencies=[Depends(read_roles)])
def list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: int | None = None,
    keyword: str | None = None,
):
    conditions = ["1=1"]
    params: list = []
    if status is not None:
        conditions.append("o.status=%s")
        params.append(status)
    if keyword:
        conditions.append("(o.order_no LIKE %s OR b.nickname LIKE %s OR s.nickname LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""SELECT COUNT(*) AS total FROM `order` o
                    LEFT JOIN user b ON o.buyer_id=b.id LEFT JOIN user s ON o.seller_id=s.id
                    WHERE {where}""",
                params,
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT o.*, b.nickname AS buyer_name, s.nickname AS seller_name, i.title AS item_title
                    FROM `order` o
                    LEFT JOIN user b ON o.buyer_id=b.id
                    LEFT JOIN user s ON o.seller_id=s.id
                    LEFT JOIN item i ON o.item_id=i.id
                    WHERE {where} ORDER BY o.id DESC LIMIT %s OFFSET %s""",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.get("/orders/{order_id}", dependencies=[Depends(read_roles)])
def get_order(order_id: int):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT o.*, b.nickname AS buyer_name, s.nickname AS seller_name, i.title AS item_title
                   FROM `order` o
                   LEFT JOIN user b ON o.buyer_id=b.id
                   LEFT JOIN user s ON o.seller_id=s.id
                   LEFT JOIN item i ON o.item_id=i.id
                   WHERE o.id=%s LIMIT 1""",
                (order_id,),
            )
            order = cursor.fetchone()
    if not order:
        raise HTTPException(404, "订单不存在")
    return ok(order)


@router.put("/orders/{order_id}/status", dependencies=[Depends(write_roles)])
def update_order_status(order_id: int, req: OrderStatusUpdate):
    with connection() as conn:
        with conn.cursor() as cursor:
            # 先取旧状态与双方用户：既用于幂等判断，也用于组装奖励对象。
            # 不判断旧值的话，反复 PUT status=3 就能反复拿奖励（刷分漏洞）。
            cursor.execute(
                "SELECT status, buyer_id, seller_id FROM `order` WHERE id=%s LIMIT 1",
                (order_id,),
            )
            order = cursor.fetchone()
            if not order:
                raise HTTPException(404, "订单不存在")
            previous_status = int(order.get("status") or 0)

            if req.status == 3:
                cursor.execute("UPDATE `order` SET status=%s, completed_at=NOW() WHERE id=%s", (req.status, order_id))
            else:
                cursor.execute("UPDATE `order` SET status=%s WHERE id=%s", (req.status, order_id))
            if cursor.rowcount == 0:
                raise HTTPException(404, "订单不存在")

            # 仅在「本次置为已完成」且「此前不是已完成」时发放，保证只发一次
            if req.status == 3 and previous_status != 3:
                reward_exchange_completion(cursor, order_id, order)
    return ok(message="订单状态已更新")


@router.delete("/orders/{order_id}", dependencies=[Depends(write_roles)])
def delete_order(order_id: int):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM `order` WHERE id=%s", (order_id,))
            if cursor.rowcount == 0:
                raise HTTPException(404, "订单不存在")
    return ok(message="订单已删除")
