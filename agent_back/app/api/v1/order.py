"""我的交换：发起交换 / 订单列表 / 订单详情 / 确认 / 完成 / 取消。

【路由挂载】
路径为 `/orders*`，**不带 `/user` 前缀**，因此不能并入 `app/main.py` 的
`_NEW_ROUTERS`（那一组统一加 `/user`），而是与需求墙 `demand.wall_router` 同一套路，
由 main.py 单独 include 并双挂载到 `/api/orders` 与 `/api/v1/orders`。
与管理端 `/api/admin/orders` 前缀不同，无路由冲突。

【鉴权】
user_id 一律从 JWT 解析（`Depends(get_current_user_id)`），不接受前端传入，
与个人中心其余接口一致。非订单双方一律拒绝（列表天然只有自己参与的订单；
详情 403、动作 403）。

【状态机】（与 admin/order.py 注释、core/constants.ORDER_STATUS_LABEL 一致）
    1 待确认 --卖家确认--> 2 交换中 --买卖任一方--> 3 已完成
    1 / 2 --买卖任一方--> 4 已取消
    5 争议中：仅管理端可写，用户侧只读展示，不提供任何流转入口。
所有流转都用**条件更新**（`WHERE id=%s AND status=<期望前置态>`）+ rowcount 判定：
并发下两个请求只有一个能改成功，另一个拿到 400「订单状态已变更，请刷新后重试」，
不会出现「两次完成、两次发分」。

【真实库表结构约束 — 写 SQL 前必看】
`order` 表**没有 `updated_at`、也没有 `message` 列**（实测 information_schema）。
INSERT 列清单里出现这两列会直接 1054 Unknown column。
留言走 `private_message` 私信表，不落订单表。

【事务与私信（刻意分两次连接）】
- 订单写入：一个 `with connection()`
- 完成交换：订单状态 + 物品下架 + 发奖，同一 `with connection()`，任一失败整体回滚
- 私信：`message_service.send_message` **自开连接自 commit**，无法与订单插入同事务，
  因此必须放在订单事务**提交之后**；私信失败只记 warning，不回滚订单、不做补偿
  （private_message 是独立记录）。
"""
import json
import logging

import pymysql
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.constants import ITEM_STATUS_LABEL, ORDER_STATUS_LABEL
from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.schemas.personal_center import (
    OrderCreate,
    OrderDetail,
    OrderItemBrief,
    OrderListItem,
    OrderMessageBrief,
    OrderParty,
    OrderTimelineNode,
)
from app.services import message_service
from app.services.image_utils import item_covers
from app.services.order_service import (
    EXCHANGE_TYPE_PURCHASE,
    generate_order_no,
    resolve_order_price,
    reward_exchange_completion,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ========== 订单状态（与 core/constants.ORDER_STATUS_LABEL 同源） ==========
STATUS_PENDING = 1
STATUS_ONGOING = 2
STATUS_DONE = 3
STATUS_CANCELLED = 4
STATUS_DISPUTED = 5
VALID_STATUSES = tuple(ORDER_STATUS_LABEL)

# ========== 物品状态（语义见 core/constants.ITEM_STATUS_LABEL） ==========
# 1=在售（可被发起交换） 2=已下架（订单完成后由本模块写入，避免他人继续发起交换）
ITEM_STATUS_ON_SALE = 1
ITEM_STATUS_OFF_SHELF = 2

# ========== 筛选角色 ==========
ROLE_BUYER = "buyer"
ROLE_SELLER = "seller"
ROLE_ALL = "all"
VALID_ROLES = (ROLE_BUYER, ROLE_SELLER, ROLE_ALL)

# ========== item.exchange_mode -> order.exchange_type 映射 ==========
# item.exchange_mode：1=免费送 2=等价互换 3=低价转让 4=平台回收（DB 列注释口径，不翻转）
# order.exchange_type：1=购买 2=以物换物 3=赠送（DB 列注释口径，不翻转）
# 两套枚举的数值含义不同，必须显式映射（直接把 exchange_mode 写进 exchange_type
# 会把「赠送」记成「购买」）。exchange_mode 为 NULL / 未知值时兜底 2（以物换物）——
# 本平台主流程就是物物交换，兜底值最贴近实际语义。
#
# ⚠️ **mode=4（平台回收）刻意不在映射表里，且在回收流程中不允许进入 order**：
# 物品交给平台回收时立即发积分并下架（item.status=2），不存在「被用户接手」的语义；
# create_order 里有显式断言拦截（见「该物品已交给平台回收」）。用户取消回收后
# recycle_status=4、物品重新在售，此时允许正常发起交换。两侧必须同步维护——
# 若未来扩映射表，先确认该 mode 是否真的有订单语义。
#
# 金额口径（见 order_service.resolve_order_price）：
#   只有 exchange_type=1（购买，即 item.exchange_mode=3 低价转让）写 order.price；
#   赠送 / 以物换物不写金额（INSERT 列清单与历史完全一致）。
EXCHANGE_TYPE_BY_MODE = {1: 3, 2: 2, 3: 1}
DEFAULT_EXCHANGE_TYPE = 2
# 平台回收物品的 exchange_mode（与 item.py 的 EXCHANGE_MODE_RECYCLE 同值；
# 刻意不跨模块 import，保持 order.py 与 item.py 的既有解耦）
EXCHANGE_MODE_RECYCLE = 4

# ========== 分页 / 条数上限 ==========
ORDER_LIST_DEFAULT_SIZE = 10
ORDER_LIST_MAX_SIZE = 50
# 详情页附带的会话消息条数上限（取最新 N 条后反转为升序），避免长会话撑爆响应
MESSAGE_PREVIEW_LIMIT = 20
# 留言长度上限：private_message.content 为 VARCHAR(500)，这里收紧到 200
# （相当于一条正常私信的长度），在接口层用中文报错，不让 1406 泄漏到数据库层
MAX_MESSAGE_LEN = 200

# 订单号撞唯一索引 uk_order_no 时的重试次数
ORDER_NO_MAX_ATTEMPTS = 3
# pymysql 唯一键冲突的 errno（ER_DUP_ENTRY）
_ER_DUP_ENTRY = 1062

# 物品已被删除（LEFT JOIN 取不到 item 行）时的展示文案
MISSING_ITEM_LABEL = "物品已不存在"


def _clamp(value: int, low: int, high: int) -> int:
    """把分页参数夹到合法区间。

    刻意「夹紧」而非报 422/400：分页参数越界属于客户端习惯差异，
    且全局异常处理器会把 Pydantic 的英文报错原样透出，用户看不懂。
    与 favorite.py / demand.py / user_center.py 同实现各自持有一份，
    避免 API 层跨模块引用私有函数。
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(number, high))


def _parse_images(raw) -> list[str]:
    """解析 item.images 并返回**已签名**的封面 URL 列表。

    实现统一收敛到 `image_utils.item_covers`（DB 只存相对路径，签名在读取时现场补）。
    解析失败一律降级为空列表，绝不让脏数据导致整个列表接口 500。
    """
    return item_covers(raw)


def _status_label(status) -> str:
    try:
        return ORDER_STATUS_LABEL.get(int(status or 0), "未知状态")
    except (TypeError, ValueError):
        return "未知状态"


def _nickname_or_fallback(nickname, user_id) -> str:
    """昵称兜底：LEFT JOIN 取不到（用户被删）时给出可读文案，不渲染 null。"""
    if nickname:
        return str(nickname)
    return f"用户{user_id}" if user_id else "社区邻居"


def _viewer_role(buyer_id: int, seller_id: int, viewer_id: int) -> str:
    """判断当前用户在这笔订单里的身份。

    规则：**我是卖家且不是买家 → seller，其余一律 buyer**。
    - 正常订单：我是卖家 → seller（对方是买家）；我是买家 → buyer（对方是卖家）；
    - 自换单（buyer==seller==我，历史脏数据）：归 buyer，
      「对方」退化为我自己，这是可接受的降级（此类订单已无法新产生，下单被 400 拦截）；
    - 列表 `role=all` 时按订单里的**实际身份**判断，而不是统一 buyer 视角——
      否则「我是卖家」的订单会把我自己显示成「对方」，在个人中心卡片上
      会出现「与 我自己」。这一处比实施清单里的描述更精确，行为对用户更正确。
    """
    if seller_id == viewer_id and buyer_id != viewer_id:
        return ROLE_SELLER
    return ROLE_BUYER


def _to_float_price(raw) -> float:
    """把 order.price（DECIMAL / None）安全转 float；非法值一律 0.0，绝不因脏数据 500。"""
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _to_optional_int(raw) -> int | None:
    """可空整数（如 order.exchange_type）：None / 非法值返回 None。"""
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _to_list_item(row: dict, viewer_id: int) -> OrderListItem:
    """把「order LEFT JOIN item LEFT JOIN user×2」的一行转成列表项。"""
    buyer_id = int(row.get("buyer_id") or 0)
    seller_id = int(row.get("seller_id") or 0)
    role = _viewer_role(buyer_id, seller_id, viewer_id)

    if role == ROLE_SELLER:
        other_user_id = buyer_id
        other_nickname = _nickname_or_fallback(row.get("buyer_nickname"), buyer_id)
    else:
        other_user_id = seller_id
        other_nickname = _nickname_or_fallback(row.get("seller_nickname"), seller_id)

    raw_title = row.get("item_title")
    is_missing = not raw_title
    images = _parse_images(row.get("item_images"))

    try:
        status = int(row.get("status") or STATUS_PENDING)
    except (TypeError, ValueError):
        status = STATUS_PENDING

    return OrderListItem(
        order_id=int(row.get("order_id") or 0),
        order_no=str(row.get("order_no") or ""),
        status=status,
        status_label=_status_label(status),
        item_id=int(row.get("item_id") or 0),
        item_title=MISSING_ITEM_LABEL if is_missing else str(raw_title),
        item_image=None if is_missing else (images[0] if images else None),
        other_user_id=other_user_id,
        other_nickname=other_nickname,
        viewer_role=role,
        # 交易方式与成交金额：前端据此决定是否展示价格
        # （仅 exchange_type=1 购买，即「低价转让」单有金额）
        exchange_type=_to_optional_int(row.get("exchange_type")),
        price=_to_float_price(row.get("price")),
        created_at=row.get("created_at"),
        completed_at=row.get("completed_at"),
    )


def _build_timeline(status: int, created_at, completed_at) -> list[OrderTimelineNode]:
    """由当前状态 + 两个时间戳推导时间线（`order` 表没有状态历史表）。

    `at=None` 表示库中确实没有该节点的发生时间（中间态与取消态都没有单独记录），
    前端展示为「—」；不伪造时间戳，也不为此新建 order_status_log 表。
    """
    nodes = [
        OrderTimelineNode(
            status=STATUS_PENDING,
            status_label=_status_label(STATUS_PENDING),
            at=created_at,
        )
    ]
    if status >= STATUS_ONGOING:
        nodes.append(
            OrderTimelineNode(status=STATUS_ONGOING, status_label=_status_label(STATUS_ONGOING), at=None)
        )
    if status == STATUS_DONE:
        nodes.append(
            OrderTimelineNode(status=STATUS_DONE, status_label=_status_label(STATUS_DONE), at=completed_at)
        )
    elif status == STATUS_CANCELLED:
        nodes.append(
            OrderTimelineNode(status=STATUS_CANCELLED, status_label=_status_label(STATUS_CANCELLED), at=None)
        )
    elif status == STATUS_DISPUTED:
        nodes.append(
            OrderTimelineNode(status=STATUS_DISPUTED, status_label=_status_label(STATUS_DISPUTED), at=None)
        )
    return nodes


def _load_order_for_action(cursor, order_id: int, user_id: int) -> dict:
    """取订单并校验「当前用户是订单双方之一」。

    非双方统一 403（而不是 404）：订单号是自增主键，用户本来就能猜到存在性，
    这里给明确提示比伪装成「不存在」更有用，也不会泄露订单内容。
    """
    cursor.execute(
        "SELECT id, order_no, item_id, buyer_id, seller_id, status "
        "FROM `order` WHERE id=%s LIMIT 1",
        (order_id,),
    )
    order = cursor.fetchone()
    if not order:
        raise HTTPException(404, "订单不存在")
    buyer_id = int(order.get("buyer_id") or 0)
    seller_id = int(order.get("seller_id") or 0)
    if user_id not in (buyer_id, seller_id):
        raise HTTPException(403, "无权操作该订单")
    return order


# ============================================================
# 发起交换
# ============================================================
@router.post("")
def create_order(payload: OrderCreate, user_id: int = Depends(get_current_user_id)):
    """发起交换：校验物品 → 建订单 → （提交后）给卖家发私信。"""
    message = (payload.message or "").strip()
    if len(message) > MAX_MESSAGE_LEN:
        raise HTTPException(400, f"留言不能超过 {MAX_MESSAGE_LEN} 字")

    with connection() as conn:
        with conn.cursor() as cursor:
            # exchange_mode 一并取出：用于映射 order.exchange_type（见文件头映射表）；
            # recycle_status 一并取出：平台回收物品的状态门（见下方断言）；
            # price 一并取出：低价转让（exchange_type=1 购买）时落到 order.price 作为成交金额
            cursor.execute(
                "SELECT id, user_id, status, exchange_mode, recycle_status, price "
                "FROM item WHERE id=%s LIMIT 1",
                (payload.item_id,),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(404, "物品不存在")
            if int(item.get("status") or 0) != ITEM_STATUS_ON_SALE:
                raise HTTPException(400, "该物品已下架或已被交换")
            # 断言：平台回收物品不走 order 流程（见文件头 EXCHANGE_TYPE_BY_MODE 注释）。
            # 仅拦「仍在回收流程中」（待取件 1 / 已入库 2 / 已售出 3）的物品；
            # 用户取消回收后 recycle_status=4、status 回 1，物品重新在售，
            # 此时允许正常发起交换（也可再次提交平台回收）。
            if (int(item.get("exchange_mode") or 0) == EXCHANGE_MODE_RECYCLE
                    and int(item.get("recycle_status") or 0) in (1, 2, 3)):
                raise HTTPException(400, "该物品已交给平台回收，不能发起交换")
            seller_id = int(item.get("user_id") or 0)
            if seller_id == user_id:
                raise HTTPException(400, "不能交换自己的物品")

            # 进行中的订单（1 待确认 / 2 交换中）不允许重复发起；
            # 已取消 / 已完成的历史订单不拦，允许再次发起交换。
            cursor.execute(
                "SELECT id FROM `order` WHERE buyer_id=%s AND item_id=%s AND status IN (%s,%s) LIMIT 1",
                (user_id, payload.item_id, STATUS_PENDING, STATUS_ONGOING),
            )
            if cursor.fetchone():
                raise HTTPException(400, "你已对该物品发起过交换请求，请等待对方处理")

            try:
                exchange_type = int(
                    EXCHANGE_TYPE_BY_MODE.get(item.get("exchange_mode"), DEFAULT_EXCHANGE_TYPE)
                )
            except (TypeError, ValueError):
                exchange_type = DEFAULT_EXCHANGE_TYPE

            # 成交金额：只有「购买」（低价转让）带金额，赠送 / 以物换物恒为 0
            order_price = resolve_order_price(exchange_type, item.get("price"))

            order_no = ""
            order_id = 0
            for attempt in range(ORDER_NO_MAX_ATTEMPTS):
                order_no = generate_order_no()
                try:
                    # 注意列清单：真实库 `order` 表**没有 updated_at / message 列**，
                    # 这里绝不能出现它们，否则 1054。
                    if exchange_type == EXCHANGE_TYPE_PURCHASE:
                        # 低价转让：额外写 price（成交金额）。列清单仅在购买单上变化，
                        # 赠送 / 交换单保持历史 SQL 一字不改（不破坏既有行为与断言）。
                        cursor.execute(
                            "INSERT INTO `order` "
                            "(order_no, item_id, buyer_id, seller_id, exchange_type, status, "
                            " created_at, price) "
                            "VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)",
                            (
                                order_no,
                                payload.item_id,
                                user_id,
                                seller_id,
                                exchange_type,
                                STATUS_PENDING,
                                order_price,
                            ),
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO `order` "
                            "(order_no, item_id, buyer_id, seller_id, exchange_type, status, created_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                            (
                                order_no,
                                payload.item_id,
                                user_id,
                                seller_id,
                                exchange_type,
                                STATUS_PENDING,
                            ),
                        )
                    order_id = int(cursor.lastrowid or 0)
                    break
                except pymysql.err.IntegrityError as exc:
                    # 只对「订单号撞唯一索引」重试；其它完整性错误（如非空约束）
                    # 属于真实表结构问题，原样抛出，不掩盖。
                    is_duplicate = bool(exc.args) and exc.args[0] == _ER_DUP_ENTRY
                    if not is_duplicate or attempt == ORDER_NO_MAX_ATTEMPTS - 1:
                        raise
                    logger.warning("订单号 %s 已存在，重新生成后重试", order_no)

    # ---- 以下在订单事务**提交之后**执行 ----
    if message:
        # message_service.send_message 自开连接自 commit，无法与订单插入同事务，
        # 因此必须放在订单提交之后；私信失败**不回滚订单、不做补偿**
        #（private_message 是独立记录，订单才是业务主体）。
        try:
            message_service.send_message(
                sender_id=user_id,
                receiver_id=seller_id,
                content=message,
                item_id=payload.item_id,
            )
        except Exception as exc:  # noqa: BLE001 — 私信是附加动作，失败不应影响下单结果
            logger.warning("订单 %s 已创建，但私信发送失败: %s", order_no, exc)

    return success(
        {"order_id": order_id, "order_no": order_no},
        "交换请求已发送，等待对方确认",
    )


# ============================================================
# 我的交换列表
# ============================================================
@router.get("")
def list_orders(
    role: str = Query(default=ROLE_ALL, description="buyer / seller / all"),
    status: int | None = Query(default=None, description="按订单状态筛选，1-5"),
    page: int = Query(default=1),
    size: int = Query(default=ORDER_LIST_DEFAULT_SIZE),
    user_id: int = Depends(get_current_user_id),
):
    """当前用户参与的交换订单（分页，按 id 倒序）。"""
    if role not in VALID_ROLES:
        raise HTTPException(400, "role 只能是 buyer / seller / all")
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(400, "不支持的订单状态")
    page = _clamp(page, 1, 10 ** 6)
    size = _clamp(size, 1, ORDER_LIST_MAX_SIZE)

    if role == ROLE_BUYER:
        conditions = ["o.buyer_id=%s"]
        params: list = [user_id]
    elif role == ROLE_SELLER:
        conditions = ["o.seller_id=%s"]
        params = [user_id]
    else:
        conditions = ["(o.buyer_id=%s OR o.seller_id=%s)"]
        params = [user_id, user_id]
    if status is not None:
        conditions.append("o.status=%s")
        params.append(status)
    where = " AND ".join(conditions)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM `order` o WHERE {where}", params)
            total = cursor.fetchone()["total"]
            # item 用 LEFT JOIN：物品被删除后订单仍在，需展示为「物品已不存在」。
            # o.item_id 单独取出，保证物品被删时前端仍能拿到可跳转/可展示的 id。
            cursor.execute(
                f"""SELECT o.id AS order_id, o.order_no, o.status, o.created_at, o.completed_at,
                           o.buyer_id, o.seller_id, o.item_id,
                           o.exchange_type, o.price,
                           i.title AS item_title, i.images AS item_images,
                           b.nickname AS buyer_nickname, s.nickname AS seller_nickname
                    FROM `order` o
                    LEFT JOIN item i ON i.id = o.item_id
                    LEFT JOIN user b ON b.id = o.buyer_id
                    LEFT JOIN user s ON s.id = o.seller_id
                    WHERE {where}
                    ORDER BY o.id DESC LIMIT %s OFFSET %s""",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()

    # 分页外壳用普通 dict：Pydantic 2.x 下字段名不能叫 list
    return success(
        {
            "total": int(total or 0),
            "page": page,
            "size": size,
            "list": [_to_list_item(row, user_id).model_dump(mode="json") for row in rows],
        }
    )


# ============================================================
# 订单详情
# ============================================================
@router.get("/{order_id}")
def get_order_detail(order_id: int, user_id: int = Depends(get_current_user_id)):
    """订单完整详情：双方信息 + 物品信息 + 状态时间线 + 消息记录。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT o.*,
                          i.title AS item_title, i.images AS item_images, i.status AS item_status,
                          i.exchange_mode AS item_exchange_mode,
                          b.nickname AS buyer_nickname, b.avatar AS buyer_avatar,
                          s.nickname AS seller_nickname, s.avatar AS seller_avatar
                   FROM `order` o
                   LEFT JOIN item i ON i.id = o.item_id
                   LEFT JOIN user b ON b.id = o.buyer_id
                   LEFT JOIN user s ON s.id = o.seller_id
                   WHERE o.id=%s LIMIT 1""",
                (order_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(404, "订单不存在")

            buyer_id = int(row.get("buyer_id") or 0)
            seller_id = int(row.get("seller_id") or 0)
            if user_id not in (buyer_id, seller_id):
                raise HTTPException(403, "无权查看该订单")

            # 消息记录：该物品下买卖双方之间的私信（与「消息记录」需求对应）。
            # 先按 id 倒序取最新 MESSAGE_PREVIEW_LIMIT 条，再反转为升序展示，
            # 长会话不会把响应撑爆。sender_nickname 用 LEFT JOIN 兜底。
            cursor.execute(
                """SELECT pm.id, pm.sender_id, pm.content, pm.created_at,
                          u.nickname AS sender_nickname
                   FROM private_message pm
                   LEFT JOIN user u ON u.id = pm.sender_id
                   WHERE pm.item_id=%s
                     AND ((pm.sender_id=%s AND pm.receiver_id=%s)
                       OR (pm.sender_id=%s AND pm.receiver_id=%s))
                   ORDER BY pm.id DESC LIMIT %s""",
                (
                    row.get("item_id"),
                    buyer_id,
                    seller_id,
                    seller_id,
                    buyer_id,
                    MESSAGE_PREVIEW_LIMIT,
                ),
            )
            messages = list(reversed(cursor.fetchall()))

    status = int(row.get("status") or STATUS_PENDING)
    raw_title = row.get("item_title")
    item_missing = not raw_title
    images = _parse_images(row.get("item_images"))
    try:
        item_status = int(row.get("item_status") or 0)
    except (TypeError, ValueError):
        item_status = 0
    try:
        item_exchange_mode = row.get("item_exchange_mode")
        item_exchange_mode = int(item_exchange_mode) if item_exchange_mode is not None else None
    except (TypeError, ValueError):
        item_exchange_mode = None

    detail = OrderDetail(
        order_id=int(row.get("id") or 0),
        order_no=str(row.get("order_no") or ""),
        status=status,
        status_label=_status_label(status),
        viewer_role=_viewer_role(buyer_id, seller_id, user_id),
        # 交易方式与成交金额：仅「购买」（低价转让）单有金额，其余为 0
        exchange_type=_to_optional_int(row.get("exchange_type")),
        price=_to_float_price(row.get("price")),
        created_at=row.get("created_at"),
        completed_at=row.get("completed_at"),
        buyer=OrderParty(
            id=buyer_id or None,
            nickname=_nickname_or_fallback(row.get("buyer_nickname"), buyer_id),
            avatar=row.get("buyer_avatar"),
        ),
        seller=OrderParty(
            id=seller_id or None,
            nickname=_nickname_or_fallback(row.get("seller_nickname"), seller_id),
            avatar=row.get("seller_avatar"),
        ),
        item=None
        if item_missing
        else OrderItemBrief(
            id=int(row.get("item_id") or 0),
            title=str(raw_title),
            cover=images[0] if images else None,
            status=item_status,
            status_label=ITEM_STATUS_LABEL.get(item_status, "未知状态"),
            exchange_mode=item_exchange_mode,
        ),
        timeline=_build_timeline(status, row.get("created_at"), row.get("completed_at")),
        messages=[
            OrderMessageBrief(
                id=int(msg.get("id") or 0),
                sender_id=int(msg.get("sender_id") or 0),
                sender_nickname=_nickname_or_fallback(
                    msg.get("sender_nickname"), msg.get("sender_id")
                ),
                content=str(msg.get("content") or ""),
                created_at=msg.get("created_at"),
            )
            for msg in messages
        ],
    )
    return success(detail.model_dump(mode="json"))


# ============================================================
# 卖家确认交换（1 -> 2）
# ============================================================
@router.put("/{order_id}/confirm")
def confirm_order(order_id: int, user_id: int = Depends(get_current_user_id)):
    """仅物品发布者（卖家）可确认；状态 1 待确认 → 2 交换中。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            order = _load_order_for_action(cursor, order_id, user_id)
            seller_id = int(order.get("seller_id") or 0)
            if user_id != seller_id:
                raise HTTPException(403, "只有物品发布者可以确认交换")
            if int(order.get("status") or 0) != STATUS_PENDING:
                raise HTTPException(400, "只有待确认的订单可以确认交换")

            # 条件更新：并发下只有一个请求能改成功
            cursor.execute(
                "UPDATE `order` SET status=%s WHERE id=%s AND status=%s",
                (STATUS_ONGOING, order_id, STATUS_PENDING),
            )
            if cursor.rowcount == 0:
                raise HTTPException(400, "订单状态已变更，请刷新后重试")

    return success(
        {
            "order_id": order_id,
            "status": STATUS_ONGOING,
            "status_label": _status_label(STATUS_ONGOING),
        },
        "已确认交换，请及时完成交接",
    )


# ============================================================
# 确认完成交换（2 -> 3）
# ============================================================
@router.put("/{order_id}/complete")
def complete_order(order_id: int, user_id: int = Depends(get_current_user_id)):
    """买卖双方任一方可确认完成；状态 2 交换中 → 3 已完成。

    同一事务内完成三件事，任一失败整体回滚：
    ① 订单置为已完成并写 completed_at；
    ② 物品置为「已下架」（决策 D：否则其他邻居仍能对该物品发起交换）；
    ③ 双方各发一次交换奖励 + 累加交换次数 / 碳减排量（与 admin 共用
       `order_service.reward_exchange_completion`）。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            order = _load_order_for_action(cursor, order_id, user_id)
            if int(order.get("status") or 0) != STATUS_ONGOING:
                raise HTTPException(400, "只有交换中的订单可以完成")

            # ① 条件更新：`AND status=2` 是并发防重的关键——
            # rowcount 为 0 说明状态已被另一方改掉，直接 400，绝不二次发奖。
            cursor.execute(
                "UPDATE `order` SET status=%s, completed_at=NOW() WHERE id=%s AND status=%s",
                (STATUS_DONE, order_id, STATUS_ONGOING),
            )
            if cursor.rowcount == 0:
                raise HTTPException(400, "订单状态已变更，请刷新后重试")

            # ② 物品下架（放到「已交换」语义的 status=2）。
            # 带 `AND status=1` 的条件更新：只改「在售」的物品，
            # 不会覆盖卖家已做的下架动作或管理端的审核结果。
            cursor.execute(
                "UPDATE item SET status=%s WHERE id=%s AND status=%s",
                (ITEM_STATUS_OFF_SHELF, order.get("item_id"), ITEM_STATUS_ON_SALE),
            )

            # ③ 发奖 + 统计（与订单状态同事务；幂等由上面的条件更新 +
            #    points_log 唯一索引双重保证）
            reward, carbon_delta = reward_exchange_completion(
                cursor,
                order_id,
                {"buyer_id": order.get("buyer_id"), "seller_id": order.get("seller_id")},
            )

    return success(
        {
            "order_id": order_id,
            "status": STATUS_DONE,
            "status_label": _status_label(STATUS_DONE),
            "points_awarded": reward,
            "carbon_added": carbon_delta,
        },
        f"交换已完成，双方各获得 {reward} 积分，减碳 {carbon_delta} kg",
    )


# ============================================================
# 取消订单（1 / 2 -> 4）
# ============================================================
@router.put("/{order_id}/cancel")
def cancel_order(order_id: int, user_id: int = Depends(get_current_user_id)):
    """买卖双方任一方可取消；待确认 / 交换中 → 已取消。

    卖家在「待确认」阶段点此接口即等价于「拒绝该交换请求」——
    复用同一状态流转与接口，不新增接口、不新增状态。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            order = _load_order_for_action(cursor, order_id, user_id)
            if int(order.get("status") or 0) not in (STATUS_PENDING, STATUS_ONGOING):
                raise HTTPException(400, "该订单已结束，无法取消")

            cursor.execute(
                "UPDATE `order` SET status=%s WHERE id=%s AND status IN (%s,%s)",
                (STATUS_CANCELLED, order_id, STATUS_PENDING, STATUS_ONGOING),
            )
            if cursor.rowcount == 0:
                raise HTTPException(400, "订单状态已变更，请刷新后重试")

    return success(
        {
            "order_id": order_id,
            "status": STATUS_CANCELLED,
            "status_label": _status_label(STATUS_CANCELLED),
        },
        "订单已取消",
    )
