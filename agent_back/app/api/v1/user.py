"""用户档案接口。

覆盖范围：
- 档案读写（GET/PUT /profile，user_id 一律从 JWT 解析，不接受前端传入）
- 头像上传（POST /avatar）
- 账户安全（改密码、换绑手机、换绑邮箱）
- 通知设置（GET/PUT /notifications）
- 意见反馈（POST /feedback）
- 地址解析（POST /location/search-address，高德地理编码）

约定：业务规则校验写在函数体内并用中文 raise HTTPException，不用 Pydantic 精确约束，
因为全局 RequestValidationError 处理器会把 Pydantic 报错原样转成英文技术串给前端。
"""
import logging
import re
import uuid
from pathlib import Path

import requests
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import settings
from app.core.image_check import detect_image_ext
from app.core.response import success
from app.core.security import get_current_user_id, hash_password, new_salt, sign_file_path
from app.db.pool import connection
from app.schemas.user import (
    ADDRESS_MAX_LEN,
    AddressSearchRequest,
    EmailBindRequest,
    EmailSendCodeRequest,
    NotificationUpdate,
    PasswordUpdate,
    PhoneBindRequest,
    PhoneSendCodeRequest,
    ProfileResponse,
    ProfileUpdate,
    UserFeedbackCreate,
)
from app.services.code_service import CODE_TTL, create_code, verify_code
from app.utils.email import send_email
from app.utils.sms import send_sms

logger = logging.getLogger(__name__)

router = APIRouter()

# 白名单字段 -> 数据库列，避免任意字段更新。
# 注意：avatar 刻意不在此表中，头像只能通过 /avatar 上传接口写入，
# 防止用户直接把该字段改成任意外部 URL。
_COLUMN_MAP = {
    "nickname": "nickname",
    "elderly_mode": "elderly_mode",
    "accessibility_mode": "accessibility_mode",
    "mobility_level": "mobility_level",
    "high_contrast": "high_contrast",
    "language": "preferred_lang",
    "location_public": "location_public",
    "latitude": "latitude",
    "longitude": "longitude",
    "community": "community",
    "building": "building",
}

# 查询档案时统一使用的列，保证 GET / PUT 返回结构一致
_PROFILE_COLUMNS = (
    "id, nickname, avatar, created_at, points, carbon_total, community, building, location_public, "
    "latitude, longitude, "
    "elderly_mode, accessibility_mode, mobility_level, high_contrast, preferred_lang"
)

# 头像上传限制
AVATAR_DIR_NAME = "avatars"
MAX_AVATAR_SIZE = 2 * 1024 * 1024

# ========== 账户安全常量 ==========
# 与 app/api/v1/auth.py 的 target_meta 保持一致：类型 email=1 / phone=2
_TARGET_TYPE = {"email": 1, "phone": 2}
# 换绑场景固定为 4（auth.target_meta 的 scenes 已新增 bind=4）
_SCENE_BIND = 4

PHONE_PATTERN = re.compile(r"^1\d{10}$")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_LETTER_PATTERN = re.compile(r"[A-Za-z]")
_DIGIT_PATTERN = re.compile(r"\d")
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 32

# ========== 通知设置 ==========
_NOTIFY_COLUMNS = ("notify_message", "notify_exchange", "notify_system")

# ========== 意见反馈 ==========
FEEDBACK_MAX_LEN = 500
FEEDBACK_CONTACT_MAX_LEN = 100
FEEDBACK_TABLE = "user_feedback"

# ========== 地址解析（高德 Web 服务） ==========
AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
# 楼栋：3号楼 / B座 / 12幢 / 5单元
_BUILDING_PATTERN = re.compile(
    r"([0-9]{1,4}|[A-Za-z]|[一二三四五六七八九十百]{1,3})\s*(号楼|栋|幢|座|单元|号院)"
)
# 小区名：取「XX小区 / XX花园 / XX苑 ...」片段
_COMMUNITY_PATTERN = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9]{2,20}?(?:小区|花园|花苑|家园|新村|公寓|大厦|广场|公馆|别墅|嘉园|雅居|名邸|苑|园))"
)


def _avatar_signed_url(relative_path: str | None) -> str | None:
    """把库中存储的头像相对路径转为带签名的受控 URL（**每次读取现场签**）。

    与物品封面同一口径：DB 只存相对路径，签名 1 小时有效。
    兼容三种存量形态 —— 外链原样返回；**带旧签名的 URL 剥掉旧签名后重签**
    （历史数据里可能残留已过期的 exp/sig，原样返回会直接 403）；裸相对路径补签。
    """
    if not relative_path:
        return None
    if relative_path.startswith("http://") or relative_path.startswith("https://"):
        return relative_path
    # 剥掉静态前缀与残留签名 query，归一成相对路径再重签
    rel = relative_path.split("?", 1)[0]
    prefix = f"{settings.api_prefix}/static/"
    if rel.startswith(prefix):
        rel = rel[len(prefix):]
    rel = rel.lstrip("/")
    if not rel:
        return None
    return f"{prefix}{rel}?{sign_file_path(rel)}"


def _row_to_profile(row: dict) -> ProfileResponse:
    return ProfileResponse(
        user_id=row["id"],
        nickname=row.get("nickname"),
        avatar=_avatar_signed_url(row.get("avatar")),
        created_at=row.get("created_at"),
        points=int(row.get("points") or 0),
        carbon_total=float(row.get("carbon_total") or 0),
        community=row.get("community"),
        building=row.get("building"),
        location_public=int(row.get("location_public") or 0),
        latitude=float(row.get("latitude") or 0),
        longitude=float(row.get("longitude") or 0),
        elderly_mode=int(row.get("elderly_mode") or 0),
        accessibility_mode=row.get("accessibility_mode") or "normal",
        mobility_level=row.get("mobility_level") or "free",
        high_contrast=int(row.get("high_contrast") or 0),
        language=row.get("preferred_lang") or "zh_CN",
    )


def _select_profile(cursor, user_id: int) -> dict | None:
    cursor.execute(
        f"SELECT {_PROFILE_COLUMNS} FROM user WHERE id=%s LIMIT 1",
        (user_id,),
    )
    return cursor.fetchone()


def _mask_phone(phone: str) -> str:
    """手机号脱敏：138****8888。长度不足时原样返回，避免越界切片。"""
    return f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else phone


def _mask_email(email: str) -> str:
    """邮箱脱敏：ab***@example.com。"""
    if "@" not in email:
        return email
    name, _, domain = email.partition("@")
    if len(name) <= 2:
        return f"{name[0]}***@{domain}" if name else email
    return f"{name[:2]}***@{domain}"


def _deliver_code(target: str, code: str, target_type: str) -> bool:
    """发送验证码，复用 app/utils 下的短信/邮件通道。

    通道异常时：debug 环境降级为控制台投递（不阻断流程），生产环境直接 500。
    与 auth.send_code 的降级策略保持一致。
    """
    try:
        if target_type == "email":
            send_email(target, code)
        else:
            send_sms(target, code)
    except Exception:
        if settings.debug:
            logger.warning("验证码通道发送失败，已降级为控制台投递 target=%s code=%s", target, code)
            return False
        logger.exception("验证码发送失败 target=%s target_type=%s", target, target_type)
        raise HTTPException(500, "验证码发送失败，请稍后重试")
    return True


def _notification_payload(row: dict) -> dict:
    """通知开关统一按 0/1 整数返回，缺列时默认开启（1）。"""
    return {
        col: int(row.get(col) if row.get(col) is not None else 1)
        for col in _NOTIFY_COLUMNS
    }


def _extract_building(address: str) -> str | None:
    """从地址文本中提取楼栋信息（如「3号楼」「B座」）。提取不到返回 None。"""
    match = _BUILDING_PATTERN.search(address or "")
    if not match:
        return None
    return f"{match.group(1)}{match.group(2)}"[:ADDRESS_MAX_LEN]


def _extract_community(address: str, formatted_address: str | None) -> str | None:
    """提取小区/社区名；提取不到时退化为高德返回的 formatted_address。"""
    match = _COMMUNITY_PATTERN.search(address or "")
    if match:
        return match.group(1)[:ADDRESS_MAX_LEN]
    if formatted_address:
        return formatted_address[:ADDRESS_MAX_LEN]
    return None


# ============================================================
# 档案读写（user_id 从 JWT 解析，不再从路径参数取，避免越权读改他人资料）
# ============================================================
@router.get("/profile")
def get_profile(user_id: int = Depends(get_current_user_id)):
    with connection() as conn:
        with conn.cursor() as cursor:
            row = _select_profile(cursor, user_id)
    if not row:
        raise HTTPException(404, "用户不存在")
    return success(_row_to_profile(row).model_dump())


@router.put("/profile")
def update_profile(body: ProfileUpdate, user_id: int = Depends(get_current_user_id)):
    # exclude_unset：只处理调用方显式传入的字段；显式传 null 表示清空（如清除位置坐标）。
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "没有需要更新的字段")
    # 昵称先做去空白处理，避免纯空格绕过 min_length 校验
    if "nickname" in data:
        if data["nickname"] is None:
            raise HTTPException(400, "昵称不能为空")
        data["nickname"] = str(data["nickname"]).strip()
        if not data["nickname"]:
            raise HTTPException(400, "昵称不能为空")

    sets = []
    params = []
    for field, column in _COLUMN_MAP.items():
        if field in data:
            sets.append(f"{column}=%s")
            params.append(data[field])
    params.append(user_id)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE user SET {', '.join(sets)} WHERE id=%s", params)
            if cursor.rowcount == 0:
                raise HTTPException(404, "用户不存在")
            row = _select_profile(cursor, user_id)
    return success(_row_to_profile(row).model_dump())


@router.post("/avatar")
def upload_avatar(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """上传头像：魔数校验真实类型，落盘后写入 user.avatar（**只存相对路径**）。

    DB 只存 `avatars/xxx.jpg` 相对路径，签名在读取时由 `_avatar_signed_url()`
    现场补（签名仅 1 小时有效，落库会立刻过期）；响应体里的 `avatar` 才是签名 URL。
    user_id 从登录态（JWT）获取，不接受前端传入，避免越权修改他人头像。
    """
    data = file.file.read(MAX_AVATAR_SIZE + 1)
    if len(data) > MAX_AVATAR_SIZE:
        raise HTTPException(400, "头像大小不能超过 2MB")
    if not data:
        raise HTTPException(400, "头像内容为空")

    # 以文件头魔数判定真实格式，不信任 Content-Type
    ext = detect_image_ext(data)
    if ext not in {"jpg", "png"}:
        raise HTTPException(400, "头像仅支持 jpg/png 格式")

    avatar_dir = Path(settings.upload_dir).resolve() / AVATAR_DIR_NAME
    avatar_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    (avatar_dir / filename).write_bytes(data)

    relative_path = f"{AVATAR_DIR_NAME}/{filename}"
    avatar_url = f"{settings.api_prefix}/static/{relative_path}?{sign_file_path(relative_path)}"

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE user SET avatar=%s WHERE id=%s", (relative_path, user_id))
            if cursor.rowcount == 0:
                raise HTTPException(404, "用户不存在")

    return success({"avatar": avatar_url}, "头像已更新")


# ============================================================
# 账户安全 1/3：修改密码
# ============================================================
@router.put("/password")
def change_password(body: PasswordUpdate, user_id: int = Depends(get_current_user_id)):
    """修改密码。

    哈希方式复用 core.security 的 MD5(password+salt)，同时轮换 salt（不引入新算法）。
    """
    old_password = (body.old_password or "").strip()
    new_password = (body.new_password or "").strip()

    if not old_password or not new_password:
        raise HTTPException(400, "原密码和新密码不能为空")
    if new_password == old_password:
        raise HTTPException(400, "新密码不能与原密码相同")
    if not (PASSWORD_MIN_LEN <= len(new_password) <= PASSWORD_MAX_LEN):
        raise HTTPException(400, f"新密码长度需为 {PASSWORD_MIN_LEN}-{PASSWORD_MAX_LEN} 位")
    if not (_LETTER_PATTERN.search(new_password) and _DIGIT_PATTERN.search(new_password)):
        raise HTTPException(400, "新密码需同时包含字母和数字")

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT password_md5, salt FROM user WHERE id=%s LIMIT 1", (user_id,))
            row = cursor.fetchone()
            # 统一返回「原密码错误」，不区分「用户不存在」，避免泄露账号存在性
            if not row or row.get("password_md5") != hash_password(old_password, row.get("salt") or ""):
                raise HTTPException(400, "原密码错误")
            new_salt_value = new_salt()
            cursor.execute(
                "UPDATE user SET password_md5=%s, salt=%s WHERE id=%s",
                (hash_password(new_password, new_salt_value), new_salt_value, user_id),
            )

    # 本项目 JWT 只含 sub + exp，无 token 版本号/黑名单，无法在服务端立即吊销旧 token。
    # 这里记录审计日志，并由前端强制退出登录，用户需重新登录获取新 token。
    logger.warning("用户 %s 修改密码成功；旧 JWT 在过期前仍有效，需前端强制重新登录", user_id)
    return success({"success": True}, "密码修改成功，请重新登录")


# ============================================================
# 账户安全 2/3：换绑手机
# ============================================================
@router.post("/phone/send-code")
def send_phone_bind_code(body: PhoneSendCodeRequest, user_id: int = Depends(get_current_user_id)):
    """向待换绑的新手机号发送验证码（scene=bind）。"""
    new_phone = (body.new_phone or "").strip()
    if not PHONE_PATTERN.fullmatch(new_phone):
        raise HTTPException(400, "手机号格式不正确")

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM user WHERE phone=%s AND id<>%s LIMIT 1", (new_phone, user_id))
            if cursor.fetchone():
                raise HTTPException(400, "该手机号已被使用")

    try:
        code = create_code(new_phone, _TARGET_TYPE["phone"], _SCENE_BIND)
    except ValueError as exc:
        # 60 秒内重复发送，code_service 抛 ValueError -> 转 429
        raise HTTPException(429, str(exc)) from exc

    delivered = _deliver_code(new_phone, code, "phone")
    payload = {"success": True, "expires_in": int(CODE_TTL.total_seconds()), "delivered": delivered}
    if settings.debug:
        # 开发环境降级：把验证码回传，便于无短信通道时自测（生产 debug=False 不会返回）
        payload["debug_code"] = code
    return success(payload, "验证码已发送")


@router.put("/phone")
def bind_phone(body: PhoneBindRequest, user_id: int = Depends(get_current_user_id)):
    """校验验证码后换绑手机号。"""
    new_phone = (body.new_phone or "").strip()
    code = (body.code or "").strip()
    if not PHONE_PATTERN.fullmatch(new_phone):
        raise HTTPException(400, "手机号格式不正确")
    if not verify_code(new_phone, _TARGET_TYPE["phone"], _SCENE_BIND, code):
        raise HTTPException(400, "验证码错误或已过期")

    with connection() as conn:
        with conn.cursor() as cursor:
            # 二次占用检查（防并发：发码到提交之间可能被别人占用）
            cursor.execute("SELECT id FROM user WHERE phone=%s AND id<>%s LIMIT 1", (new_phone, user_id))
            if cursor.fetchone():
                raise HTTPException(400, "该手机号已被使用")
            cursor.execute("UPDATE user SET phone=%s WHERE id=%s", (new_phone, user_id))
            if cursor.rowcount == 0:
                raise HTTPException(404, "用户不存在")
    return success({"success": True, "phone": _mask_phone(new_phone)}, "手机号已更新")


# ============================================================
# 账户安全 3/3：换绑邮箱
# ============================================================
@router.post("/email/send-code")
def send_email_bind_code(body: EmailSendCodeRequest, user_id: int = Depends(get_current_user_id)):
    """向待换绑的新邮箱发送验证码（scene=bind）。"""
    new_email = (body.new_email or "").strip()
    if not EMAIL_PATTERN.fullmatch(new_email):
        raise HTTPException(400, "邮箱格式不正确")

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM user WHERE email=%s AND id<>%s LIMIT 1", (new_email, user_id))
            if cursor.fetchone():
                raise HTTPException(400, "该邮箱已被使用")

    try:
        code = create_code(new_email, _TARGET_TYPE["email"], _SCENE_BIND)
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from exc

    delivered = _deliver_code(new_email, code, "email")
    payload = {"success": True, "expires_in": int(CODE_TTL.total_seconds()), "delivered": delivered}
    if settings.debug:
        payload["debug_code"] = code
    return success(payload, "验证码已发送")


@router.put("/email")
def bind_email(body: EmailBindRequest, user_id: int = Depends(get_current_user_id)):
    """校验验证码后换绑邮箱。"""
    new_email = (body.new_email or "").strip()
    code = (body.code or "").strip()
    if not EMAIL_PATTERN.fullmatch(new_email):
        raise HTTPException(400, "邮箱格式不正确")
    if not verify_code(new_email, _TARGET_TYPE["email"], _SCENE_BIND, code):
        raise HTTPException(400, "验证码错误或已过期")

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM user WHERE email=%s AND id<>%s LIMIT 1", (new_email, user_id))
            if cursor.fetchone():
                raise HTTPException(400, "该邮箱已被使用")
            cursor.execute("UPDATE user SET email=%s WHERE id=%s", (new_email, user_id))
            if cursor.rowcount == 0:
                raise HTTPException(404, "用户不存在")
    return success({"success": True, "email": _mask_email(new_email)}, "邮箱已更新")


# ============================================================
# 通知设置
# ============================================================
@router.get("/notifications")
def get_notifications(user_id: int = Depends(get_current_user_id)):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT notify_message, notify_exchange, notify_system FROM user WHERE id=%s LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")
    return success(_notification_payload(row))


@router.put("/notifications")
def update_notifications(body: NotificationUpdate, user_id: int = Depends(get_current_user_id)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "没有需要更新的字段")

    sets = []
    params = []
    for column in _NOTIFY_COLUMNS:
        if column in data:
            sets.append(f"{column}=%s")
            params.append(data[column])
    params.append(user_id)

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE user SET {', '.join(sets)} WHERE id=%s", params)
            if cursor.rowcount == 0:
                raise HTTPException(404, "用户不存在")
            cursor.execute(
                "SELECT notify_message, notify_exchange, notify_system FROM user WHERE id=%s LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
    return success(_notification_payload(row), "通知设置已保存")


# ============================================================
# 意见反馈（user_feedback 表，与程序评价 platform_feedback 语义不同）
# ============================================================
@router.post("/feedback")
def create_user_feedback(body: UserFeedbackCreate, user_id: int = Depends(get_current_user_id)):
    content = (body.content or "").strip()
    contact = (body.contact or "").strip() or None
    if not content:
        raise HTTPException(400, "反馈内容不能为空")
    if len(content) > FEEDBACK_MAX_LEN:
        raise HTTPException(400, f"反馈内容不能超过 {FEEDBACK_MAX_LEN} 字")
    if contact and len(contact) > FEEDBACK_CONTACT_MAX_LEN:
        raise HTTPException(400, f"联系方式不能超过 {FEEDBACK_CONTACT_MAX_LEN} 字")

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {FEEDBACK_TABLE} (user_id, content, contact) VALUES (%s,%s,%s)",
                (user_id, content, contact),
            )
            feedback_id = cursor.lastrowid
    return success({"success": True, "feedback_id": feedback_id}, "感谢你的反馈")


# ============================================================
# 地址解析（高德 Web 服务地理编码）
# ============================================================
@router.post("/location/search-address")
def search_address(body: AddressSearchRequest, _: int = Depends(get_current_user_id)):
    """把文本地址解析为坐标 + 小区名 + 楼栋。

    仅返回解析结果，不落库；由前端确认后再调 PUT /user/profile 保存。
    """
    address = (body.address or "").strip()
    if len(address) < 2:
        raise HTTPException(400, "请输入至少 2 个字的地址")

    if not settings.amap_web_key:
        raise HTTPException(501, "地址解析服务未配置，请使用「定位当前位置」或联系管理员配置 AMAP_WEB_KEY")

    try:
        resp = requests.get(
            AMAP_GEOCODE_URL,
            params={"key": settings.amap_web_key, "address": address, "output": "JSON"},
            timeout=8,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.exception("高德地理编码请求失败 address=%s", address)
        raise HTTPException(502, "地址解析服务暂时不可用，请稍后重试") from exc

    if payload.get("status") != "1":
        raise HTTPException(400, f"地址解析失败：{payload.get('info') or '未找到该地址'}")

    geocodes = payload.get("geocodes") or []
    if not geocodes:
        raise HTTPException(404, "未找到该地址，请检查后重试")

    first = geocodes[0]
    location = first.get("location") or ""
    if "," not in location:
        raise HTTPException(404, "未找到该地址的坐标，请检查后重试")
    lng_text, lat_text = location.split(",", 1)
    try:
        longitude = float(lng_text)
        latitude = float(lat_text)
    except ValueError as exc:
        raise HTTPException(404, "地址解析结果异常，请稍后重试") from exc

    return success({
        "latitude": latitude,
        "longitude": longitude,
        "community": _extract_community(address, first.get("formatted_address")),
        "building": _extract_building(address),
        "formatted_address": first.get("formatted_address") or address,
    }, "地址解析成功")
