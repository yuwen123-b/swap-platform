from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import jwt
from fastapi import Header, HTTPException
from app.core.config import settings


def hash_password(password: str, salt: str) -> str:
    return hashlib.md5(f"{password}{salt}".encode()).hexdigest()


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def new_salt() -> str:
    return secrets.token_hex(8)


def get_current_user_id(authorization: str | None = Header(default=None)) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(authorization[7:], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Token 无效或已过期") from exc
    except jwt.InvalidKeyError as exc:
        # 服务端 JWT 密钥未配置等问题，按未登录处理而非 500
        raise HTTPException(status_code=401, detail="登录态校验失败") from exc
