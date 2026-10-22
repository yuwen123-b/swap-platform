"""物品查询工具：供智能体助手通过 function-calling 调用，查询平台物品数据库。

工具契约（与 agent.py 的 OpenAI tool schema 对齐）：
- search_items(keyword, category)        关键词 + 分类模糊查询可用物品
- find_nearby_items(latitude, longitude, radius)  基于物品坐标 Haversine 距离排序

只读查询，不写库；返回结构化 JSON 供 LLM 组织自然语言回复。
"""
import logging
import math
from typing import Any

from app.db.pool import connection

logger = logging.getLogger(__name__)

# item.status 取值：1=审核通过可交换（见 item.py list_items 默认 status=1）
AVAILABLE_STATUS = 1
DEFAULT_LIMIT = 10
MAX_LIMIT = 20


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """用 Haversine 公式计算两点间球面距离（公里）。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _to_float(value: Any) -> float | None:
    """安全把 DECIMAL/str 转 float；失败返回 None。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_to_summary(row: dict, distance_km: float | None = None) -> dict:
    """把物品行精简成 LLM 易读的摘要 dict。"""
    summary = {
        "item_id": row.get("id"),
        "title": row.get("title"),
        "description": (row.get("description") or "")[:80],
        "category": row.get("category_name") or row.get("name"),
        "condition_level": row.get("condition_level"),
        "exchange_mode": row.get("exchange_mode"),
        "expected_item": row.get("expected_item"),
        "owner_id": row.get("user_id"),
    }
    if distance_km is not None:
        summary["distance_km"] = round(distance_km, 2)
    return summary


def search_items(keyword: str, category: str | None = None, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """按关键词 + 分类查询可用物品（title/description 模糊匹配）。

    Args:
        keyword: 搜索词，匹配物品标题或描述；为空则按分类列出最新。
        category: 分类名（如「图书文具」），None 表示不限分类。
        limit: 返回条数上限，强制 clamp 到 [1, MAX_LIMIT]。
    """
    limit = max(1, min(MAX_LIMIT, int(limit or DEFAULT_LIMIT)))
    conditions = ["i.status = %s"]
    params: list[Any] = [AVAILABLE_STATUS]
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        conditions.append("(i.title LIKE %s OR i.description LIKE %s)")
        params.extend([kw, kw])
    if category and category.strip():
        conditions.append("c.name = %s")
        params.append(category.strip())

    where = " AND ".join(conditions)
    sql = (
        f"SELECT i.id, i.user_id, i.title, i.description, i.category_id, i.condition_level, "
        f"i.exchange_mode, i.expected_item, i.latitude, i.longitude, c.name AS category_name "
        f"FROM item i LEFT JOIN category c ON i.category_id = c.id "
        f"WHERE {where} ORDER BY i.id DESC LIMIT %s"
    )
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params + [limit])
                rows = cursor.fetchall()
        return [_row_to_summary(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_items 查询失败 keyword=%s category=%s：%s", keyword, category, exc)
        return []


def find_nearby_items(
    latitude: float,
    longitude: float,
    radius_km: float = 5.0,
    keyword: str = "",
    limit: int = DEFAULT_LIMIT,
    viewer_user_id: int | None = None,
) -> list[dict]:
    """查询指定坐标 radius_km 半径内的可用物品，按距离升序排序。

    隐私规则（user.location_public）：
    - 仅返回所有者已公开位置的物品（u.location_public = 1）；
    - 例外：查看者自己的物品始终可见（不受其自身 location_public 影响），
      这样「关闭公开」的用户自己仍能用「离我最近」看到自己发布的物品。

    物品表无坐标或距离超半径的过滤掉；坐标非法时返回空列表。
    """
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return []
    radius = max(0.1, min(50.0, float(radius_km or 5.0)))
    limit = max(1, min(MAX_LIMIT, int(limit or DEFAULT_LIMIT)))

    # 先取可用且带坐标的物品（粗筛：用 bounding box 缩小候选集，再做精确 Haversine）
    # bounding box：纬度 1°≈111km，经度 1°≈111*cos(lat)km
    lat_delta = radius / 111.0
    lng_delta = radius / (111.0 * max(math.cos(math.radians(lat)), 0.2))
    conditions = [
        "i.status = %s",
        "i.latitude IS NOT NULL",
        "i.longitude IS NOT NULL",
        "i.latitude BETWEEN %s AND %s",
        "i.longitude BETWEEN %s AND %s",
    ]
    params: list[Any] = [AVAILABLE_STATUS, lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta]
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        conditions.append("(i.title LIKE %s OR i.description LIKE %s)")
        params.extend([kw, kw])

    # 隐私过滤：仅展示所有者已公开位置的物品；查看者查看自己的物品不受此限。
    # 用 LEFT JOIN + COALESCE 兼容 owner 行缺失的异常数据（视为不公开）。
    if viewer_user_id is not None:
        conditions.append("(COALESCE(u.location_public, 0) = 1 OR i.user_id = %s)")
        params.append(viewer_user_id)
    else:
        conditions.append("COALESCE(u.location_public, 0) = 1")

    where = " AND ".join(conditions)
    sql = (
        f"SELECT i.id, i.user_id, i.title, i.description, i.category_id, i.condition_level, "
        f"i.exchange_mode, i.expected_item, i.latitude, i.longitude, c.name AS category_name "
        f"FROM item i "
        f"LEFT JOIN category c ON i.category_id = c.id "
        f"LEFT JOIN user u ON i.user_id = u.id "
        f"WHERE {where} ORDER BY i.id DESC LIMIT %s"
    )
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params + [limit * 5])  # 多取一些以便精确过滤后仍够数
                rows = cursor.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("find_nearby_items 查询失败 lat=%s lng=%s：%s", latitude, longitude, exc)
        return []

    # 精确 Haversine 过滤 + 排序
    with_distance: list[tuple[float, dict]] = []
    for r in rows:
        item_lat = _to_float(r.get("latitude"))
        item_lng = _to_float(r.get("longitude"))
        if item_lat is None or item_lng is None:
            continue
        dist = _haversine_km(lat, lng, item_lat, item_lng)
        if dist <= radius:
            with_distance.append((dist, _row_to_summary(r, dist)))
    with_distance.sort(key=lambda x: x[0])
    return [item for _, item in with_distance[:limit]]


def get_user_profile(user_id: int) -> dict:
    """读取用户的位置信息（供 Agent 注入上下文）。

    返回 dict：{user_id, latitude, longitude, community, nickname}
    位置未设置时 latitude/longitude/community 为 None。
    """
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, nickname, latitude, longitude, community "
                    "FROM user WHERE id = %s LIMIT 1",
                    (user_id,),
                )
                row = cursor.fetchone()
        if not row:
            return {"user_id": user_id, "latitude": None, "longitude": None, "community": None, "nickname": None}
        return {
            "user_id": row.get("id"),
            "nickname": row.get("nickname"),
            "latitude": _to_float(row.get("latitude")),
            "longitude": _to_float(row.get("longitude")),
            "community": row.get("community"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_user_profile 查询失败 user_id=%s：%s", user_id, exc)
        return {"user_id": user_id, "latitude": None, "longitude": None, "community": None, "nickname": None}
