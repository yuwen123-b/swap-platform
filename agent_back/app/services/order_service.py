"""交换订单的共享业务逻辑。

`reward_exchange_completion` 原为 `app/routers/admin/order.py` 的模块级私有函数，
本轮**纯上移**到本模块，供两处共用：
- 管理端 `PUT /api/admin/orders/{id}/status`（管理员改状态）
- 用户侧 `PUT /api/orders/{id}/complete`（买卖任一方确认完成）

一份发奖逻辑由两处调用，避免「同一规则两套实现」随时间漂移
（历史教训：审核发奖曾在 admin/item.py 与其它路径各写一遍）。
上移前后逻辑**逐行一致**，唯一变化是返回值由 None 改为 (reward, carbon_delta)：
用户侧接口需要它组装「+50 分 / 减碳 5.0kg」提示；管理端忽略返回值，行为不变。

【事务约定 — 与 points_service 完全一致】
本模块所有函数都接收调用方传入的 `cursor`，**绝不自己开事务 / 不自己取连接**。
调用方负责把「业务写入（订单状态 + 物品下架） + 积分发放」放进同一个
`with connection() as conn` 里，任一环节抛错整体回滚，
不会出现「状态已改、分没发」或「分发了、余额没更新」。
"""
import logging
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.services.points_service import (
    DEFAULT_CARBON_PER_EXCHANGE,
    DEFAULT_POINTS_EXCHANGE,
    RULE_CARBON_PER_EXCHANGE,
    RULE_POINTS_EXCHANGE,
    SOURCE_EXCHANGE,
    award_points,
    bump_exchange_stats,
    get_float_rule,
    get_int_rule,
)

logger = logging.getLogger(__name__)

# 订单号形态：SW + yyyyMMddHHmmss + 4 位随机数字 = 20 字符
# （`order`.order_no 为 VARCHAR(32) NOT NULL + uk_order_no 唯一索引，余量充足）
ORDER_NO_PREFIX = "SW"
ORDER_NO_RANDOM_DIGITS = 4

# ============================================================
# 交易方式 / 金额（与 app/api/v1/order.py 的 EXCHANGE_TYPE_BY_MODE 同源口径）
# ============================================================
# `order.exchange_type`：1=购买 2=以物换物 3=赠送（真实库列注释口径，不翻转）
EXCHANGE_TYPE_PURCHASE = 1
EXCHANGE_TYPE_BARTER = 2
EXCHANGE_TYPE_GIVE = 3

# `order.price` 为 DECIMAL(10,2)：统一量化到 2 位小数，避免浮点尾数写库
PRICE_QUANT = Decimal("0.01")


def resolve_order_price(exchange_type: int, item_price) -> Decimal:
    """由「交易方式 + 物品转让价」推导订单成交金额。

    只有**购买**（`exchange_type=1`，即 item.exchange_mode=3 低价转让）才带金额；
    赠送 / 以物换物一律 `Decimal('0.00')`——「赠送不带金额」是产品口径，
    也让 INSERT 列清单在非购买单上与历史完全一致（不新增列、不动既有行为）。

    `item_price` 直接来自 `item.price`（DB Decimal 或字符串），
    非法值不抛错而是归零：物品侧已有校验，这里只做「写进 order 前」的最后兜底，
    不让一条脏数据把整笔下单打挂。
    """
    if int(exchange_type or 0) != EXCHANGE_TYPE_PURCHASE:
        return Decimal("0.00")
    try:
        value = Decimal(str(item_price)) if item_price not in (None, "") else Decimal("0.00")
    except (InvalidOperation, TypeError, ValueError):
        logger.warning("item.price 无法解析为金额（%r），订单成交金额按 0 处理", item_price)
        return Decimal("0.00")
    if value <= 0:
        return Decimal("0.00")
    return value.quantize(PRICE_QUANT)


def generate_order_no(now: datetime | None = None) -> str:
    """生成订单号：SW + yyyyMMddHHmmss + 4 位随机数字。

    随机位用 secrets 而非 random：`uk_order_no` 唯一索引是硬约束，
    secrets 取值不可预测、分布均匀，配合调用方的「撞键重试」即可杜绝重复。
    时间戳显式接受 `now`（不传取当前时间），便于测试固定取值。
    """
    stamp = (now or datetime.now()).strftime("%Y%m%d%H%M%S")
    suffix = secrets.randbelow(10 ** ORDER_NO_RANDOM_DIGITS)
    return f"{ORDER_NO_PREFIX}{stamp}{suffix:0{ORDER_NO_RANDOM_DIGITS}d}"


def reward_exchange_completion(cursor, order_id: int, order: dict) -> tuple[int, float]:
    """交换首次完成：给买卖双方各发积分，并累加交换次数 / 碳减排量。

    返回 `(本次发放的积分, 本次碳减排量)`；管理端不关心返回值，忽略即可。

    与订单状态更新处于同一事务（由调用方的 `with connection()` 提供），
    任一环节抛错整体回滚，不会出现「状态已改、分没发」。

    幂等性**不在本函数内判断**，由调用方各自保证：
    - 管理端：先读旧状态，仅 `previous_status != 3` 时调用；
    - 用户侧：条件更新 `UPDATE ... WHERE id=%s AND status=2` 的 rowcount 判定；
    - 两者共同的最后一道闸是 points_log 唯一索引
      `uk_points_log_source(source, related_id, user_id)`——同一订单只可能写一次流水。
    """
    reward = get_int_rule(cursor, RULE_POINTS_EXCHANGE, DEFAULT_POINTS_EXCHANGE)
    carbon_delta = get_float_rule(cursor, RULE_CARBON_PER_EXCHANGE, DEFAULT_CARBON_PER_EXCHANGE)

    buyer_id = int(order.get("buyer_id") or 0)
    seller_id = int(order.get("seller_id") or 0)

    # 买家家与卖家为同一用户（历史脏数据 / 自换自）时只结算一次。
    # 若按双方各发，同一账号会被双倍奖励，等同于绕开规则刷分，因此这里显式去重。
    if buyer_id and buyer_id == seller_id:
        logger.warning("订单 %s 的买家与卖家为同一用户(%s)，仅发放一次交换奖励", order_id, buyer_id)
        award_points(
            cursor,
            buyer_id,
            reward,
            source=SOURCE_EXCHANGE,
            related_id=order_id,
            description="完成交换奖励",
        )
        bump_exchange_stats(cursor, buyer_id, carbon_delta)
        return reward, carbon_delta

    for uid, role in ((seller_id, "作为卖家"), (buyer_id, "作为买家")):
        if not uid:
            continue
        award_points(
            cursor,
            uid,
            reward,
            source=SOURCE_EXCHANGE,
            related_id=order_id,
            description=f"完成交换奖励（{role}）",
        )
        bump_exchange_stats(cursor, uid, carbon_delta)
    return reward, carbon_delta
