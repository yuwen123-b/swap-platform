"""积分规则读取与积分流水写入。

【事务约定 — 非常重要】
本模块所有函数都接收调用方传入的 `cursor`，**绝不自己开事务 / 不自己取连接**。
调用方负责把「业务写入 + 积分发放」放进同一个 `with connection() as conn` 里，
这样任一环节抛错都能整体回滚，不会出现「状态改了、分没发」或「分发了、余额没更新」。

【balance 口径】
`points_log.balance` 必须等于变动后的 `user.points`。
实现上用 `UPDATE ... points=points+%s` 后**回读**，而不是「先读再加再写」：
并发加分时回读拿到的才是数据库的权威余额，避免丢失更新。
回读必须发生在 UPDATE 之后、INSERT points_log 之前。

【规则来源】
奖励数值一律从 `sys_config` 读取（键名与 admin/points.py 的 RULE_KEYS 对齐），
不硬编码在业务代码里。DB 中缺键或值非法时回落到常量默认值，保证首次部署即可用。

【失败语义】
`award_points` 不吞异常：
- 命中 `points_log` 的唯一索引（同一笔业务重复发放）→ 抛 `PointsAwardError`，
  由调用方事务回滚，全局异常处理器转成 409 + 明确提示；
- 其它数据库错误（连接断开、列缺失等）→ 原样抛出，走 500，不伪装成业务冲突。
"""
import logging

import pymysql

from app.core.constants import POINTS_SOURCE_LABEL, level_progress

logger = logging.getLogger(__name__)

# pymysql 唯一键冲突的 errno（ER_DUP_ENTRY）
_ER_DUP_ENTRY = 1062


class PointsAwardError(RuntimeError):
    """积分流水写入失败（可预期的业务冲突）。

    目前唯一触发场景：命中 points_log 的唯一索引
    `uk_points_log_source(source, related_id, user_id)`——即同一笔业务
    （同一 source + 同一 related_id）已经给同一用户发过分。

    这类重复必须让调用方的事务整体回滚：否则会留下「余额加了、流水没记」的脏账。
    刻意与「数据库不可用」等基础设施错误区分，后者原样抛出（500），不误报成 409。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

# ========== sys_config 键名 ==========
RULE_POINTS_PUBLISH = "points_publish"
RULE_POINTS_EXCHANGE = "points_exchange"
RULE_CARBON_PER_EXCHANGE = "carbon_per_exchange"

# ========== 兜底默认值（DB 有值时以 DB 为准） ==========
# 发布奖励 20 分：发布 5 件即可到 LV2（101 分），比 10 分更符合社区活跃度预期
DEFAULT_POINTS_PUBLISH = 20
# 完成交换奖励 50 分：交换是本平台的核心行为，给足激励
DEFAULT_POINTS_EXCHANGE = 50
# 每次完成交换折算的碳减排量（kgCO2e）
DEFAULT_CARBON_PER_EXCHANGE = 5.0

# ========== points_log.source ==========
SOURCE_PUBLISH = 1
SOURCE_EXCHANGE = 2
SOURCE_ADMIN = 4
# 5 = 兑换消耗（商家端：用户用积分兑换商家服务/商品）
SOURCE_REDEEM = 5
# 7 = 兑换过期退还（兑换单超期未核销，原额退回消耗的积分）
# 与 SOURCE_REDEEM 用不同 source，因此同一笔兑换单可以同时存在
# 「消耗」与「退还」两条流水，不会撞 uk_points_log_source 唯一索引。
SOURCE_REDEEM_REFUND = 7
# 8 = 平台回收所得（用户发布物品选「交给平台回收」，按成色估价立即发分）
SOURCE_RECYCLE = 8
# 9 = 平台回收取消退还（取件前取消，原额退回发放的积分）。
# 与 SOURCE_REDEEM / SOURCE_REDEEM_REFUND 完全同一个套路：发放与退还**必须用不同
# source**，否则同一笔回收单写第二条流水必撞 uk_points_log_source 唯一索引
# （取消功能会 100% 失败报 409）。
SOURCE_RECYCLE_CANCEL = 9

# 说明列宽（points_log.description 为 VARCHAR(255)），写入前统一截断
_DESCRIPTION_MAX_LEN = 255


def source_label(source: int) -> str:
    """把 source 数值转成中文说明，未知值统一显示「其他」。"""
    try:
        return POINTS_SOURCE_LABEL.get(int(source), "其他")
    except (TypeError, ValueError):
        return "其他"


def _read_config_value(cursor, key: str) -> str | None:
    """读取 sys_config.config_value，任何异常都返回 None 由调用方兜底。

    这里吞掉异常是有意为之：sys_config 不可用（表缺失、权限问题）不应该让
    「审核通过」这类主流程直接 500，奖励降级为默认值继续发放更安全。
    """
    try:
        cursor.execute("SELECT config_value FROM sys_config WHERE config_key=%s LIMIT 1", (key,))
        row = cursor.fetchone()
    except Exception:  # noqa: BLE001 — 配置读取失败不应阻断主流程
        logger.warning("读取积分规则失败 key=%s，将使用默认值", key, exc_info=True)
        return None
    if not row:
        return None
    value = row.get("config_value") if isinstance(row, dict) else None
    return None if value is None else str(value).strip()


def get_int_rule(cursor, key: str, default: int) -> int:
    """读取整数型规则。

    缺失 / 非数字 / **小于等于 0** 一律回落默认值。
    0 不视为合法配置：奖励配成 0 会让发放静默失效，属典型误配；
    若确需停发奖励，应通过管理端关闭对应功能，而不是把分值配成 0。
    """
    raw = _read_config_value(cursor, key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("积分规则 %s 的值 %r 不是整数，回落默认值 %s", key, raw, default)
        return default
    if value <= 0:
        logger.warning("积分规则 %s 的值为 %s（<=0），按误配处理，回落默认值 %s", key, value, default)
        return default
    return value


def get_float_rule(cursor, key: str, default: float) -> float:
    """读取浮点型规则（如碳减排量系数），规则同 get_int_rule。"""
    raw = _read_config_value(cursor, key)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("积分规则 %s 的值 %r 不是数字，回落默认值 %s", key, raw, default)
        return default
    if value <= 0:
        logger.warning("积分规则 %s 的值为 %s（<=0），按误配处理，回落默认值 %s", key, value, default)
        return default
    return value


def award_points(
    cursor,
    user_id: int,
    points: int,
    source: int,
    related_id: int | None = None,
    description: str | None = None,
) -> int | None:
    """给用户加分/扣分并写一条积分流水，返回变动后的余额。

    - 必须在调用方的事务内执行（本函数不 commit）
    - `points` 可为负数（管理员扣分）；为 0 时不产生任何写入，返回 None
    - balance 为 UPDATE 后回读的权威余额
    - 命中 points_log 唯一索引（同一笔业务重复发放）时抛 PointsAwardError，
      让调用方的 `with connection()` 回滚整笔事务
    """
    if not points:
        return None

    cursor.execute("UPDATE user SET points=points+%s WHERE id=%s", (points, user_id))

    cursor.execute("SELECT points FROM user WHERE id=%s LIMIT 1", (user_id,))
    row = cursor.fetchone()
    balance = 0
    if row is not None:
        raw_balance = row.get("points") if isinstance(row, dict) else None
        try:
            balance = int(raw_balance or 0)
        except (TypeError, ValueError):
            balance = 0

    if description and len(description) > _DESCRIPTION_MAX_LEN:
        description = description[:_DESCRIPTION_MAX_LEN]

    try:
        cursor.execute(
            "INSERT INTO points_log (user_id, points, balance, source, related_id, description) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (user_id, points, balance, source, related_id, description),
        )
    except pymysql.err.IntegrityError as exc:
        # 只把「唯一键冲突」翻译成可读的业务提示；其余 IntegrityError（如非空约束）
        # 仍按基础设施错误抛出，避免掩盖真实的表结构问题。
        if not exc.args or exc.args[0] != _ER_DUP_ENTRY:
            raise
        raise PointsAwardError(
            f"积分发放失败：用户 {user_id} 的「{source_label(source)}」流水已存在"
            f"（source={source}, related_id={related_id}），同一笔业务不重复发放，本次已跳过"
        ) from exc
    return balance


def get_effective_rules(cursor) -> dict:
    """读取**当前生效**的积分规则（供智能体提示词注入实时数值）。

    存在的意义：DB 现值（points_publish=10 / points_exchange=20）与代码兜底默认值
    （20 / 50）并不一致，且管理端可随时改 sys_config。把数字写死进提示词，
    会导致 AI 的说法与平台实际规则矛盾；实时读取可彻底避免漂移。

    读取失败由 `get_int_rule` / `get_float_rule` 内部回落默认值，不会抛异常。
    """
    return {
        "points_publish": get_int_rule(cursor, RULE_POINTS_PUBLISH, DEFAULT_POINTS_PUBLISH),
        "points_exchange": get_int_rule(cursor, RULE_POINTS_EXCHANGE, DEFAULT_POINTS_EXCHANGE),
        "carbon_per_exchange": get_float_rule(cursor, RULE_CARBON_PER_EXCHANGE, DEFAULT_CARBON_PER_EXCHANGE),
    }


def get_points_snapshot(cursor, user_id: int) -> dict | None:
    """读取用户积分快照（供智能体工具 get_points_balance，只读）。

    返回 None 表示用户不存在。等级换算复用 `constants.level_progress`，
    与个人中心 / Profile.vue 的等级口径严格一致。

    与 `api/v1/user_center.py::carbon_summary` 的差异：这里额外给出等级与晋级进度，
    让模型能直接回答「我还差多少分」，且只返回模型需要的字段（不含手机号等）。
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None

    cursor.execute(
        "SELECT points, carbon_total, exchange_count FROM user WHERE id=%s LIMIT 1",
        (uid,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    try:
        points = int(row.get("points") or 0)
    except (TypeError, ValueError):
        points = 0
    try:
        carbon_total = float(row.get("carbon_total") or 0)
    except (TypeError, ValueError):
        carbon_total = 0.0
    try:
        exchange_count = int(row.get("exchange_count") or 0)
    except (TypeError, ValueError):
        exchange_count = 0

    return {
        "user_id": uid,
        "points": points,
        "carbon_total": round(carbon_total, 2),
        "exchange_count": exchange_count,
        **level_progress(points),
    }


def bump_exchange_stats(cursor, user_id: int, carbon_delta: float) -> None:
    """交换完成时累加「完成交换次数」与「碳减排量」。

    这两项**不写入 points_log**（该表没有对应列），只与积分发放处于同一事务。

    用 COALESCE 兜底：存量数据的 exchange_count / carbon_total 可能是 NULL，
    直接 `NULL + 1` 结果仍是 NULL，会导致统计永远为 0。
    """
    cursor.execute(
        "UPDATE user SET exchange_count=COALESCE(exchange_count, 0) + 1, "
        "carbon_total=COALESCE(carbon_total, 0) + %s WHERE id=%s",
        (carbon_delta, user_id),
    )
