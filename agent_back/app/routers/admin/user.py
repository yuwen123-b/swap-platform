from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role

router = APIRouter()

read_roles = require_role([1, 2, 3])
write_roles = require_role([1, 2])


class StatusUpdate(BaseModel):
    status: int = Field(ge=0, le=1)


@router.get("/users", dependencies=[Depends(read_roles)])
def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
    status: int | None = None,
):
    conditions = ["1=1"]
    params: list = []
    if keyword:
        conditions.append("(nickname LIKE %s OR phone LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if status is not None:
        conditions.append("status=%s")
        params.append(status)
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM user WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT id, phone, nickname, avatar, email, gender, credit_score, points,
                           exchange_count, donate_count, status, is_verified, last_login_time, created_at
                    FROM user WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s""",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.get("/users/{user_id}", dependencies=[Depends(read_roles)])
def get_user(user_id: int):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, phone, nickname, avatar, real_name, email, gender, birthday, community_id,
                          credit_score, points, carbon_total, exchange_count, donate_count,
                          status, is_verified, last_login_time, created_at
                   FROM user WHERE id=%s LIMIT 1""",
                (user_id,),
            )
            user = cursor.fetchone()
            if not user:
                raise HTTPException(404, "用户不存在")
            cursor.execute("SELECT COUNT(*) AS c FROM item WHERE user_id=%s", (user_id,))
            user["item_count"] = cursor.fetchone()["c"]
            cursor.execute("SELECT COUNT(*) AS c FROM `order` WHERE buyer_id=%s OR seller_id=%s", (user_id, user_id))
            user["order_count"] = cursor.fetchone()["c"]
    return ok(user)


@router.put("/users/{user_id}/status", dependencies=[Depends(write_roles)])
def update_user_status(user_id: int, req: StatusUpdate):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE user SET status=%s WHERE id=%s", (req.status, user_id))
            if cursor.rowcount == 0:
                raise HTTPException(404, "用户不存在")
    return ok(message="状态已更新")


@router.delete("/users/{user_id}", dependencies=[Depends(write_roles)])
def delete_user(user_id: int):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM user WHERE id=%s", (user_id,))
            if cursor.rowcount == 0:
                raise HTTPException(404, "用户不存在")
    return ok(message="用户已删除")
