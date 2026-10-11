from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.pool import connection
from app.routers.admin.deps import create_admin_token, hash_admin_password, ok

router = APIRouter()


class AdminLogin(BaseModel):
    username: str
    password: str


@router.post("/login")
def admin_login(req: AdminLogin):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM admin WHERE username=%s LIMIT 1", (req.username,))
            row = cursor.fetchone()
    if not row or row["password_hash"] != hash_admin_password(req.password):
        raise HTTPException(400, "账号或密码错误")
    if row["status"] != 1:
        raise HTTPException(403, "账号已被禁用")
    token = create_admin_token(row["id"], row["username"], row["role"])
    return ok(
        {
            "token": token,
            "admin_id": row["id"],
            "username": row["username"],
            "real_name": row["real_name"],
            "role": row["role"],
        },
        "登录成功",
    )
