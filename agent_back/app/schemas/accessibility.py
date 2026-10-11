"""无障碍模式与志愿者任务的请求/响应模型。"""
from pydantic import BaseModel, Field


class SetModeRequest(BaseModel):
    user_id: int
    mode: str = Field(..., description="normal / visually_impaired / mobility_impaired")


class SetMobilityRequest(BaseModel):
    user_id: int
    mobility_level: str = Field(..., description="free / limited / assisted")


class UiConfig(BaseModel):
    mode: str
    voice_navigation: bool
    high_contrast: bool
    skip_self_pickup: bool
    volunteer_entry: bool


class SetModeResponse(BaseModel):
    success: bool
    ui_config: UiConfig


class HandoverOptions(BaseModel):
    mobility_level: str
    methods: list[str]
    recommended: str


class VoiceLabelResponse(BaseModel):
    item_id: int
    label: str


class VolunteerTaskCreate(BaseModel):
    exchange_id: str
    requester_id: int
    item_id: int | None = None
    volunteer_id: int | None = None
    handover_method: str = "volunteer_pickup"
    note: str = ""


class VolunteerTaskResponse(BaseModel):
    task_id: int
    status: str


class VolunteerTaskUpdate(BaseModel):
    volunteer_id: int
    status: str = Field(..., description="accepted / done / cancelled")
