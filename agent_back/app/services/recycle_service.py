"""平台回收（二期）的核心业务逻辑。

闭环：用户发布物品选「交给平台回收」→ 平台按成色估价**立即发积分** →
物品进入平台库存 → 运营批量卖给回收商（merchant.category='回收'）→ 毛利统计。

【事务约定 — 与 points_service / merchant_service 完全一致】
本模块所有写函数都接收调用方传入的 `cursor`，**绝不自己开事务 / 不自己取连接**。
调用方负责把「业务写入 + 积分发放/退还」放进同一个 `with connection() as conn` 里，
任一环节抛错整体回滚，不会出现「单建了、分没发」或「分发了、单没落库」。

【三条并发铁律（与 merchant_service 同款）】
1. **防重复发分**：先 INSERT 回收单拿 `lastrowid`，再 `award_points`，
   `related_id=回收单id` —— `uk_points_log_source(source, related_id, user_id)`
   唯一索引因此天然保证「一笔回收只发一次分」。绝不能先发分再建单
   （那时 related_id 只能写 NULL，MySQL 唯一索引不约束 NULL，闸门失效）。
2. **防并发双卖**：批量销售先 `SELECT ... FOR UPDATE` 锁行，
   再用条件更新 `WHERE ... AND status=2` 校验 `rowcount == 条数`，
   不符整笔回滚 —— 两个运营同时卖同一批，只有一个能成功。
3. **防状态回退**：入库 / 取消 / 售出全部用条件更新 + rowcount 判定，
   绝不「先 SELECT 再裸 UPDATE」。

【估价真源】
`estimate_points()` 是**全平台唯一**的估价实现（常量表 + clamp），
前端只调 `GET /recycle/estimate` 展示，绝不把公式抄一份到 JS。
"""
import json
import secrets
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import logging

from app.core.config import settings
from app.core.constants import (
    PICKUP_METHOD_LABEL,
    RECYCLE_ESTIMATE_MAX,
    RECYCLE_ESTIMATE_MIN,
    RECYCLE_ESTIMATE_POINTS,
    RECYCLE_STATUS_LABEL,
)
from app.services.image_utils import item_covers
from app.services.points_service import (
    SOURCE_RECYCLE,
    SOURCE_RECYCLE_CANCEL,
    award_points,
)

logger = logging.getLogger(__name__)

# ========== platform_recycle.status ==========
RECYCLE_STATUS_PENDING = 1      # 待取件
RECYCLE_STATUS_STOCKED = 2      # 已入库（平台库存）
RECYCLE_STATUS_SOLD = 3         # 已售出
RECYCLE_STATUS_CANCELLED = 4    # 已取消

# ========== item.recycle_status（与上表同序，另有 0=不参与） ==========
ITEM_RECYCLE_NONE = 0
ITEM_RECYCLE_PENDING = 1
ITEM_RECYCLE_STOCKED = 2
ITEM_RECYCLE_SOLD = 3
ITEM_RECYCLE_CANCELLED = 4

# ========== platform_sale.status ==========
SALE_STATUS_DEAL = 1

# ========== 取件方式 ==========
PICKUP_TO_POINT = 1     # 送到回收点
PICKUP_DOOR = 2         # 上门取件
PICKUP_METHODS = (PICKUP_TO_POINT, PICKUP_DOOR)

# 单号前缀：PR=平台回收，PS=平台销售（与 RD/SW 的既有前缀族区分，便于对账）
RECYCLE_NO_PREFIX = "PR"
SALE_NO_PREFIX = "PS"
NO_RANDOM_DIGITS = 4

# 批量销售单笔上限（DECIMAL(10,2) 理论上限 99999999.99）
MAX_SALE_AMOUNT = Decimal("99999999.99")
# 批量销售一次最多卖多少条（前端默认不跨页勾选，这里兜底）
MAX_SELL_ITEMS = 100

_MONEY_QUANT = Decimal("0.01")

# items_json 明细快照里允许的最长物品标题（超长截断，防 TEXT 列被单条撑爆）
_SNAPSHOT_TITLE_MAX_LEN = 50


class RecycleError(RuntimeError):
    """平台回收可预期的业务错误（由 main.py 的异常处理器转成对应 HTTP 状态码）。

    与「数据库不可用」等基础设施错误区分：后者原样抛出（500），
    不伪装成业务错误，避免掩盖真实的表结构/连接问题。
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# ============================================================
# 通用工具
# ============================================================
def as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def as_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_money(value) -> Decimal:
    """任意数值 → 两位小数的 Decimal（写 DECIMAL(10,2) 列 / 出 JSON 前统一口径）。

    与 merchant_service.to_money 同实现（HALF_UP）：float `round(0.155, 2)`=0.15
    而 Decimal HALF_UP=0.16，金额必须统一走 Decimal。
    """
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    if amount.is_nan() or amount.is_infinite():
        amount = Decimal("0")
    return amount.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def recycle_status_label(status) -> str:
    try:
        return RECYCLE_STATUS_LABEL.get(int(status), "未知状态")
    except (TypeError, ValueError):
        return "未知状态"


def _generate_no(prefix: str) -> str:
    """生成单号：前缀 + yyyyMMddHHmmss + 4 位随机数字 = 20 字符。

    随机位用 `secrets`（同 generate_redemption_no）：唯一索引是硬约束，
    secrets 分布均匀，撞键概率可忽略（真撞上由唯一索引兜底报错）。
    """
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = secrets.randbelow(10 ** NO_RANDOM_DIGITS)
    return f"{prefix}{stamp}{suffix:0{NO_RANDOM_DIGITS}d}"


# ============================================================
# 估价（服务端唯一真源）
# ============================================================
def estimate_points(condition_level) -> int:
    """按成色等级估价，结果恒在 [RECYCLE_ESTIMATE_MIN, RECYCLE_ESTIMATE_MAX]。

    - 成色缺失 / 非法（含 None、负数、越界）一律回落 **0 档**（最低档），
      与 DB 列默认值（condition_level=0 表示未填写）语义一致；
    - 纯函数：不读库、不读配置，估算结果只由成色决定，方便单测穷举。
    """
    try:
        level = int(condition_level)
    except (TypeError, ValueError):
        level = 0
    base = RECYCLE_ESTIMATE_POINTS.get(level)
    if base is None:
        base = RECYCLE_ESTIMATE_POINTS[0]
    return max(RECYCLE_ESTIMATE_MIN, min(base, RECYCLE_ESTIMATE_MAX))


def estimate_preview(condition_level) -> dict:
    """估价预览响应（GET /recycle/estimate 的返回体）。"""
    return {
        "condition_level": max(0, min(as_int(condition_level), 5)),
        "estimate_points": estimate_points(condition_level),
        "min": RECYCLE_ESTIMATE_MIN,
        "max": RECYCLE_ESTIMATE_MAX,
    }


# ============================================================
# 行 → 响应
# ============================================================
def to_recycle_item(row: dict) -> dict:
    status = as_int(row.get("status"))
    pickup_method = as_int(row.get("pickup_method"))
    return {
        "id": as_int(row.get("id")),
        "recycle_no": row.get("recycle_no") or "",
        "user_id": as_int(row.get("user_id")),
        "user_nickname": row.get("user_nickname") or "社区邻居",
        "item_id": as_int(row.get("item_id")),
        "item_title": row.get("item_title") or "",
        "item_image": row.get("item_image"),
        "points_reward": as_int(row.get("points_reward")),
        "pickup_method": pickup_method,
        "pickup_method_label": PICKUP_METHOD_LABEL.get(pickup_method, "未知方式"),
        "pickup_address": row.get("pickup_address"),
        "status": status,
        "status_label": recycle_status_label(status),
        "received_at": row.get("received_at"),
        "sold_at": row.get("sold_at"),
        "created_at": row.get("created_at"),
    }


def to_sale_item(row: dict) -> dict:
    return {
        "id": as_int(row.get("id")),
        "sale_no": row.get("sale_no") or "",
        "recycler_id": as_int(row.get("recycler_id")),
        "recycler_name": row.get("recycler_name") or "",
        "total_amount": as_float(row.get("total_amount")),
        "item_count": as_int(row.get("item_count")),
        "items": _parse_items_json(row.get("items_json")),
        "status": as_int(row.get("status")),
        "created_at": row.get("created_at"),
    }


def _parse_items_json(raw) -> list[dict]:
    """解析 platform_sale.items_json（销售时快照）。解析失败降级空列表，不 500。"""
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


# ============================================================
# 用户端：提交回收
# ============================================================
def submit_recycle(cursor, user_id: int, item_id: int, pickup_method: int,
                   pickup_address: str | None) -> dict:
    """用户把已发布的物品交给平台回收，**同一事务内**完成：

    1. 读物品并校验（归属 / 状态门 `status IN (1,4)` / 未在回收流程中）；
    2. 按成色（服务端读库，**绝不接受前端传估价**）算 accept_points；
    3. 条件更新 item（exchange_mode=4 + accept_points + recycle_status=1 + status=2）；
    4. INSERT platform_recycle（status=1）→ 拿 lastrowid；
    5. `award_points(+points, source=8, related_id=回收单id)` —— 顺序绝不能反，
       否则 related_id 只能写 NULL，唯一索引防重复发分的闸门失效。

    状态门为什么放宽到 `IN (1,4)`：`POST /items` 落库固定 status=4（待审核），
    只允许 1 会让「发布即回收」100% 报 400。
    """
    if pickup_method not in PICKUP_METHODS:
        raise RecycleError(400, "取件方式只能是 1=送到回收点 / 2=上门取件")

    address = (pickup_address or "").strip() if pickup_address else ""
    if pickup_method == PICKUP_DOOR and not address:
        raise RecycleError(400, "选择上门取件时请填写取件地址")
    if len(address) > 200:
        raise RecycleError(400, "取件地址不能超过 200 个字符")

    cursor.execute(
        "SELECT id, user_id, title, status, recycle_status, condition_level "
        "FROM item WHERE id=%s LIMIT 1",
        (item_id,),
    )
    item = cursor.fetchone()
    if not item:
        raise RecycleError(404, "物品不存在")
    if as_int(item.get("user_id")) != as_int(user_id):
        raise RecycleError(403, "只能回收自己发布的物品")

    item_status = as_int(item.get("status"))
    recycle_status = as_int(item.get("recycle_status"))
    if item_status not in (1, 4):
        raise RecycleError(400, "该物品当前状态不可回收（仅在售 / 审核中的物品可以交给平台回收）")
    if recycle_status in (RECYCLE_STATUS_PENDING, RECYCLE_STATUS_STOCKED, RECYCLE_STATUS_SOLD):
        raise RecycleError(400, "该物品已在回收流程中，请到「我的回收单」查看")

    title = item.get("title") or ""
    points = estimate_points(item.get("condition_level"))

    # 条件更新：并发双击时只有一个请求能拿到 rowcount=1（防重复提交/重复发分第一道闸）
    cursor.execute(
        "UPDATE item SET exchange_mode=4, accept_points=%s, recycle_status=%s, status=2 "
        "WHERE id=%s AND user_id=%s AND status IN (1,4) AND recycle_status IN (0,4)",
        (points, ITEM_RECYCLE_PENDING, item_id, user_id),
    )
    if cursor.rowcount == 0:
        raise RecycleError(400, "该物品已在回收流程中，请到「我的回收单」查看")

    recycle_no = _generate_no(RECYCLE_NO_PREFIX)
    cursor.execute(
        "INSERT INTO platform_recycle "
        "(recycle_no, user_id, item_id, points_reward, pickup_method, pickup_address, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (recycle_no, user_id, item_id, points, pickup_method,
         address if address else None, RECYCLE_STATUS_PENDING),
    )
    recycle_id = as_int(cursor.lastrowid)

    # 先建单、后发分：related_id=回收单id，唯一索引保证一笔回收只发一次分
    balance = award_points(
        cursor,
        user_id,
        points,
        source=SOURCE_RECYCLE,
        related_id=recycle_id,
        description=f"平台回收「{title[:30]}」",
    )

    return {
        "recycle_id": recycle_id,
        "recycle_no": recycle_no,
        "item_id": item_id,
        "points_reward": points,
        "remaining_points": as_int(balance),
        "pickup_method": pickup_method,
        "pickup_method_label": PICKUP_METHOD_LABEL.get(pickup_method, "未知方式"),
    }


# ============================================================
# 用户端：取消回收
# ============================================================
def cancel_recycle(cursor, user_id: int, recycle_id: int) -> dict:
    """用户取消回收（仅 status=1 待取件），同事务内退回积分。

    退还**必须用 source=9**（SOURCE_RECYCLE_CANCEL）：发放时已写过
    `(8, recycle_id, user_id)` 流水，沿用 8 必撞 uk_points_log_source → 409。
    与兑换模块 5（消耗）/7（退还）完全同一个套路。

    取消后 item.status 回 1（重新在售）、recycle_status=4，允许重新提交回收。
    """
    cursor.execute(
        "SELECT id, user_id, item_id, points_reward, status "
        "FROM platform_recycle WHERE id=%s LIMIT 1",
        (recycle_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise RecycleError(404, "回收单不存在")
    if as_int(row.get("user_id")) != as_int(user_id):
        raise RecycleError(403, "只能操作自己的回收单")
    if as_int(row.get("status")) != RECYCLE_STATUS_PENDING:
        raise RecycleError(
            400, f"该回收单当前为「{recycle_status_label(row.get('status'))}」，无法取消"
        )

    # 条件更新：并发下只有一个请求能取消成功
    cursor.execute(
        "UPDATE platform_recycle SET status=%s WHERE id=%s AND user_id=%s AND status=%s",
        (RECYCLE_STATUS_CANCELLED, recycle_id, user_id, RECYCLE_STATUS_PENDING),
    )
    if cursor.rowcount == 0:
        raise RecycleError(400, "该回收单状态已变化，无法取消")

    item_id = as_int(row.get("item_id"))
    cursor.execute(
        "UPDATE item SET recycle_status=%s, status=1 WHERE id=%s",
        (ITEM_RECYCLE_CANCELLED, item_id),
    )

    refund = as_int(row.get("points_reward"))
    balance = award_points(
        cursor,
        user_id,
        refund,
        source=SOURCE_RECYCLE_CANCEL,
        related_id=recycle_id,
        description="平台回收取消退还",
    )
    return {
        "recycle_id": recycle_id,
        "status": RECYCLE_STATUS_CANCELLED,
        "refund_points": refund,
        "remaining_points": as_int(balance),
    }


# ============================================================
# 用户端：我的回收单（只读）
# ============================================================
def list_my_recycles(cursor, user_id: int, status: int | None,
                     page: int, size: int) -> dict:
    where = "r.user_id=%s"
    params: list = [user_id]
    if status is not None:
        where += " AND r.status=%s"
        params.append(status)

    cursor.execute(
        f"SELECT COUNT(*) AS total FROM platform_recycle r WHERE {where}", params
    )
    total = as_int((cursor.fetchone() or {}).get("total"))
    cursor.execute(
        f"""SELECT r.*, i.title AS item_title, i.images AS item_images,
                   u.nickname AS user_nickname
            FROM platform_recycle r
            LEFT JOIN item i ON r.item_id = i.id
            LEFT JOIN user u ON r.user_id = u.id
            WHERE {where}
            ORDER BY r.id DESC LIMIT %s OFFSET %s""",
        params + [size, (page - 1) * size],
    )
    rows = cursor.fetchall()
    return {
        "total": total,
        "page": page,
        "size": size,
        "list": [_to_my_recycle_item(row) for row in rows],
    }


def _to_my_recycle_item(row: dict) -> dict:
    """用户侧列表行：不透出 user 字段，只透出物品摘要。"""
    data = to_recycle_item(row)
    data.pop("user_id", None)
    data.pop("user_nickname", None)
    return data


def parse_first_image(raw) -> str | None:
    """从 item.images 取首图，返回**读取时现场签名**的受控 URL。

    DB 只存相对路径（2026-10 起），历史脏数据里已带 `?exp=&sig=` 的旧值
    由 `normalize_image_ref` 剥旧签名后重签。脏数据降级 None，不 500。
    """
    covers = item_covers(raw)
    return covers[0] if covers else None


# ============================================================
# 运营端：入库 / 批量销售 / 销售记录 / 统计
# ============================================================
def receive_recycle(cursor, recycle_id: int) -> dict:
    """运营标记已入库：1 → 2，写 received_at，同步 item.recycle_status=2。"""
    cursor.execute(
        "SELECT id, status FROM platform_recycle WHERE id=%s LIMIT 1", (recycle_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise RecycleError(404, "回收单不存在")

    cursor.execute(
        "UPDATE platform_recycle SET status=%s, received_at=NOW() "
        "WHERE id=%s AND status=%s",
        (RECYCLE_STATUS_STOCKED, recycle_id, RECYCLE_STATUS_PENDING),
    )
    if cursor.rowcount == 0:
        current = as_int(row.get("status"))
        raise RecycleError(
            400, f"该回收单当前为「{recycle_status_label(current)}」，仅待取件可标记入库"
        )

    return {
        "recycle_id": recycle_id,
        "status": RECYCLE_STATUS_STOCKED,
        "status_label": recycle_status_label(RECYCLE_STATUS_STOCKED),
    }


def get_recycler(cursor, recycler_id: int) -> dict:
    """校验回收商：merchant.category='回收' 且 status=1。merchant 全程只读。"""
    cursor.execute(
        "SELECT id, name FROM merchant WHERE id=%s AND category=%s AND status=1 LIMIT 1",
        (recycler_id, "回收"),
    )
    row = cursor.fetchone()
    if not row:
        raise RecycleError(400, "回收商不存在或不可用（仅「已通过审核且类型为回收」的商家可选）")
    return row


def sell_to_recycler(cursor, recycler_id: int, recycle_ids: list[int],
                     total_amount) -> dict:
    """批量把已入库物品卖给回收商（单事务，见模块头的并发铁律 2）。

    任务书原步骤漏了「同步 item.recycle_status=3」，这里补上 ——
    不同步的话物品侧会永远停在「已入库」。
    """
    if not recycle_ids:
        raise RecycleError(400, "请先勾选要出售的回收单")
    # 去重 + 限流：前端默认不跨页勾选，这里兜底防一次提交上百条
    ids = sorted({as_int(i) for i in recycle_ids if as_int(i) > 0})
    if not ids:
        raise RecycleError(400, "请先勾选要出售的回收单")
    if len(ids) > MAX_SELL_ITEMS:
        raise RecycleError(400, f"单次最多出售 {MAX_SELL_ITEMS} 条回收单")

    amount = to_money(total_amount)
    if amount <= 0:
        raise RecycleError(400, "销售金额必须大于 0")
    if amount > MAX_SALE_AMOUNT:
        raise RecycleError(400, "销售金额超出上限")

    recycler = get_recycler(cursor, recycler_id)

    # 一次性锁行：防止两个运营同时卖同一批
    placeholders = ", ".join(["%s"] * len(ids))
    cursor.execute(
        f"SELECT id, item_id, recycle_no, points_reward, status "
        f"FROM platform_recycle WHERE id IN ({placeholders}) FOR UPDATE",
        ids,
    )
    rows = cursor.fetchall()
    if len(rows) != len(ids):
        raise RecycleError(400, "部分回收单不存在，请刷新后重试")
    not_stocked = [r for r in rows if as_int(r.get("status")) != RECYCLE_STATUS_STOCKED]
    if not_stocked:
        nos = "、".join(r.get("recycle_no") or str(r.get("id")) for r in not_stocked[:5])
        raise RecycleError(
            400, f"回收单 {nos} 不在已入库状态，仅已入库的物品可以出售"
        )

    # 物品明细快照：销售时的标题/积分，后续改名不影响历史单据
    item_ids = sorted({as_int(r.get("item_id")) for r in rows})
    title_by_id: dict[int, str] = {}
    if item_ids:
        ph = ", ".join(["%s"] * len(item_ids))
        cursor.execute(f"SELECT id, title FROM item WHERE id IN ({ph})", item_ids)
        title_by_id = {as_int(r.get("id")): (r.get("title") or "") for r in cursor.fetchall()}

    snapshot = []
    for r in rows:
        item_id = as_int(r.get("item_id"))
        title = (title_by_id.get(item_id) or "")[:_SNAPSHOT_TITLE_MAX_LEN]
        snapshot.append({
            "recycle_id": as_int(r.get("id")),
            "recycle_no": r.get("recycle_no") or "",
            "item_id": item_id,
            "item_title": title,
            "points_reward": as_int(r.get("points_reward")),
        })
    items_json = json.dumps(snapshot, ensure_ascii=False)

    sale_no = _generate_no(SALE_NO_PREFIX)
    cursor.execute(
        "INSERT INTO platform_sale (sale_no, recycler_id, total_amount, item_count, items_json, status) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (sale_no, recycler_id, str(amount), len(ids), items_json, SALE_STATUS_DEAL),
    )
    sale_id = as_int(cursor.lastrowid)

    # 条件更新：rowcount 必须等于条数，否则（并发下另一运营已卖掉其中一单）整笔回滚
    cursor.execute(
        f"UPDATE platform_recycle SET status=%s, sold_at=NOW() "
        f"WHERE id IN ({placeholders}) AND status=%s",
        [RECYCLE_STATUS_SOLD, *ids, RECYCLE_STATUS_STOCKED],
    )
    if cursor.rowcount != len(ids):
        raise RecycleError(409, "部分回收单状态已变化，本次出售未完成，请刷新后重试")

    # 同步物品侧（任务书遗漏项）：item.recycle_status → 3
    cursor.execute(
        f"UPDATE item SET recycle_status=%s WHERE id IN ({ph})",
        [ITEM_RECYCLE_SOLD, *item_ids],
    )

    return {
        "sale_id": sale_id,
        "sale_no": sale_no,
        "recycler_id": recycler_id,
        "recycler_name": recycler.get("name") or "",
        "total_amount": float(amount),
        "item_count": len(ids),
    }


def list_sales(cursor, recycler_id: int | None, page: int, size: int) -> dict:
    where = "1=1"
    params: list = []
    if recycler_id:
        where += " AND s.recycler_id=%s"
        params.append(recycler_id)

    cursor.execute(f"SELECT COUNT(*) AS total FROM platform_sale s WHERE {where}", params)
    total = as_int((cursor.fetchone() or {}).get("total"))
    cursor.execute(
        f"""SELECT s.*, m.name AS recycler_name
            FROM platform_sale s LEFT JOIN merchant m ON s.recycler_id = m.id
            WHERE {where}
            ORDER BY s.id DESC LIMIT %s OFFSET %s""",
        params + [size, (page - 1) * size],
    )
    rows = cursor.fetchall()
    return {
        "total": total,
        "page": page,
        "size": size,
        "list": [to_sale_item(row) for row in rows],
    }


def recycle_stats(cursor) -> dict:
    """平台回收运营数据（任务书 6 字段 + 看板扩展 4 项）。

    口径（与《变更影响分析》4.3 一致）：
    - `total_received`：曾入库过（status IN (2,3)，已售出也算入过库）；
    - `total_points_issued`：**排除已取消**（取消已退回，计入成本会虚高）；
    - `total_cost`：积分折算，汇率复用 `settings.merchant_points_to_yuan`
      （与商家结算同源，不硬编码 1 元/100 分）；
    - `gross_profit`：允许为负 —— 库存还没卖出时就是负毛利，真实经营状态，不 clamp。
    """
    def _count(sql: str, params: list = ()) -> int:
        cursor.execute(sql, params)
        return as_int((cursor.fetchone() or {}).get("c"))

    total_received = _count(
        "SELECT COUNT(*) AS c FROM platform_recycle WHERE status IN (%s,%s)",
        [RECYCLE_STATUS_STOCKED, RECYCLE_STATUS_SOLD],
    )
    total_sold = _count(
        "SELECT COUNT(*) AS c FROM platform_recycle WHERE status=%s",
        [RECYCLE_STATUS_SOLD],
    )
    pending_pickup = _count(
        "SELECT COUNT(*) AS c FROM platform_recycle WHERE status=%s",
        [RECYCLE_STATUS_PENDING],
    )
    cursor.execute(
        "SELECT COALESCE(SUM(points_reward), 0) AS p FROM platform_recycle "
        "WHERE status IN (%s,%s,%s)",
        [RECYCLE_STATUS_PENDING, RECYCLE_STATUS_STOCKED, RECYCLE_STATUS_SOLD],
    )
    total_points_issued = as_int((cursor.fetchone() or {}).get("p"))

    cursor.execute(
        "SELECT COALESCE(SUM(total_amount), 0) AS m FROM platform_sale WHERE status=%s",
        [SALE_STATUS_DEAL],
    )
    total_revenue = to_money((cursor.fetchone() or {}).get("m"))

    yuan_per_point = Decimal(str(settings.merchant_points_to_yuan))
    total_cost = to_money(Decimal(total_points_issued) * yuan_per_point)
    gross_profit = to_money(total_revenue - total_cost)

    cursor.execute("SELECT status, COUNT(*) AS c FROM platform_recycle GROUP BY status")
    counts = {as_int(r.get("status")): as_int(r.get("c")) for r in cursor.fetchall()}
    status_distribution = [
        {"status": s, "status_label": recycle_status_label(s), "count": counts.get(s, 0)}
        for s in (1, 2, 3, 4)
    ]

    cursor.execute(
        """SELECT s.recycler_id, m.name AS recycler_name,
                  SUM(s.total_amount) AS amount, COUNT(*) AS sales,
                  SUM(s.item_count) AS items
           FROM platform_sale s LEFT JOIN merchant m ON s.recycler_id = m.id
           GROUP BY s.recycler_id, m.name
           ORDER BY amount DESC, s.recycler_id ASC LIMIT 10"""
    )
    top_recyclers = [
        {
            "recycler_id": as_int(r.get("recycler_id")),
            "recycler_name": r.get("recycler_name") or "未知回收商",
            "total_amount": as_float(r.get("amount")),
            "sale_count": as_int(r.get("sales")),
            "item_count": as_int(r.get("items")),
        }
        for r in cursor.fetchall()
    ]

    return {
        "total_received": total_received,
        "total_sold": total_sold,
        "total_points_issued": total_points_issued,
        "total_revenue": float(total_revenue),
        "total_cost": float(total_cost),
        "gross_profit": float(gross_profit),
        "points_to_yuan": as_float(settings.merchant_points_to_yuan),
        "pending_pickup": pending_pickup,
        "status_distribution": status_distribution,
        "top_recyclers": top_recyclers,
    }
