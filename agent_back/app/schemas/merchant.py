"""商家端闭环的请求 / 响应模型。

沿用项目约定：
- 字段长度 / 取值范围的校验**放在接口层**用中文报错，不用 Pydantic 的
  `max_length` / `ge` —— 全局 RequestValidationError 处理器会把 Pydantic 的
  英文报错原样透出，终端用户看不懂（见 schemas/personal_center.py 的同款说明）。
- 分页外壳（`{total, page, size, list}`）刻意不用 Pydantic 模型：
  Pydantic 2.x 下字段名不能叫 `list`，列表接口直接返回普通 dict。
"""
from datetime import datetime

from pydantic import BaseModel


# ============================================================
# 商家
# ============================================================
class MerchantApplyRequest(BaseModel):
    """商家入驻申请。"""

    name: str
    category: str | None = None
    contact: str | None = None
    address: str | None = None
    description: str | None = None


class MerchantInfoUpdate(BaseModel):
    """修改店铺资料（工作台「店铺设置」页）。

    全部字段可选，**只覆盖请求里显式出现的字段**（`exclude_unset`）——
    与 `POST /apply` 重提同一个口径：商家只改联系方式时，
    不能把没重新填的分类/地址静默清空成 NULL。
    需要清空某项时显式传空串（空串 → 落库 NULL）。
    """

    name: str | None = None
    category: str | None = None
    contact: str | None = None
    address: str | None = None
    description: str | None = None
    logo_url: str | None = None


class MerchantSettlementSummary(BaseModel):
    """商家结算自查（只读）：把「本店值多少钱、平台抽多少、结了多少」算清。

    「已结算 / 待结算」统一用**应得口径**（元），与 `gross_amount` 可直接相减，
    避免一个页面里混着「佣金口径」和「应得口径」两个数导致商家看不懂。
    """

    merchant_id: int
    merchant_name: str = ""
    commission_rate: float = 0.0
    points_to_yuan: float = 0.0

    redemption_count: int = 0
    points_total: int = 0
    gross_amount: float = 0.0
    commission_amount: float = 0.0
    net_amount: float = 0.0

    settled_points: int = 0
    settled_amount: float = 0.0
    settled_commission: float = 0.0
    pending_amount: float = 0.0
    settled_count: int = 0
    last_settled_at: datetime | None = None
    period: str = ""


class MerchantInfo(BaseModel):
    """商家自身信息（含待审核/已拒绝等非公开状态）。"""

    id: int
    user_id: int | None = None
    name: str = ""
    category: str | None = None
    contact: str | None = None
    address: str | None = None
    description: str | None = None
    logo_url: str | None = None
    status: int = 0
    status_label: str = "待审核"
    commission_rate: float = 0.0
    audit_reason: str | None = None
    created_at: datetime | None = None


class MerchantBrief(BaseModel):
    """用户端可见的商家公开信息（只出 status=1 的商家）。"""

    id: int
    name: str = ""
    category: str | None = None
    address: str | None = None
    contact: str | None = None
    description: str | None = None
    logo_url: str | None = None
    product_count: int = 0


# ============================================================
# 商家商品 / 服务
# ============================================================
class MerchantProductCreate(BaseModel):
    title: str
    description: str | None = None
    image_url: str | None = None
    points_cost: int
    stock: int = 0


class MerchantProductUpdate(BaseModel):
    """改商品：所有字段可选，None / 未传表示不修改。"""

    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    points_cost: int | None = None
    stock: int | None = None


class MerchantProductItem(BaseModel):
    id: int
    merchant_id: int
    title: str = ""
    description: str | None = None
    image_url: str | None = None
    points_cost: int = 0
    stock: int = 0
    sold_count: int = 0
    status: int = 1
    status_label: str = "上架中"
    created_at: datetime | None = None


# ============================================================
# 兑换
# ============================================================
class RedeemRequest(BaseModel):
    product_id: int


class RedeemResult(BaseModel):
    """兑换成功后的凭据。`code` 是给商家看 / 商家输入的 6 位核销码。"""

    order_id: int
    order_no: str = ""
    code: str = ""
    points_cost: int = 0
    product_title: str = ""
    merchant_name: str = ""
    expires_at: datetime | None = None
    points_balance: int | None = None


class VerifyRequest(BaseModel):
    code: str


class VerifyResult(BaseModel):
    success: bool = True
    order_id: int
    order_no: str = ""
    product_title: str = ""
    points_cost: int = 0
    user_nickname: str = "社区邻居"
    redeemed_at: datetime | None = None


class RedemptionItem(BaseModel):
    """兑换单（用户侧「我的兑换记录」/ 商家侧核销列表共用）。"""

    id: int
    order_no: str = ""
    status: int = 1
    status_label: str = "待核销"
    code: str = ""
    points_cost: int = 0
    product_id: int = 0
    product_title: str = ""
    merchant_id: int = 0
    merchant_name: str = ""
    user_id: int = 0
    user_nickname: str = ""
    expires_at: datetime | None = None
    redeemed_at: datetime | None = None
    created_at: datetime | None = None


# ============================================================
# 平台管理端
# ============================================================
class AuditRequest(BaseModel):
    """审核商家。`reason` 在拒绝时写入 merchant.audit_reason，商家可见。"""

    approved: bool
    reason: str | None = None


class SettleRequest(BaseModel):
    """手动触发结算：`merchant_id` 为空表示结算全部已通过审核的商家。"""

    merchant_id: int | None = None
    period: str | None = None
