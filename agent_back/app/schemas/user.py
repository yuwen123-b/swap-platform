"""用户档案（含助老/无障碍/语言偏好）的请求与响应模型。"""
from typing import Literal

from pydantic import BaseModel, Field

ModeLiteral = Literal["normal", "visually_impaired", "mobility_impaired"]
MobilityLiteral = Literal["free", "limited", "assisted"]
LangLiteral = Literal["zh_CN", "en_US"]


class ProfileResponse(BaseModel):
    user_id: int
    nickname: str | None = None
    elderly_mode: int = 0
    accessibility_mode: ModeLiteral = "normal"
    mobility_level: MobilityLiteral = "free"
    high_contrast: int = 0
    language: LangLiteral = "zh_CN"


class ProfileUpdate(BaseModel):
    elderly_mode: int | None = Field(default=None, ge=0, le=1)
    accessibility_mode: ModeLiteral | None = None
    mobility_level: MobilityLiteral | None = None
    high_contrast: int | None = Field(default=None, ge=0, le=1)
    language: LangLiteral | None = None
