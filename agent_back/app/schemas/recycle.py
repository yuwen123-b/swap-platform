"""平台回收二期的请求模型。

沿用项目约定：
- 字段长度 / 取值范围的校验**放在接口层**用中文报错，不用 Pydantic 的
  `max_length` / `ge` —— 全局 RequestValidationError 处理器会把 Pydantic 的
  英文报错原样透出，终端用户看不懂（见 schemas/merchant.py 的同款说明）。
- 估价**不由前端传入**：`accept_points` 一律由服务端按成色从
  `RECYCLE_ESTIMATE_POINTS` 常量表计算（否则用户可伪造 500 分）。
"""
from pydantic import BaseModel


class RecycleSubmitRequest(BaseModel):
    """用户提交平台回收。"""

    pickup_method: int
    pickup_address: str | None = None


class RecycleSellRequest(BaseModel):
    """运营批量把已入库物品卖给回收商。"""

    recycler_id: int
    recycle_ids: list[int]
    # 前端传 number；接口层用 Decimal(str(...)) 转换后再量化，
    # 避免 float 二进制尾数写进 DECIMAL(10,2)
    total_amount: float
