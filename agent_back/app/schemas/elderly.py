"""助老模式接口的请求/响应模型。"""
from pydantic import BaseModel, Field


class ElderlyCard(BaseModel):
    """三态卡片：ok=可以换 / no=不行 / contacted=已帮您联系。"""
    status: str = Field(..., description="ok / no / contacted")
    label: str
    item_id: int | None = None
    item_title: str | None = None


class ElderlySpeech(BaseModel):
    """前端播报参数：分句文本 + 语速 + 音色。"""
    text: str
    sentences: list[str]
    rate: float
    voice: str


class ElderlyActionResult(BaseModel):
    card: ElderlyCard | None = None
    speech: ElderlySpeech
    heard_text: str = ""
    action: dict | None = None


class ElderlyInteractResponse(BaseModel):
    intent: str
    # 意图实体（如 keyword=老人想找的物品名），供前端/上层业务扩展使用
    entities: dict = Field(default_factory=dict)
    response_text: str
    response_audio_url: str = ""
    action_result: ElderlyActionResult


class CallHelpRequest(BaseModel):
    user_id: int
    context: str = ""
