"""个人中心扩展区（我的收藏 / 我的需求 / 我的交换）的响应模型。

与 `app/schemas/user_center.py` 分离：那三个区已定稿，本文件只放后续新增功能，
避免单文件继续膨胀。

注意：分页外壳（`{total, page, size, list}`）刻意不使用 Pydantic 模型——
Pydantic 2.x 下字段名不能叫 `list`（字段默认值会遮蔽内建 `list`，
导致 `list[FavoriteItem]` 求值报 TypeError），因此列表接口直接返回普通 dict。
"""
from datetime import datetime

from pydantic import BaseModel


class FavoriteItem(BaseModel):
    """收藏列表项：物品摘要 + 收藏时间。

    `id` 是 item.id（不是 favorite.id），前端据此跳转物品详情；
    `favorite_id` 保留下来便于将来做「取消收藏」的精确定位。
    物品被删除后 LEFT JOIN 取不到 item 字段，此时 `status_label` 为「物品已不存在」。
    """

    id: int
    favorite_id: int
    title: str = ""
    cover: str | None = None
    status: int = 0
    status_label: str = "未知状态"
    favorited_at: datetime | None = None


# ============================================================
# 我想要的（需求）
# ============================================================
class DemandCreate(BaseModel):
    """发布需求的请求体。字段长度在接口层用中文报错校验，
    不走 Pydantic 的 max_length——全局 RequestValidationError 处理器会把
    Pydantic 的英文报错原样透出，终端用户看不懂。
    """

    title: str
    description: str | None = None
    category: str | None = None


class DemandUpdate(BaseModel):
    """编辑需求：三个字段均可选，只更新传入的字段（None 表示不修改）。"""

    title: str | None = None
    description: str | None = None
    category: str | None = None


class DemandItem(BaseModel):
    """「我的需求」列表项。"""

    id: int
    title: str = ""
    description: str | None = None
    category: str | None = None
    status: int = 1
    status_label: str = "进行中"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DemandWallItem(BaseModel):
    """公开需求墙条目。

    隐私约束：只包含**昵称**与**楼栋**，SQL 层就不 SELECT 手机号 / 联系方式，
    不依赖前端隐藏。`user_id` 是内部主键（非隐私字段），用于点进去开私信。
    `building` 为空时前端展示「社区邻居」，不渲染 null。
    """

    id: int
    user_id: int
    title: str = ""
    category: str | None = None
    nickname: str = "社区邻居"
    building: str | None = None
    created_at: datetime | None = None


# ============================================================
# 我的交换（订单）
# ============================================================
class OrderCreate(BaseModel):
    """发起交换的请求体。

    `message` 为可选留言：非空时由接口层调私信服务给卖家发一条消息，
    空 / 全空白视为不留言（不产生 private_message 记录）。
    长度在接口层用中文报错校验，不走 Pydantic 的 max_length——
    全局 RequestValidationError 处理器会把 Pydantic 的英文报错原样透出，用户看不懂。
    """

    item_id: int
    message: str | None = None


class OrderListItem(BaseModel):
    """「我的交换」列表项。

    `viewer_role` 表示**当前用户在这笔订单里的身份**（buyer / seller），
    前端据此决定展示「对方」是谁、以及给不给「确认交换」按钮。
    `other_nickname` 就是那个「对方」的昵称（按 viewer_role 取反）。
    物品被删除后 LEFT JOIN 取不到 item，此时 `item_title` 为「物品已不存在」、
    `item_image` 为 None，但 `item_id` 仍可用（order.item_id 是 NOT NULL）。

    `exchange_type` / `price`：交易方式（1=购买 2=以物换物 3=赠送）与成交金额。
    前端只用它决定「低价转让单要不要展示价格」——赠送 / 以物换物单 price 恒为 0。
    """

    order_id: int
    order_no: str = ""
    status: int = 1
    status_label: str = "待确认"
    item_id: int = 0
    item_title: str = ""
    item_image: str | None = None
    other_user_id: int | None = None
    other_nickname: str = "社区邻居"
    viewer_role: str = "buyer"
    exchange_type: int | None = None
    price: float = 0.0
    created_at: datetime | None = None
    completed_at: datetime | None = None


class OrderParty(BaseModel):
    """订单一方（买家 / 卖家）的公开信息。

    只含 id / 昵称 / 头像，**不含手机号、邮箱、联系方式**——
    双方虽已存在交易关系，仍不在订单接口里扩散联系方式（要联系走私信）。
    """

    id: int | None = None
    nickname: str = "社区邻居"
    avatar: str | None = None


class OrderItemBrief(BaseModel):
    """订单详情里的物品摘要。`item` 为 None 表示物品已被删除。"""

    id: int
    title: str = ""
    cover: str | None = None
    status: int = 0
    status_label: str = "未知状态"
    exchange_mode: int | None = None


class OrderTimelineNode(BaseModel):
    """状态时间线节点。

    `order` 表**没有状态历史表**，节点由「当前 status + created_at + completed_at」
    推导而来；`at` 为 None 表示库中不存在该节点的真实时间戳
    （例如「交换中」是中间态，没有单独记录发生时点），前端展示为「—」。
    """

    status: int
    status_label: str
    at: datetime | None = None


class OrderMessageBrief(BaseModel):
    """订单详情里的私信摘要（该物品下买卖双方之间的消息，最多 20 条）。"""

    id: int
    sender_id: int
    sender_nickname: str = "社区邻居"
    content: str = ""
    created_at: datetime | None = None


class OrderDetail(BaseModel):
    """订单完整详情。

    `exchange_type` / `price` 与列表项同口径：只有「购买」（item.exchange_mode=3
    低价转让）单带金额，赠送 / 以物换物单 `price` 恒为 0。
    """

    order_id: int
    order_no: str = ""
    status: int = 1
    status_label: str = "待确认"
    viewer_role: str = "buyer"
    exchange_type: int | None = None
    price: float = 0.0
    created_at: datetime | None = None
    completed_at: datetime | None = None
    buyer: OrderParty
    seller: OrderParty
    item: OrderItemBrief | None = None
    timeline: list[OrderTimelineNode] = []
    messages: list[OrderMessageBrief] = []
