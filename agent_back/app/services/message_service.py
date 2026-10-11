"""私信服务：发送、聊天记录、会话列表、已读标记。"""

from app.db.pool import connection


def send_message(sender_id: int, receiver_id: int, content: str, item_id: int | None = None) -> int:
    """插入一条私信，返回新消息 ID。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO private_message (sender_id, receiver_id, item_id, content) VALUES (%s,%s,%s,%s)",
                (sender_id, receiver_id, item_id, content),
            )
            return cursor.lastrowid


def get_chat_history(user_id: int, other_user_id: int, item_id: int | None = None) -> list[dict]:
    """获取当前用户与对方的聊天记录（仅双方参与的消息），按发送时间升序。"""
    conditions = ["((pm.sender_id=%s AND pm.receiver_id=%s) OR (pm.sender_id=%s AND pm.receiver_id=%s))"]
    params: list = [user_id, other_user_id, other_user_id, user_id]
    if item_id:
        conditions.append("pm.item_id=%s")
        params.append(item_id)
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT pm.*, u.nickname AS sender_nickname, u.avatar AS sender_avatar "
                f"FROM private_message pm JOIN user u ON u.id=pm.sender_id "
                f"WHERE {where} ORDER BY pm.created_at ASC, pm.id ASC",
                params,
            )
            return cursor.fetchall()


def get_sessions(user_id: int) -> list[dict]:
    """会话列表：按对方用户分组，取每组最后一条消息，并统计未读数。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT pm.*,
                       IF(pm.sender_id=%s, pm.receiver_id, pm.sender_id) AS other_user_id,
                       u.nickname AS other_nickname,
                       u.avatar AS other_avatar,
                       (SELECT COUNT(*) FROM private_message m2
                         WHERE m2.sender_id = IF(pm.sender_id=%s, pm.receiver_id, pm.sender_id)
                           AND m2.receiver_id = %s AND m2.is_read = 0) AS unread_count
                FROM private_message pm
                JOIN user u ON u.id = IF(pm.sender_id=%s, pm.receiver_id, pm.sender_id)
                JOIN (
                    SELECT MAX(id) AS max_id FROM private_message
                    WHERE sender_id=%s OR receiver_id=%s
                    GROUP BY IF(sender_id=%s, receiver_id, sender_id)
                ) latest ON pm.id = latest.max_id
                ORDER BY pm.id DESC
                """,
                (user_id, user_id, user_id, user_id, user_id, user_id, user_id),
            )
            return cursor.fetchall()


def mark_message_read(user_id: int, message_id: int) -> bool:
    """标记消息为已读（仅接收者可标记），返回是否实际发生更新。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE private_message SET is_read=1 WHERE id=%s AND receiver_id=%s AND is_read=0",
                (message_id, user_id),
            )
            return cursor.rowcount > 0
