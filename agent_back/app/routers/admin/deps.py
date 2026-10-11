from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException

from app.core.config import settings
from app.db.pool import connection


def hash_admin_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_admin_token(admin_id: int, username: str, role: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.admin_token_expire_minutes)
    payload = {"admin_id": admin_id, "username": username, "role": role, "type": "admin", "exp": expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_admin(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(authorization[7:], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "admin":
            raise ValueError("非管理员令牌")
        admin_id = int(payload["admin_id"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Token 无效或已过期") from exc
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username, real_name, role, status FROM admin WHERE id=%s LIMIT 1", (admin_id,))
            row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="管理员不存在")
    if row["status"] != 1:
        raise HTTPException(status_code=401, detail="账号已被禁用")
    return {"admin_id": row["id"], "username": row["username"], "real_name": row["real_name"], "role": row["role"]}


def require_role(allowed_roles: list[int]):
    def checker(admin: dict = Depends(get_current_admin)) -> dict:
        if admin["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="无权限访问")
        return admin

    return checker


def ok(data: Any = None, message: str = "success") -> dict:
    return {"code": 200, "message": message, "data": data}
