"""个人中心 / 碳积分共用的领域常量。

等级阈值与前端 `agent_front/src/views/Profile.vue` 的 `LEVELS` / `LEVEL_PROGRESS`
数值严格一致。两处刻意不共享代码（前端无法在构建期依赖后端），只对齐数值：
若调整阈值，必须同时改这两处。

约定：积分取值口径统一为 `user.points`（账户余额），`user.carbon_total` 只表示碳减排量。
"""

# ============================================================
# 等级规则：基于 user.points
# 0-100 LV1 / 101-500 LV2 / 501-1000 LV3 / 1000+ LV4
# 按「最低积分」从高到低排列，便于取第一个满足条件的等级
# ============================================================
LEVELS = (
    (1000, 4, "LV4"),
    (501, 3, "LV3"),
    (101, 2, "LV2"),
    (0, 1, "LV1"),
)

# 当前等级 -> (区间起点, 晋级所需积分, 下一等级名)
# 区间语义为「起点（含）到终点（不含）」，终点即下一等级的起始分。
# LV4 已达顶，不在表中。
LEVEL_PROGRESS = {
    1: (0, 101, "LV2"),
    2: (101, 501, "LV3"),
    3: (501, 1000, "LV4"),
}

# ============================================================
# item.status 语义
# 1=在售（管理端审核通过写入）
# 2=已下架（用户主动下架写入）
# 3=审核未通过（管理端审核拒绝写入，携带 reject_reason）
# 4=待审核（发布时默认写入）
# 注意：2 与 3 语义不同，不可混用——否则管理端「已拒绝」列表会混入主动下架品。
# ============================================================
ITEM_STATUS_LABEL = {
    1: "在售",
    2: "已下架",
    3: "审核未通过",
    4: "审核中",
}

# ============================================================
# `order`.status 语义（用户侧「我的交换」与管理端订单列表共用同一套标签）
# 1 待确认 --卖家确认--> 2 交换中 --买卖任一方--> 3 已完成
# 1/2 --买卖任一方--> 4 已取消
# 5 争议中：仅管理端可写，用户侧只读展示，不提供流转入口
# 注意：与真实库 `order`.status 的**列注释**（1=待联系 2=已约定 5=申诉中）措辞不同——
# 列注释是建表时留下的旧文案，改注释需要 MODIFY 重建表；应用层一律以本表为准。
# ============================================================
ORDER_STATUS_LABEL = {
    1: "待确认",
    2: "交换中",
    3: "已完成",
    4: "已取消",
    5: "争议中",
}


# ============================================================
# points_log.source 语义，与 sql/points_log.sql 的列注释保持一致
# ============================================================
POINTS_SOURCE_LABEL = {
    1: "发布物品",
    2: "完成交换",
    3: "收到好评",
    4: "管理员调整",
    5: "兑换消耗",
    6: "免费送出奖励",
    # 7 = 兑换过期退还：兑换单超期未核销时把消耗的积分原额退回。
    # 与 5（兑换消耗）用不同 source，因此不会撞 points_log 的
    # uk_points_log_source(source, related_id, user_id) 唯一索引——
    # 同一笔兑换单可以同时存在一条消耗流水和一条退还流水。
    7: "兑换过期退还",
    # 8 = 平台回收所得：用户发布物品选「交给平台回收」，平台按成色估价、
    # 提交时立即发放（related_id = platform_recycle.id）。
    8: "平台回收所得",
    # 9 = 平台回收取消退还：用户在取件前取消回收，把发放的积分原额退回。
    # 与 8 用不同 source —— 与 5/7 的关系完全同一个套路：
    # 同一笔回收单允许同时存在一条发放流水和一条退还流水，
    # 不同 source 才不会撞 uk_points_log_source 唯一索引。
    9: "平台回收取消退还",
}


# ============================================================
# 商家端闭环状态标签
# ============================================================
# merchant.status
MERCHANT_STATUS_LABEL = {
    0: "待审核",
    1: "已通过",
    2: "已拒绝",
    3: "已停业",
}

# merchant_product.status
MERCHANT_PRODUCT_STATUS_LABEL = {
    0: "已下架",
    1: "上架中",
}

# redemption_order.status
REDEMPTION_STATUS_LABEL = {
    1: "待核销",
    2: "已核销",
    3: "已过期",
    4: "已取消",
}

# merchant_settlement.status
SETTLEMENT_STATUS_LABEL = {
    0: "待结算",
    1: "已结算",
}


# ============================================================
# 平台回收（二期）状态标签
# ============================================================
# platform_recycle.status（单向流转：1 → 2 → 3；任何状态可流转到 4 仅限用户取消，且只允许 1 → 4）
RECYCLE_STATUS_LABEL = {
    1: "待取件",
    2: "已入库",
    3: "已售出",
    4: "已取消",
}

# item.recycle_status（与 platform_recycle.status 同序同步；0 = 不参与回收）
RECYCLE_ITEM_STATUS_LABEL = {
    0: "不参与",
    1: "待取件",
    2: "已入库",
    3: "已售出",
    4: "已取消",
}

# platform_recycle.pickup_method
PICKUP_METHOD_LABEL = {
    1: "送到回收点",
    2: "上门取件",
}

# 估价常量表：成色等级（item.condition_level）→ 平台回收估价（积分）。
# **服务端唯一的估价真源**：前端只调 GET /recycle/estimate 展示，绝不把公式抄一份到 JS
# —— 用户看到多少、实际到账就是多少。结果恒被 clamp 到 [MIN, MAX]。
RECYCLE_ESTIMATE_POINTS = {0: 10, 1: 25, 2: 60, 3: 120, 4: 220, 5: 350}
RECYCLE_ESTIMATE_MIN = 10
RECYCLE_ESTIMATE_MAX = 500


def points_to_level(points: int) -> tuple[int, str]:
    """按积分计算等级，返回 (等级码, 展示名)。

    负数或非法值按 0 处理，最低必落在 LV1，不会越界。
    """
    try:
        value = int(points)
    except (TypeError, ValueError):
        value = 0
    for minimum, code, label in LEVELS:
        if value >= minimum:
            return code, label
    # 理论上不可达（LEVELS 含 min=0 的 LV1），保留兜底避免异常
    return 1, "LV1"


def level_progress(points: int) -> dict:
    """计算「到下一级」的进度。

    返回 dict 可直接展开进 CarbonSummary：
    level / level_label / next_level / next_level_gap / progress_percent

    - 未满级：percent = 区间内已完成比例（四舍五入取整）
    - 已满级（LV4）：next_level=None、gap=0、percent=100
    """
    try:
        value = int(points)
    except (TypeError, ValueError):
        value = 0
    value = max(value, 0)

    code, label = points_to_level(value)
    segment = LEVEL_PROGRESS.get(code)
    if not segment:
        return {
            "level": code,
            "level_label": label,
            "next_level": None,
            "next_level_gap": 0,
            "progress_percent": 100,
        }

    start, target, next_level = segment
    span = target - start
    done = min(max(value - start, 0), span)
    remaining = max(target - value, 0)
    return {
        "level": code,
        "level_label": label,
        "next_level": next_level,
        "next_level_gap": remaining,
        "progress_percent": round(done / span * 100) if span > 0 else 0,
    }
