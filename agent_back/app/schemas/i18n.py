"""国际化接口的请求/响应模型。"""
from pydantic import BaseModel, Field


class SetLanguageRequest(BaseModel):
    user_id: int
    language: str = Field(..., description="zh_CN / en_US")


class SetLanguageResponse(BaseModel):
    success: bool
    language: str


class TranslateRequest(BaseModel):
    text: str
    source_lang: str = "zh_CN"
    target_lang: str = "en_US"


class TranslateResponse(BaseModel):
    translated_text: str
    confidence: float
    note: str = ""
