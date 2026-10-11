from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role

router = APIRouter()

read_roles = require_role([1, 2, 3])
write_roles = require_role([1, 2])
audit_roles = require_role([1, 2, 3])


class ItemUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=64)
    description: str | None = None
    category_id: int | None = None
    condition_level: int | None = Field(default=None, ge=1, le=5)
    exchange_mode: int | None = Field(default=None, ge=1, le=3)
    price: float | None = Field(default=None, ge=0)
    expected_item: str | None = Field(default=None, max_length=100)
    status: int | None = Field(default=None, ge=1, le=4)


class AuditRequest(BaseModel):
    approved: bool
    reason: str = ""


# 注意：/audit/list 必须先于 /{item_id} 声明，避免被路径参数捕获
@router.get("/items/audit/list", dependencies=[Depends(audit_roles)])
def audit_list(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100)):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM item WHERE status=4")
            total = cursor.fetchone()["total"]
            cursor.execute(
                """SELECT i.*, c.name AS category_name, u.nickname AS publisher
                   FROM item i
                   LEFT JOIN category c ON i.category_id = c.id
                   LEFT JOIN user u ON i.user_id = u.id
                   WHERE i.status=4 ORDER BY i.id ASC LIMIT %s OFFSET %s""",
                (size, (page - 1) * size),
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.post("/items/{item_id}/audit", dependencies=[Depends(audit_roles)])
def audit_item(item_id: int, req: AuditRequest):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, status FROM item WHERE id=%s LIMIT 1", (item_id,))
            item = cursor.fetchone()
            if not item:
                raise HTTPException(404, "物品不存在")
            if item["status"] != 4:
                raise HTTPException(400, "该物品不在待审核状态")
            if req.approved:
                cursor.execute("UPDATE item SET status=1, reject_reason=NULL WHERE id=%s", (item_id,))
                return ok(message="审核通过，物品已上架")
            cursor.execute("UPDATE item SET status=3, reject_reason=%s WHERE id=%s", (req.reason, item_id))
            return ok(message="已拒绝该物品上架")


@router.get("/items", dependencies=[Depends(read_roles)])
def list_items(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
    category_id: int | None = None,
    status: int | None = None,
    publisher: str | None = None,
):
    conditions = ["1=1"]
    params: list = []
    if keyword:
        conditions.append("(i.title LIKE %s OR i.description LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if category_id:
        conditions.append("i.category_id=%s")
        params.append(category_id)
    if status is not None:
        conditions.append("i.status=%s")
        params.append(status)
    if publisher:
        conditions.append("u.nickname LIKE %s")
        params.append(f"%{publisher}%")
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM item i LEFT JOIN user u ON i.user_id=u.id WHERE {where}", params
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT i.*, c.name AS category_name, u.nickname AS publisher
                    FROM item i
                    LEFT JOIN category c ON i.category_id = c.id
                    LEFT JOIN user u ON i.user_id = u.id
                    WHERE {where} ORDER BY i.id DESC LIMIT %s OFFSET %s""",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.get("/items/{item_id}", dependencies=[Depends(read_roles)])
def get_item(item_id: int):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT i.*, c.name AS category_name, u.nickname AS publisher
                   FROM item i
                   LEFT JOIN category c ON i.category_id = c.id
                   LEFT JOIN user u ON i.user_id = u.id
                   WHERE i.id=%s LIMIT 1""",
                (item_id,),
            )
            item = cursor.fetchone()
    if not item:
        raise HTTPException(404, "物品不存在")
    return ok(item)


@router.put("/items/{item_id}", dependencies=[Depends(write_roles)])
def update_item(item_id: int, req: ItemUpdate):
    fields: list[str] = []
    params: list = []
    for name in ("title", "description", "category_id", "condition_level", "exchange_mode", "price", "expected_item", "status"):
        value = getattr(req, name)
        if value is not None:
            fields.append(f"{name}=%s")
            params.append(value)
    if not fields:
        raise HTTPException(400, "没有需要修改的字段")
    params.append(item_id)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE item SET {', '.join(fields)} WHERE id=%s", params)
            if cursor.rowcount == 0:
                raise HTTPException(404, "物品不存在")
    return ok(message="物品已更新")


@router.delete("/items/{item_id}", dependencies=[Depends(write_roles)])
def delete_item(item_id: int):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM item WHERE id=%s", (item_id,))
            if cursor.rowcount == 0:
                raise HTTPException(404, "物品不存在")
    return ok(message="物品已删除")
