"""平台回收 · 用户端接口（挂载于 `/api/v1/recycle` 与 `/api/recycle` 双前缀）。

3 个接口：估价预览 / 我的回收单 / 取消回收。
提交回收落在 `PUT /api/v1/items/{item_id}/recycle`（item.py，语义归物品侧）。

**为什么估价接口放独立 router 而不是 `/items/recycle/estimate`**：
`@router.get("/{item_id}")` 会把 `recycle` 字符串匹配成 item_id，
Pydantic 转 int 失败 → 422 而非 404（FastAPI 按声明顺序匹配的固有陷阱）。
放新 router 从根上消除这个坑。

响应外壳统一 `success()`（`code:0`），与管理端的 `ok()`（`code:200`）刻意不混用。
回收是平台自营业务，**不受** `settings.merchant_enabled` 开关约束
（商家停业开关不应连带关掉回收）。

鉴权：user_id 一律从 JWT 解析（`Depends(get_current_user_id)`），不接受前端传入。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.services import recycle_service

logger = logging.getLogger(__name__)

LIST_DEFAULT_SIZE = 10
LIST_MAX_SIZE = 100


def _clamp(value: int, low: int, high: int) -> int:
    """分页参数越界一律夹紧而非 422（与 user_center.py 同实现）。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


router = APIRouter()


@router.get("/estimate")
def estimate(condition_level: int = Query(default=0)):
    """估价预览（提交前弹窗展示）。服务端唯一真源 `recycle_service.estimate_points`，
    前端只展示，绝不把公式抄一份到 JS —— 用户看到多少、实际到账就是多少。"""
    return success(recycle_service.estimate_preview(condition_level))


@router.get("/my")
def my_recycles(
    status: int | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=LIST_DEFAULT_SIZE),
    user_id: int = Depends(get_current_user_id),
):
    """我的回收单，可按状态筛选（1待取件 2已入库 3已售出 4已取消）。"""
    status_value: int | None = None
    if status is not None:
        if status not in (1, 2, 3, 4):
            raise HTTPException(400, "回收单状态只能是 1=待取件 / 2=已入库 / 3=已售出 / 4=已取消")
        status_value = int(status)
    page_v = _clamp(page, 1, 10 ** 6)
    size_v = _clamp(size, 1, LIST_MAX_SIZE)

    with connection() as conn:
        with conn.cursor() as cursor:
            data = recycle_service.list_my_recycles(cursor, user_id, status_value, page_v, size_v)
    return success(data)


@router.put("/{recycle_id}/cancel")
def cancel_recycle(recycle_id: int, user_id: int = Depends(get_current_user_id)):
    """取消回收（仅待取件可取消），同事务退回积分（source=9，不撞唯一索引）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            result = recycle_service.cancel_recycle(cursor, user_id, recycle_id)
    return success(result, "已取消回收，积分已退回")
