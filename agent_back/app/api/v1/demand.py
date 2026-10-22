"""我想要的（需求）：个人需求管理 + 首页公开需求墙。

刻意拆成两个 router：
- `router`      个人需求（发布 / 列表 / 编辑 / 撤销 / 完成），路径为 `/user/demands*`，
                并入 `app/main.py` 的 `_NEW_ROUTERS` 双挂载到 `/api/user` 与 `/api/v1/user`；
- `wall_router` 公开需求墙，路径必须是 `/demands`（**不是** `/user/demands`）。
                若也挂 `/user` 前缀，会与「我的需求列表」同路径同 method 直接冲突
                （后注册者覆盖前者），因此由 main.py 单独 include，
                双挂载 `/api/demands` 与 `/api/v1/demands`。

隐私约束：公开墙的 SQL **只取 `u.nickname` 与 `u.building`**，
不查手机号 / 联系方式 / 邮箱——隐私在数据源层就断掉，不依赖前端隐藏。
`user_id` 是内部主键（非隐私字段），用于前端点进去发起私信。

user_id 一律从 JWT 解析，不接受前端传入：
- 个人需求接口用 `get_current_user_id`（未登录 401）；
- 公开墙用 `get_optional_user_id`（未登录也能看，登录后额外排除自己的需求）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.response import success
from app.core.security import get_current_user_id, get_optional_user_id
from app.db.pool import connection
from app.schemas.personal_center import (
    DemandCreate,
    DemandItem,
    DemandUpdate,
    DemandWallItem,
)

logger = logging.getLogger(__name__)

# 个人需求：由 main.py 挂到 /user 前缀
router = APIRouter()
# 公开需求墙：由 main.py 挂到 /demands 前缀（必须是独立前缀）
wall_router = APIRouter()

# ========== 需求状态（与 swap_demand.status 列注释一致） ==========
STATUS_ONGOING = 1
STATUS_DONE = 2
STATUS_CANCELLED = 3
DEMAND_STATUS_LABEL = {
    STATUS_ONGOING: "进行中",
    STATUS_DONE: "已完成",
    STATUS_CANCELLED: "已撤销",
}
VALID_STATUSES = tuple(DEMAND_STATUS_LABEL)

# ========== 分页 / 条数上限 ==========
DEMAND_LIST_DEFAULT_SIZE = 10
DEMAND_LIST_MAX_SIZE = 50
# 首页需求墙：默认 6 条，上限 20（需求方给定）
WALL_DEFAULT_LIMIT = 6
WALL_MAX_LIMIT = 20

# ========== 字段长度上限（与 swap_demand 列宽一致） ==========
MAX_TITLE_LEN = 100
MAX_CATEGORY_LEN = 50
MAX_DESCRIPTION_LEN = 500


def _clamp(value: int, low: int, high: int) -> int:
    """把分页/条数参数夹到合法区间。

    刻意「夹紧」而非报 422/400：分页参数越界属于客户端习惯差异，
    且全局 RequestValidationError 处理器会把 Pydantic 的英文报错原样透出，
    用户看不懂。与 favorite.py / user_center.py 同实现各自持有一份，
    避免 API 层跨模块引用私有函数。
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


def _require_title(raw) -> str:
    """标题必填 + 长度校验，报错用中文（不走 Pydantic 的 max_length）。"""
    title = (raw or "").strip()
    if not title:
        raise HTTPException(400, "请填写需求标题")
    if len(title) > MAX_TITLE_LEN:
        raise HTTPException(400, f"需求标题最多 {MAX_TITLE_LEN} 个字")
    return title


def _optional_text(raw, field_label: str, max_len: int) -> str | None:
    """可选文本字段：空白串归一为 None，超长报中文错。"""
    value = (raw or "").strip()
    if not value:
        return None
    if len(value) > max_len:
        raise HTTPException(400, f"{field_label}最多 {max_len} 个字")
    return value


def _to_demand(row: dict) -> DemandItem:
    try:
        status = int(row.get("status") or STATUS_ONGOING)
    except (TypeError, ValueError):
        status = STATUS_ONGOING
    return DemandItem(
        id=row["id"],
        title=row.get("title") or "",
        description=row.get("description"),
        category=row.get("category"),
        status=status,
        status_label=DEMAND_STATUS_LABEL.get(status, "未知状态"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _to_wall_item(row: dict) -> DemandWallItem:
    """公开墙条目：昵称缺失时回落到「社区邻居」，绝不返回手机号。"""
    try:
        user_id = int(row.get("user_id") or 0)
    except (TypeError, ValueError):
        user_id = 0
    return DemandWallItem(
        id=row["id"],
        user_id=user_id,
        title=row.get("title") or "",
        category=row.get("category"),
        nickname=(row.get("nickname") or "").strip() or "社区邻居",
        building=row.get("building"),
        created_at=row.get("created_at"),
    )


def _fetch_owned(cursor, demand_id: int, user_id: int) -> dict:
    """取需求归属并校验权限。

    不存在与「非本人」统一返回 404（不区分），避免通过状态码枚举他人的需求是否存在。
    """
    cursor.execute("SELECT user_id, status FROM swap_demand WHERE id=%s LIMIT 1", (demand_id,))
    row = cursor.fetchone()
    if not row or int(row["user_id"]) != user_id:
        raise HTTPException(404, "需求不存在")
    return row


# ============================================================
# 我想要的：发布
# ============================================================
@router.post("/demands")
def create_demand(payload: DemandCreate, user_id: int = Depends(get_current_user_id)):
    """发布一条需求，初始状态为「进行中」(1)。"""
    title = _require_title(payload.title)
    description = _optional_text(payload.description, "需求描述", MAX_DESCRIPTION_LEN)
    category = _optional_text(payload.category, "期望类别", MAX_CATEGORY_LEN)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO swap_demand (user_id, title, description, category, status) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, title, description, category, STATUS_ONGOING),
            )
            demand_id = int(cursor.lastrowid or 0)

    return success(
        {
            "id": demand_id,
            "title": title,
            "status": STATUS_ONGOING,
            "status_label": DEMAND_STATUS_LABEL[STATUS_ONGOING],
        },
        "需求发布成功",
    )


# ============================================================
# 我想要的：我的需求列表
# ============================================================
@router.get("/demands")
def list_my_demands(
    status: int | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=DEMAND_LIST_DEFAULT_SIZE),
    user_id: int = Depends(get_current_user_id),
):
    """我的需求列表（可按状态筛选，按发布时间倒序）。"""
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(400, "不支持的需求状态")
    page = _clamp(page, 1, 10 ** 6)
    size = _clamp(size, 1, DEMAND_LIST_MAX_SIZE)

    conditions = ["user_id=%s"]
    params: list = [user_id]
    if status is not None:
        conditions.append("status=%s")
        params.append(status)
    where = " AND ".join(conditions)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM swap_demand WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                "SELECT id, title, description, category, status, created_at, updated_at "
                f"FROM swap_demand WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                (*params, size, (page - 1) * size),
            )
            rows = cursor.fetchall()

    # 分页外壳用普通 dict：Pydantic 2.x 下字段名不能叫 list
    return success(
        {
            "total": int(total or 0),
            "page": page,
            "size": size,
            "list": [_to_demand(row).model_dump() for row in rows],
        }
    )


# ============================================================
# 我想要的：编辑 / 撤销 / 完成
# ============================================================
@router.put("/demands/{demand_id}")
def update_demand(
    demand_id: int,
    payload: DemandUpdate,
    user_id: int = Depends(get_current_user_id),
):
    """编辑需求：仅本人、仅「进行中」状态可编辑；只更新传入的字段。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            row = _fetch_owned(cursor, demand_id, user_id)
            if int(row["status"]) != STATUS_ONGOING:
                raise HTTPException(400, "只有进行中的需求可以编辑")

            fields: list[str] = []
            params: list = []
            if payload.title is not None:
                fields.append("title=%s")
                params.append(_require_title(payload.title))
            if payload.description is not None:
                fields.append("description=%s")
                params.append(_optional_text(payload.description, "需求描述", MAX_DESCRIPTION_LEN))
            if payload.category is not None:
                fields.append("category=%s")
                params.append(_optional_text(payload.category, "期望类别", MAX_CATEGORY_LEN))
            if not fields:
                raise HTTPException(400, "没有需要修改的内容")

            params.extend([demand_id, user_id])
            cursor.execute(
                f"UPDATE swap_demand SET {', '.join(fields)} WHERE id=%s AND user_id=%s",
                params,
            )

    return success({"id": demand_id}, "需求已更新")


def _transition(demand_id: int, user_id: int, to_status: int, ok_msg: str, bad_msg: str):
    """「进行中」-> 终态 的统一流转（仅本人可操作）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            row = _fetch_owned(cursor, demand_id, user_id)
            if int(row["status"]) != STATUS_ONGOING:
                raise HTTPException(400, bad_msg)
            cursor.execute(
                "UPDATE swap_demand SET status=%s WHERE id=%s AND user_id=%s",
                (to_status, demand_id, user_id),
            )

    return success(
        {"id": demand_id, "status": to_status, "status_label": DEMAND_STATUS_LABEL[to_status]},
        ok_msg,
    )


@router.put("/demands/{demand_id}/cancel")
def cancel_demand(demand_id: int, user_id: int = Depends(get_current_user_id)):
    """撤销需求：1 -> 3。"""
    return _transition(demand_id, user_id, STATUS_CANCELLED, "需求已撤销", "只有进行中的需求可以撤销")


@router.put("/demands/{demand_id}/complete")
def complete_demand(demand_id: int, user_id: int = Depends(get_current_user_id)):
    """标记需求已完成：1 -> 2。"""
    return _transition(demand_id, user_id, STATUS_DONE, "已标记为完成", "只有进行中的需求可以标记完成")


# ============================================================
# 公开需求墙（首页）：只给进行中的需求，只暴露昵称 + 楼栋
# ============================================================
@wall_router.get("")
def list_demand_wall(
    limit: int = Query(default=WALL_DEFAULT_LIMIT),
    category: str | None = Query(default=None),
    viewer_id: int | None = Depends(get_optional_user_id),
):
    """首页公开需求墙。

    - 只返回 `status=1`（进行中）的需求；
    - 登录后自动排除「自己发布的需求」（避免自己看到自己的）；
      未登录时无「自己」概念，展示全部；
    - `limit` 默认 6、上限 20，越界静默夹紧；
    - 只 SELECT 昵称与楼栋，返回体不含手机号 / 联系方式。
    """
    limit = _clamp(limit, 1, WALL_MAX_LIMIT)

    conditions = ["d.status=%s"]
    params: list = [STATUS_ONGOING]
    keyword = (category or "").strip()
    if keyword:
        conditions.append("d.category=%s")
        params.append(keyword)
    if viewer_id is not None:
        conditions.append("d.user_id<>%s")
        params.append(viewer_id)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT d.id, d.user_id, d.title, d.category, d.created_at, "
                "       u.nickname, u.building "
                "FROM swap_demand d JOIN user u ON d.user_id = u.id "
                f"WHERE {' AND '.join(conditions)} "
                "ORDER BY d.created_at DESC, d.id DESC LIMIT %s",
                (*params, limit),
            )
            rows = cursor.fetchall()

    return success({"list": [_to_wall_item(row).model_dump() for row in rows]})
