"""用户档案（含助老/无障碍/语言偏好/账户安全/通知设置/意见反馈）的请求与响应模型。

约定：Pydantic 只做「字段存在性 + 宽松上限」的兜底，**业务规则校验一律放在接口函数体内**
（用中文 raise HTTPException），因为全局 RequestValidationError 处理器会把 Pydantic
的校验错误原样转成英文技术串返回给前端，用户无法理解。
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ModeLiteral = Literal["normal", "visually_impaired", "mobility_impaired"]
MobilityLiteral = Literal["free", "limited", "assisted"]
LangLiteral = Literal["zh_CN", "en_US"]

# 昵称长度限制：与前端 maxlength 保持一致
NICKNAME_MAX_LEN = 20
# 地址/社区/楼栋：与前端输入框上限保持一致
ADDRESS_MAX_LEN = 64
# 验证码为 6 位数字（发码逻辑见 app/services/code_service.py）
CODE_LEN = 6


class ProfileResponse(BaseModel):
    user_id: int
    nickname: str | None = None
    # 头像 URL（带签名，见 core.security.sign_file_path）
    avatar: str | None = None
    # 注册时间：前端据此计算「已加入社区 N 天」
    created_at: datetime | None = None
    # 账户积分余额（第一区卡片展示；等级按此字段计算）
    points: int = 0
    # 碳减排量汇总（kgCO2e，第四区概览展示）
    carbon_total: float = 0
    # 所在社区名称（user 表内已有该列，无需 JOIN）
    community: str | None = None
    # 楼栋信息（位置管理页展示 / 手动输入地址时写入）
    building: str | None = None
    # 位置是否公开：0 不公开（默认）1 公开。与位置是否存在解耦，
    # 关闭时他人「附近搜索」看不到本人物品，但本人自己的「离我最近」不受影响。
    location_public: int = 0
    # 当前位置坐标（0 表示未设置）；是否公开由 location_public 独立控制
    latitude: float = 0
    longitude: float = 0
    elderly_mode: int = 0
    accessibility_mode: ModeLiteral = "normal"
    mobility_level: MobilityLiteral = "free"
    high_contrast: int = 0
    language: LangLiteral = "zh_CN"


class ProfileUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=NICKNAME_MAX_LEN)
    elderly_mode: int | None = Field(default=None, ge=0, le=1)
    accessibility_mode: ModeLiteral | None = None
    mobility_level: MobilityLiteral | None = None
    high_contrast: int | None = Field(default=None, ge=0, le=1)
    language: LangLiteral | None = None
    location_public: int | None = Field(default=None, ge=0, le=1)
    # 允许清空位置：传 null 表示清除坐标（接口用 exclude_unset 保留显式 null）
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    # 地址信息：位置管理页「手动输入地址」经地理编码后写入
    community: str | None = Field(default=None, max_length=ADDRESS_MAX_LEN)
    building: str | None = Field(default=None, max_length=ADDRESS_MAX_LEN)


# ========== 账户安全 ==========
# 注意：密码规则（8-32 位且同时含字母与数字）在接口函数体内校验，
# 这里仅做「必填 + 宽松上限」兜底，避免英文报错串直出前端。
class PasswordUpdate(BaseModel):
    old_password: str = Field(max_length=64)
    new_password: str = Field(max_length=64)


class PhoneSendCodeRequest(BaseModel):
    new_phone: str = Field(max_length=32)


class PhoneBindRequest(BaseModel):
    new_phone: str = Field(max_length=32)
    code: str = Field(max_length=16)


class EmailSendCodeRequest(BaseModel):
    new_email: str = Field(max_length=128)


class EmailBindRequest(BaseModel):
    new_email: str = Field(max_length=128)
    code: str = Field(max_length=16)


# ========== 通知设置 ==========
class NotificationUpdate(BaseModel):
    notify_message: int | None = Field(default=None, ge=0, le=1)
    notify_exchange: int | None = Field(default=None, ge=0, le=1)
    notify_system: int | None = Field(default=None, ge=0, le=1)


# ========== 意见反馈（写入 user_feedback 表） ==========
class UserFeedbackCreate(BaseModel):
    content: str = Field(max_length=1000)
    contact: str | None = Field(default=None, max_length=200)


# ========== 地址解析（高德地理编码） ==========
class AddressSearchRequest(BaseModel):
    address: str = Field(max_length=120)
