"""3D 物品模型接口的请求 / 响应模型。"""
from pydantic import BaseModel


class ModelGenerateRequest(BaseModel):
    """触发生成 3D 模型的请求体。"""

    item_id: int


class ModelStatus(BaseModel):
    """3D 模型状态（GET /model/{item_id} 的 data）。

    `model_url` 只在 ready 时非空，且是**带 HMAC 签名的**相对地址
    （/api/v1/static/items/{id}/models/model.glb?exp=&sig=），1 小时有效。
    """

    item_id: int
    model_status: str = "none"  # none / generating / ready / failed
    model_url: str | None = None
