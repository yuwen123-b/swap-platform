from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import time
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


def get_optional_user_id(authorization: str | None = Header(default=None)) -> int | None:
    """可选登录态：未带 token 或 token 无效时返回 None，不抛 401。

    用于「不登录也能访问、但登录后有额外能力」的接口
    （如物品列表按距离排序：登录用户可直接使用其已保存的位置）。
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        payload = jwt.decode(authorization[7:], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, jwt.InvalidKeyError):
        return None


# ========== 受控文件签名（禁止图片直链访问） ==========
# 图片等静态资源不再直接暴露目录，改为带 HMAC 签名的 URL：
#   /api/v1/static/items/xxx.jpg?exp=1700000000&sig=xxxx
# 服务端校验签名与有效期后才返回文件，未签名或过期则拒绝访问。

def _file_signature(relative_path: str, expires_at: int) -> str:
    """对待签名的相对路径与过期时间计算 HMAC-SHA256 摘要。"""
    payload = f"{relative_path}:{expires_at}".encode()
    return hmac.new(settings.jwt_secret.encode(), payload, hashlib.sha256).hexdigest()


def sign_file_path(relative_path: str, expire_seconds: int | None = None) -> str:
    """为 uploads 下的相对路径生成查询串（exp + sig）。

    返回形如 "exp=1700000000&sig=abcdef..."，由调用方拼接在 URL 之后。
    """
    expire = expire_seconds if expire_seconds is not None else settings.file_url_expire_seconds
    expires_at = int(time.time()) + int(expire)
    return f"exp={expires_at}&sig={_file_signature(relative_path, expires_at)}"


def verify_file_signature(relative_path: str, expires_at: int, signature: str) -> bool:
    """校验文件访问签名：先验时效，再用恒定时间比较验证摘要。"""
    if expires_at < int(time.time()):
        return False
    expected = _file_signature(relative_path, expires_at)
    return hmac.compare_digest(expected, signature or "")
