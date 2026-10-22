"""我的收藏：收藏 / 取消收藏 / 收藏列表 / 检查是否已收藏。

user_id 一律从 JWT 解析（`Depends(get_current_user_id)`），不接受前端传入，
与个人中心其余接口保持一致。路由前缀为 `/user`，由 `app/main.py` 的
`_NEW_ROUTERS` 统一双挂载到 `/api/user` 与 `/api/v1/user`；路径与 user.py、
user_center.py 均无重叠，也不存在路径参数通配，无路由抢占。

表结构由 `app/db/pool.py` 的 `ensure_personal_center_tables()` 幂等维护：
复用既有 `favorite` 表，并补 `uk_user_item (user_id, item_id)` 唯一索引，
使「收藏」天然幂等——重复点击不会产生重复行。
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.constants import ITEM_STATUS_LABEL
from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.schemas.personal_center import FavoriteItem
from app.services.image_utils import item_covers

logger = logging.getLogger(__name__)

router = APIRouter()

FAVORITE_LIST_DEFAULT_SIZE = 10
FAVORITE_LIST_MAX_SIZE = 50
# 物品已被删除（LEFT JOIN 取不到 item 行）时的展示文案
MISSING_ITEM_LABEL = "物品已不存在"


def _clamp(value: int, low: int, high: int) -> int:
    """把分页参数夹到合法区间。

    刻意「夹紧」而非报 422/400：分页参数越界属于客户端习惯差异，
    且全局异常处理器会把 Pydantic 的英文报错原样透出，用户看不懂。
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


def _parse_images(raw) -> list[str]:
    """解析 item.images 并返回**已签名**的封面 URL 列表。

    实现统一收敛到 `image_utils.item_covers`（DB 只存相对路径，签名在读取时现场补），
    与 `user_center._parse_images` 同口径。解析失败一律降级为空列表，
    绝不让脏数据导致整个列表接口 500。
    """
    return item_covers(raw)


def _to_favorite(row: dict) -> FavoriteItem:
    """把「favorite LEFT JOIN item」的一行转成响应模型。

    物品已被删除时 item 侧字段全为 NULL，此时给出「物品已不存在」而不是
    映射成某个 status 标签，避免误导。
    """
    item_id = row.get("item_id_raw")
    is_missing = item_id is None
    images = _parse_images(row.get("images"))
    try:
        status = int(row.get("status") or 0)
    except (TypeError, ValueError):
        status = 0
    return FavoriteItem(
        id=int(item_id or 0),
        favorite_id=int(row.get("favorite_id") or 0),
        title=(row.get("title") or "") if not is_missing else "",
        cover=images[0] if images else None,
        status=status,
        status_label=MISSING_ITEM_LABEL if is_missing else ITEM_STATUS_LABEL.get(status, "未知状态"),
        favorited_at=row.get("favorited_at"),
    )


# ============================================================
# 收藏列表
# ============================================================
@router.get("/favorites")
def list_favorites(
    page: int = Query(default=1),
    size: int = Query(default=FAVORITE_LIST_DEFAULT_SIZE),
    user_id: int = Depends(get_current_user_id),
):
    """当前用户的收藏列表（分页，按收藏时间倒序）。"""
    page = _clamp(page, 1, 10 ** 6)
    size = _clamp(size, 1, FAVORITE_LIST_MAX_SIZE)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM favorite WHERE user_id=%s", (user_id,))
            total = cursor.fetchone()["total"]
            # 用 LEFT JOIN：物品被删除后收藏行仍在，需要展示为「物品已不存在」
            cursor.execute(
                "SELECT f.id AS favorite_id, f.created_at AS favorited_at, "
                "       i.id AS item_id_raw, i.title, i.images, i.status "
                "FROM favorite f LEFT JOIN item i ON f.item_id = i.id "
                "WHERE f.user_id=%s ORDER BY f.id DESC LIMIT %s OFFSET %s",
                (user_id, size, (page - 1) * size),
            )
            rows = cursor.fetchall()

    # 分页外壳用普通 dict：Pydantic 2.x 下字段名不能叫 list
    return success(
        {
            "total": int(total or 0),
            "page": page,
            "size": size,
            "list": [_to_favorite(row).model_dump() for row in rows],
        }
    )


# ============================================================
# 是否已收藏（详情页加载时调用，避免「先看到未收藏、点击才发现已收藏」）
# ============================================================
@router.get("/favorites/check/{item_id}")
def check_favorite(item_id: int, user_id: int = Depends(get_current_user_id)):
    """返回当前用户是否已收藏该物品；不校验物品是否存在（纯查询，无副作用）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 AS ok FROM favorite WHERE user_id=%s AND item_id=%s LIMIT 1",
                (user_id, item_id),
            )
            row = cursor.fetchone()
    return success({"item_id": item_id, "favorited": row is not None})


# ============================================================
# 收藏 / 取消收藏
# ============================================================
@router.post("/favorites/{item_id}")
def add_favorite(item_id: int, user_id: int = Depends(get_current_user_id)):
    """收藏物品。

    幂等：`INSERT IGNORE` 配合唯一索引 `uk_user_item`，重复收藏不会报错也不会产生重复行，
    只把「本次是否新建」通过 created 字段告诉前端，用于给出不同文案。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM item WHERE id=%s LIMIT 1", (item_id,))
            if not cursor.fetchone():
                raise HTTPException(404, "物品不存在")
            cursor.execute(
                "INSERT IGNORE INTO favorite (user_id, item_id) VALUES (%s, %s)",
                (user_id, item_id),
            )
            created = cursor.rowcount > 0

    return success(
        {"item_id": item_id, "favorited": True, "created": created},
        "收藏成功" if created else "你已收藏过该物品",
    )


@router.delete("/favorites/{item_id}")
def remove_favorite(item_id: int, user_id: int = Depends(get_current_user_id)):
    """取消收藏（幂等：未收藏时同样返回成功，只是 removed=False）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM favorite WHERE user_id=%s AND item_id=%s",
                (user_id, item_id),
            )
            removed = cursor.rowcount > 0

    return success(
        {"item_id": item_id, "favorited": False, "removed": removed},
        "已取消收藏" if removed else "尚未收藏该物品",
    )
