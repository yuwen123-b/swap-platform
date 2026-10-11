from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.pool import connection
from app.routers.admin.deps import hash_admin_password, ok, require_role

router = APIRouter()

# 仅超级管理员可访问
super_admin = require_role([1])


class AccountCreate(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    real_name: str | None = Field(default=None, max_length=20)
    role: int = Field(default=3, ge=1, le=3)


class AccountUpdate(BaseModel):
    real_name: str | None = Field(default=None, max_length=20)
    role: int | None = Field(default=None, ge=1, le=3)
    status: int | None = Field(default=None, ge=0, le=1)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=6, max_length=64)


@router.get("/accounts", dependencies=[Depends(super_admin)])
def list_accounts(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), keyword: str | None = None):
    conditions = ["1=1"]
    params: list = []
    if keyword:
        conditions.append("(username LIKE %s OR real_name LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM admin WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"SELECT id, username, real_name, role, status, created_at FROM admin WHERE {where} ORDER BY id ASC LIMIT %s OFFSET %s",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.post("/accounts", dependencies=[Depends(super_admin)])
def create_account(req: AccountCreate):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM admin WHERE username=%s LIMIT 1", (req.username,))
            if cursor.fetchone():
                raise HTTPException(400, "用户名已存在")
            cursor.execute(
                "INSERT INTO admin (username, password_hash, real_name, role, status) VALUES (%s,%s,%s,%s,1)",
                (req.username, hash_admin_password(req.password), req.real_name, req.role),
            )
            new_id = cursor.lastrowid
    return ok({"id": new_id}, "创建成功")


@router.put("/accounts/{account_id}", dependencies=[Depends(super_admin)])
def update_account(account_id: int, req: AccountUpdate):
    fields: list[str] = []
    params: list = []
    if req.real_name is not None:
        fields.append("real_name=%s")
        params.append(req.real_name)
    if req.role is not None:
        fields.append("role=%s")
        params.append(req.role)
    if req.status is not None:
        fields.append("status=%s")
        params.append(req.status)
    if not fields:
        raise HTTPException(400, "没有需要修改的字段")
    params.append(account_id)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE admin SET {', '.join(fields)} WHERE id=%s", params)
            if cursor.rowcount == 0:
                raise HTTPException(404, "管理员不存在")
    return ok(message="修改成功")


@router.delete("/accounts/{account_id}", dependencies=[Depends(super_admin)])
def delete_account(account_id: int, admin: dict = Depends(super_admin)):
    if account_id == admin["admin_id"]:
        raise HTTPException(400, "不能删除自己")
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM admin WHERE id=%s", (account_id,))
            if cursor.rowcount == 0:
                raise HTTPException(404, "管理员不存在")
    return ok(message="删除成功")


@router.post("/accounts/{account_id}/reset-password", dependencies=[Depends(super_admin)])
def reset_password(account_id: int, req: PasswordReset):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM admin WHERE id=%s", (account_id,))
            if cursor.fetchone() is None:
                raise HTTPException(404, "管理员不存在")
            cursor.execute("UPDATE admin SET password_hash=%s WHERE id=%s", (hash_admin_password(req.new_password), account_id))
    return ok(message="密码重置成功")
