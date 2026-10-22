"""个人中心第二 / 三 / 四区的响应模型。

本轮 5 个接口全部没有请求体（GET + 一个无 body 的 PUT），因此这里只定义响应模型。
字段与前端 `src/views/profile/ItemsView.vue` / `CarbonView.vue` 一一对应。

注意：分页外壳（`{total, page, size, list}`）刻意不使用 Pydantic 模型——
Pydantic 2.x 下字段名不能叫 `list`（字段默认值会遮蔽内建 `list`，
导致 `list[ItemBrief]` 求值报 TypeError），因此列表接口直接返回普通 dict。
"""
from datetime import datetime

from pydantic import BaseModel

from app.core.constants import ITEM_STATUS_LABEL


class ItemBrief(BaseModel):
    """我的物品列表项。"""

    id: int
    title: str = ""
    # 封面取 item.images（JSON 字符串）里的第一张；无图或解析失败时为 None
    cover: str | None = None
    status: int = 4
    status_label: str = ITEM_STATUS_LABEL[4]
    created_at: datetime | None = None


class CarbonSummary(BaseModel):
    """第四区汇总卡 + 进度条。

    total_points 取 user.points（账户余额）；
    carbon_total 为碳减排量（kgCO2e），与积分是两套口径，不可互相换算。
    """

    total_points: int = 0
    carbon_total: float = 0
    exchange_count: int = 0
    level: int = 1
    level_label: str = "LV1"
    next_level: str | None = None
    next_level_gap: int = 0
    progress_percent: int = 0


class PointsLogEntry(BaseModel):
    """积分明细项。"""

    id: int
    # 变动值：正数为获得，负数为消耗
    points: int = 0
    # 变动后余额快照，与 user.points 一致
    balance: int = 0
    source: int = 0
    source_label: str = "其他"
    related_id: int | None = None
    description: str | None = None
    created_at: datetime | None = None


class CarbonRankInfo(BaseModel):
    """社区碳积分排名。

    community 为空时不参与排名，rank 返回 None，前端据此提示「未设置所在社区」。
    """

    rank: int | None = None
    total: int = 0
    community: str | None = None
