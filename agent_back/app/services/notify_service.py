"""通知服务：企业微信机器人 Webhook 推送。

未配置 wework_webhook_url 时降级为日志打印（mock），不阻断业务流程。
"""
import logging

import requests

from app.core.config import settings
from app.db.pool import connection

logger = logging.getLogger(__name__)


def push_wecom_markdown(content: str) -> bool:
    """推送 markdown 消息到企业微信群机器人，返回是否真正推送成功。"""
    if not settings.wework_webhook_url:
        logger.info("[wework mock] %s", content)
        return False
    try:
        resp = requests.post(
            settings.wework_webhook_url,
            json={"msgtype": "markdown", "markdown": {"content": content}},
            timeout=10,
        )
        if resp.status_code >= 400:
            logger.warning("企微推送失败 HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except requests.RequestException as exc:
        logger.warning("企微推送异常：%s", exc)
        return False


def _get_user_name(user_id: int) -> str:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT nickname FROM user WHERE id=%s LIMIT 1", (user_id,))
            row = cursor.fetchone()
    return (row or {}).get("nickname") or f"用户{user_id}"


def push_help_alert(user_id: int, context: str = "") -> bool:
    """一键呼叫：把老人当前操作状态推送给紧急联系人（企微群机器人）。"""
    name = _get_user_name(user_id)
    content = (
        "**助老模式一键呼叫**\n"
        f"> 用户：{name}（ID {user_id}）\n"
        f"> 当前操作：{context or '未提供'}\n"
        "> 请尽快联系老人确认情况。"
    )
    return push_wecom_markdown(content)


def push_volunteer_task(task_id: int, item_title: str, note: str = "") -> bool:
    """志愿者代取任务推送。"""
    content = (
        "**社区代取任务**\n"
        f"> 任务号：{task_id}\n"
        f"> 物品：{item_title}\n"
        f"> 备注：{note or '无'}\n"
        "> 请有空闲的志愿者接单协助。"
    )
    return push_wecom_markdown(content)
