import re
import logging
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.response import success
from app.core.config import settings
from app.core.security import create_token, get_current_user_id, hash_password, new_salt
from app.db.pool import connection
from app.schemas.auth import (EmailCodeLoginRequest, PasswordLoginRequest, PhoneCodeLoginRequest, RegisterRequest, SendCodeRequest)
from app.services.code_service import create_code, verify_code
from app.utils.email import send_email
from app.utils.sms import send_sms

router = APIRouter()
logger = logging.getLogger(__name__)
PHONE_PATTERN = re.compile(r"^1\d{10}$")


def target_meta(target_type: str, scene: str) -> tuple[int, int]:
    types = {"email": 1, "phone": 2}
    # bind=4：换绑手机/邮箱场景（见 app/api/v1/user.py 的 _SCENE_BIND）
    scenes = {"register": 1, "login": 2, "reset": 3, "bind": 4}
    if target_type not in types or scene not in scenes:
        raise HTTPException(400, "验证码类型或场景无效")
    return types[target_type], scenes[scene]


def user_payload(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row.get("email"),
        "phone": row.get("phone"),
        "nickname": row.get("nickname"),
        "avatar": row.get("avatar"),
        # 持久化的个人偏好：前端据此决定初始语言与无障碍模式
        "elderly_mode": int(row.get("elderly_mode") or 0),
        "accessibility_mode": row.get("accessibility_mode") or "normal",
        "mobility_level": row.get("mobility_level") or "free",
        "high_contrast": int(row.get("high_contrast") or 0),
        "language": row.get("preferred_lang") or "zh_CN",
    }


def login_by_user(row: dict):
    return success({"token": create_token(row["id"]), "user": user_payload(row)}, "登录成功")


def mark_login(row: dict, request: Request) -> None:
    client_ip = request.client.host if request.client else ""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE user SET last_login_time=NOW(), last_login_ip=%s, failed_login_count=0 WHERE id=%s",
                (client_ip, row["id"]),
            )


def validate_target(target: str, target_type: str) -> None:
    if target_type == "phone" and not PHONE_PATTERN.fullmatch(target):
        raise HTTPException(422, "手机号格式不正确")
    if target_type == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", target):
        raise HTTPException(422, "邮箱格式不正确")


def login_response(row: dict, request: Request):
    mark_login(row, request)
    return success({"token": create_token(row["id"]), "user": user_payload(row)}, "登录成功")


@router.post("/send-code")
def send_code(payload: SendCodeRequest):
    target_type, scene = target_meta(payload.target_type, payload.scene)
    validate_target(payload.target, payload.target_type)
    try:
        code = create_code(payload.target, target_type, scene)
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from exc

    delivered = True
    try:
        if payload.target_type == "email":
            send_email(payload.target, code)
        else:
            send_sms(payload.target, code)
    except Exception:
        if settings.debug:
            # 开发环境降级：验证码打印到控制台并通过 debug_code 返回，不阻断注册流程。
            logger.warning("验证码通道发送失败，已降级为控制台投递 target=%s code=%s", payload.target, code)
            delivered = False
        else:
            logger.exception("验证码发送失败 target=%s target_type=%s", payload.target, payload.target_type)
            raise HTTPException(500, "验证码发送失败，请稍后重试")

    if settings.debug:
        return success({"debug_code": code, "delivered": delivered})
    return success(None if delivered else {"delivered": False})


@router.post("/register")
def register(payload: RegisterRequest):
    if payload.register_type not in {"email", "phone"}:
        raise HTTPException(422, "注册方式无效")
    target = payload.email if payload.register_type == "email" else payload.phone
    if not target:
        raise HTTPException(422, "请填写对应的注册账号")
    validate_target(target, payload.register_type)
    target_type = 1 if payload.register_type == "email" else 2
    if not verify_code(target, target_type, 1, payload.code):
        raise HTTPException(400, "验证码错误或已过期")
    salt = new_salt()
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM user WHERE email=%s OR phone=%s LIMIT 1", (payload.email, payload.phone))
            if cursor.fetchone():
                raise HTTPException(409, "邮箱或手机号已注册")
            # user.phone 是 NOT NULL 且唯一；邮箱注册先写占位值，绑定手机号时再更新。
            phone = payload.phone or f"em_{secrets.token_hex(4)}"
            cursor.execute("INSERT INTO user (phone,email,nickname,password_md5,salt) VALUES (%s,%s,%s,%s,%s)", (phone, payload.email, payload.nickname, hash_password(payload.password, salt), salt))
            user_id = cursor.lastrowid
    return success({"user_id": user_id}, "注册成功")


@router.post("/login/email-code")
def email_code_login(payload: EmailCodeLoginRequest, request: Request):
    if not verify_code(payload.email, 1, 2, payload.code):
        raise HTTPException(401, "验证码错误或已过期")
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user WHERE email=%s LIMIT 1", (payload.email,))
            row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")
    return login_response(row, request)


@router.post("/login/phone-code")
def phone_code_login(payload: PhoneCodeLoginRequest, request: Request):
    if not verify_code(payload.phone, 2, 2, payload.code):
        raise HTTPException(401, "验证码错误或已过期")
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user WHERE phone=%s LIMIT 1", (payload.phone,))
            row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")
    return login_response(row, request)


@router.post("/login/password")
def password_login(payload: PasswordLoginRequest, request: Request):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user WHERE email=%s LIMIT 1", (payload.email,))
            row = cursor.fetchone()
    if not row or row["password_md5"] != hash_password(payload.password, row["salt"]):
        raise HTTPException(401, "邮箱或密码错误")
    return login_response(row, request)


@router.get("/me")
def me(user_id: int = Depends(get_current_user_id)):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user WHERE id=%s LIMIT 1", (user_id,))
            row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")
    return success(user_payload(row))
