import json
import logging
from typing import Any

from app.core.config import settings
from app.db.pool import connection

logger = logging.getLogger(__name__)


def log_ai_call(api_name: str, request_body: Any, response_body: Any = None, status: int = 1,
                duration_ms: int | None = None, error_msg: str | None = None) -> None:
    """记录 AI 接口调用日志，供管理端 AI 监控使用。开关关闭或写库失败时静默跳过。"""
    if not settings.ai_monitor_enabled:
        return
    try:
        req = json.dumps(request_body, ensure_ascii=False, default=str)[:4000] if request_body is not None else None
        resp = json.dumps(response_body, ensure_ascii=False, default=str)[:4000] if response_body is not None else None
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ai_log (api_name, request_body, response_body, status, duration_ms, error_msg) VALUES (%s,%s,%s,%s,%s,%s)",
                    (api_name, req, resp, status, duration_ms, error_msg[:500] if error_msg else None),
                )
    except Exception as exc:  # 日志失败不影响业务
        logger.warning("ai_log 写入失败: %s", exc)
