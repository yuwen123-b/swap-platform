"""验证码服务：进程内内存存储。

适用于开发环境 / 单实例部署：
- 验证码 6 位数字，5 分钟过期；
- 同一目标 + 场景 60 秒内不可重复发送；
- 校验成功后立即失效（防重放）。

注意：内存存储在服务重启后丢失，且不支持多实例共享，
水平扩展时需替换为 Redis 等共享存储。
"""

from datetime import datetime, timedelta
import secrets
import threading

# (target, target_type, scene) -> 验证码记录
_STORE: dict[tuple[str, int, int], dict] = {}
_LOCK = threading.Lock()

CODE_TTL = timedelta(minutes=5)
RESEND_INTERVAL = timedelta(seconds=60)


def _purge_expired_locked(now: datetime) -> None:
    expired = [key for key, item in _STORE.items() if item["expires_at"] <= now]
    for key in expired:
        del _STORE[key]


def create_code(target: str, target_type: int, scene: int) -> str:
    now = datetime.now()
    key = (target, target_type, scene)
    with _LOCK:
        _purge_expired_locked(now)
        latest = _STORE.get(key)
        if latest and now - latest["created_at"] < RESEND_INTERVAL:
            raise ValueError("验证码发送过于频繁，请稍后再试")

        code = f"{secrets.randbelow(1000000):06d}"
        _STORE[key] = {
            "code": code,
            "created_at": now,
            "expires_at": now + CODE_TTL,
            "used": False,
        }
    return code


def verify_code(target: str, target_type: int, scene: int, code: str) -> bool:
    now = datetime.now()
    key = (target, target_type, scene)
    with _LOCK:
        item = _STORE.get(key)
        if (
            not item
            or item["used"]
            or item["expires_at"] <= now
            or item["code"] != code
        ):
            return False
        item["used"] = True
        return True
