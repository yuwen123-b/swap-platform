"""志愿者服务：代取任务的创建、查询与状态流转。

状态机：pending（待接单）→ accepted（已接单）→ done（已完成）；cancelled（已取消）。
"""
from app.db.pool import connection
from app.services import notify_service

# 任务状态枚举
STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"
_VALID_TRANSITIONS = {
    STATUS_PENDING: {STATUS_ACCEPTED, STATUS_CANCELLED},
    STATUS_ACCEPTED: {STATUS_DONE, STATUS_CANCELLED},
    STATUS_DONE: set(),
    STATUS_CANCELLED: set(),
}


def create_task(exchange_id: str, requester_id: int, item_id: int | None = None,
                volunteer_id: int | None = None, handover_method: str = "volunteer_pickup",
                note: str = "") -> dict:
    """创建代取任务：指定志愿者则直接为已接单，否则挂起并推送社区志愿者群。"""
    status = STATUS_ACCEPTED if volunteer_id else STATUS_PENDING
    with connection() as conn:
        with conn.cursor() as cursor:
            item_title = ""
            if item_id:
                cursor.execute("SELECT title FROM item WHERE id=%s LIMIT 1", (item_id,))
                row = cursor.fetchone()
                item_title = (row or {}).get("title") or ""
            cursor.execute(
                """INSERT INTO volunteer_task
                       (exchange_id, requester_id, volunteer_id, item_id,
                        handover_method, status, note)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (exchange_id, requester_id, volunteer_id, item_id,
                 handover_method, status, note),
            )
            task_id = cursor.lastrowid
    if not volunteer_id:
        # 未指定志愿者：推送社区志愿者群（mock 降级不阻断）
        notify_service.push_volunteer_task(task_id, item_title or "待查看", note)
    return {"task_id": task_id, "status": status}


def list_tasks(user_id: int) -> list[dict]:
    """查询与用户相关的任务（作为委托人、志愿者，或可接的待接单任务）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT t.*, i.title AS item_title
                   FROM volunteer_task t
                   LEFT JOIN item i ON t.item_id = i.id
                   WHERE t.requester_id=%s OR t.volunteer_id=%s OR t.status=%s
                   ORDER BY t.id DESC LIMIT 50""",
                (user_id, user_id, STATUS_PENDING),
            )
            return cursor.fetchall()


def update_status(task_id: int, volunteer_id: int, status: str) -> dict:
    """更新任务状态：接单时绑定志愿者；非法状态流转直接报错。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, volunteer_id FROM volunteer_task WHERE id=%s LIMIT 1",
                           (task_id,))
            task = cursor.fetchone()
            if not task:
                raise ValueError("任务不存在")
            current = task["status"]
            if status not in _VALID_TRANSITIONS.get(current, set()):
                raise ValueError(f"任务状态不能从 {current} 变更为 {status}")
            if status == STATUS_ACCEPTED:
                cursor.execute(
                    "UPDATE volunteer_task SET status=%s, volunteer_id=%s WHERE id=%s",
                    (status, volunteer_id, task_id),
                )
            else:
                cursor.execute("UPDATE volunteer_task SET status=%s WHERE id=%s", (status, task_id))
    return {"task_id": task_id, "status": status}
