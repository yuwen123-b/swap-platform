"""个人中心第二 / 三 / 四区接口：我的物品、碳积分（汇总 / 明细 / 社区排名）。

与 `app/api/v1/user.py` 分离，避免单文件继续膨胀；两者路由前缀同为 `/user`，
由 `app/main.py` 的 `_NEW_ROUTERS` 统一双挂载到 `/api/user` 与 `/api/v1/user`。
路径与 user.py 的接口无重叠，且两边都没有路径参数通配，不存在路由抢占。

约定：所有接口的 user_id 一律从 JWT 解析（`Depends(get_current_user_id)`），
不接受前端传入，与其他个人中心接口保持一致。
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.constants import ITEM_STATUS_LABEL, level_progress
from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.schemas.user_center import (
    CarbonRankInfo,
    CarbonSummary,
    ItemBrief,
    PointsLogEntry,
)
from app.services.image_utils import item_covers
from app.services.points_service import source_label

logger = logging.getLogger(__name__)

router = APIRouter()

# ========== 我的物品 ==========
# 可下架的状态：在售(1) 与 待审核(4)
# 已下架(2) 不能重复下架；审核未通过(3) 由管理端语义决定，用户侧不应改写
REMOVABLE_STATUSES = (1, 4)
# 下架后的状态：2（已下架）。刻意不用 3——3 在管理端表示「审核未通过」，
# 两者混用会让管理端「已拒绝」列表混入用户主动下架的物品。
REMOVED_STATUS = 2
ITEM_LIST_DEFAULT_SIZE = 10
ITEM_LIST_MAX_SIZE = 50

# ========== 碳积分 ==========
CARBON_LOG_DEFAULT_LIMIT = 10
CARBON_LOG_MAX_LIMIT = 50


def _clamp(value: int, low: int, high: int) -> int:
    """把分页/条数参数夹到合法区间。

    刻意「夹紧」而不是报 422/400：分页参数越界属于客户端习惯差异，
    静默归一化体验更好，也避免全局 RequestValidationError 处理器
    抛出英文技术报错给终端用户。
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


def _parse_images(raw) -> list[str]:
    """解析 item.images 并返回**已签名**的封面 URL 列表。

    实现统一收敛到 `image_utils.item_covers`（DB 只存相对路径，签名在读取时现场补）。
    与 `favorite._parse_images` 同口径——两者曾各自持有一份，现共用同一实现，
    避免「签名口径」漂移。解析失败一律降级为空列表，绝不让脏数据导致接口 500。
    """
    return item_covers(raw)


def _item_brief(row: dict) -> ItemBrief:
    images = _parse_images(row.get("images"))
    try:
        status = int(row.get("status") or 0)
    except (TypeError, ValueError):
        status = 0
    return ItemBrief(
        id=row["id"],
        title=row.get("title") or "",
        cover=images[0] if images else None,
        status=status,
        status_label=ITEM_STATUS_LABEL.get(status, "未知状态"),
        created_at=row.get("created_at"),
    )


def _log_entry(row: dict) -> PointsLogEntry:
    def _as_int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    source = _as_int(row.get("source"))
    return PointsLogEntry(
        id=row["id"],
        points=_as_int(row.get("points")),
        balance=_as_int(row.get("balance")),
        source=source,
        source_label=source_label(source),
        related_id=row.get("related_id"),
        description=row.get("description"),
        created_at=row.get("created_at"),
    )


# ============================================================
# 第二区：我的物品
# ============================================================
@router.get("/items")
def list_my_items(
    status: int | None = Query(default=None, description="1=在售 2=已下架 3=审核未通过 4=审核中"),
    page: int = Query(default=1),
    size: int = Query(default=ITEM_LIST_DEFAULT_SIZE),
    user_id: int = Depends(get_current_user_id),
):
    """当前用户发布的物品列表（分页，可按状态筛选）。"""
    # status 在函数体内校验而非 Query(ge/le)：全局异常处理器会把 Pydantic 报错
    # 原样转成英文技术串，用户看不懂，这里给明确中文提示。
    if status is not None and status not in ITEM_STATUS_LABEL:
        raise HTTPException(400, "status 取值不合法，可选 1/2/3/4")

    page = _clamp(page, 1, 10 ** 6)
    size = _clamp(size, 1, ITEM_LIST_MAX_SIZE)

    conditions = ["user_id=%s"]
    params: list = [user_id]
    if status is not None:
        conditions.append("status=%s")
        params.append(status)
    where = " AND ".join(conditions)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM item WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"SELECT id, title, images, status, created_at FROM item "
                f"WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()

    # 分页外壳用普通 dict：Pydantic 2.x 下字段名不能叫 list（会遮蔽内建 list）
    return success(
        {
            "total": int(total or 0),
            "page": page,
            "size": size,
            "list": [_item_brief(row).model_dump() for row in rows],
        }
    )


@router.put("/items/{item_id}/remove")
def remove_my_item(item_id: int, user_id: int = Depends(get_current_user_id)):
    """下架自己的物品：status -> 2（已下架）。

    归属与状态先用 SELECT 判断，便于给出精确提示；
    真正生效的 UPDATE 依然带 `AND user_id=%s AND status IN (...)`，
    避免「检查通过后、写入前」被并发改动（TOCTOU）。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, user_id, status FROM item WHERE id=%s LIMIT 1", (item_id,))
            row = cursor.fetchone()
            # 不区分「物品不存在」与「不属于我」：统一 404，避免通过状态码枚举他人的 item_id
            if not row or int(row.get("user_id") or 0) != user_id:
                raise HTTPException(404, "物品不存在")

            current_status = int(row.get("status") or 0)
            if current_status not in REMOVABLE_STATUSES:
                raise HTTPException(400, "仅可下架「在售」或「审核中」的物品")

            cursor.execute(
                "UPDATE item SET status=%s WHERE id=%s AND user_id=%s AND status IN (%s, %s)",
                (REMOVED_STATUS, item_id, user_id, *REMOVABLE_STATUSES),
            )
            if cursor.rowcount == 0:
                # 走到这里说明检查与写入之间状态被改了（并发），提示用户刷新重试
                raise HTTPException(400, "下架失败，物品状态已变化，请刷新后重试")

    return success(
        {
            "id": item_id,
            "status": REMOVED_STATUS,
            "status_label": ITEM_STATUS_LABEL[REMOVED_STATUS],
        },
        "物品已下架",
    )


# ============================================================
# 第四区：碳积分
# ============================================================
@router.get("/carbon/summary")
def carbon_summary(user_id: int = Depends(get_current_user_id)):
    """碳积分汇总：总积分 / 碳减排量 / 完成交换次数 / 等级 / 晋级进度。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT points, carbon_total, exchange_count FROM user WHERE id=%s LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")

    try:
        total_points = int(row.get("points") or 0)
    except (TypeError, ValueError):
        total_points = 0
    try:
        carbon_total = float(row.get("carbon_total") or 0)
    except (TypeError, ValueError):
        carbon_total = 0.0
    try:
        exchange_count = int(row.get("exchange_count") or 0)
    except (TypeError, ValueError):
        exchange_count = 0

    payload = CarbonSummary(
        total_points=total_points,
        carbon_total=carbon_total,
        exchange_count=exchange_count,
        # 等级阈值与前端 Hero 卡同一套数值，定义在 app/core/constants.py
        **level_progress(total_points),
    )
    return success(payload.model_dump())


@router.get("/carbon/logs")
def carbon_logs(
    limit: int = Query(default=CARBON_LOG_DEFAULT_LIMIT, description="返回条数，默认 10，上限 50"),
    user_id: int = Depends(get_current_user_id),
):
    """积分明细：points_log 中当前用户的最近 N 条记录。"""
    if limit < 1:
        raise HTTPException(400, "limit 至少为 1")
    # 超大值夹到上限而不是报错，避免前端传 999 直接失败
    limit = min(limit, CARBON_LOG_MAX_LIMIT)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, points, balance, source, related_id, description, created_at "
                "FROM points_log WHERE user_id=%s ORDER BY id DESC LIMIT %s",
                (user_id, limit),
            )
            rows = cursor.fetchall()

    # 同上：外壳用 dict，避免字段名 list 与内建类型冲突
    return success({"limit": limit, "list": [_log_entry(row).model_dump() for row in rows]})


@router.get("/carbon/rank")
def carbon_rank(user_id: int = Depends(get_current_user_id)):
    """当前用户在其所属社区内的碳积分排名。

    用 COUNT 子查询而不是 `RANK() OVER (...)`：窗口函数需要 MySQL 8.0+，
    本项目其余 SQL 均为 5.7 兼容写法，保持一致。
    名次口径：同社区中积分严格高于自己的人数 + 1（同分并列）。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT community, points FROM user WHERE id=%s LIMIT 1", (user_id,))
            me = cursor.fetchone()
            if not me:
                raise HTTPException(404, "用户不存在")

            community = (me.get("community") or "").strip()
            if not community:
                # 未设置社区时不退化到「全站排名」——口径不同会误导用户
                return success(
                    CarbonRankInfo(rank=None, total=0, community=None).model_dump(),
                    "未设置所在社区，暂无排名",
                )

            try:
                my_points = int(me.get("points") or 0)
            except (TypeError, ValueError):
                my_points = 0

            cursor.execute("SELECT COUNT(*) AS total FROM user WHERE community=%s", (community,))
            total = cursor.fetchone()["total"]
            cursor.execute(
                "SELECT COUNT(*) AS higher FROM user WHERE community=%s AND points > %s",
                (community, my_points),
            )
            higher = cursor.fetchone()["higher"]

    payload = CarbonRankInfo(rank=int(higher or 0) + 1, total=int(total or 0), community=community)
    return success(payload.model_dump())
