import base64
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

SMS_ENDPOINT = "https://dysmsapi.aliyuncs.com"


def _percent_encode(value: str) -> str:
    """阿里云 RPC 签名要求的 RFC3986 编码：+ -> %20、* -> %2A、保留 ~。"""
    return quote(str(value), safe="~").replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


def _aliyun_send(phone: str, code: str) -> None:
    missing = [
        name
        for name, value in (
            ("SMS_ACCESS_KEY_ID", settings.sms_access_key_id),
            ("SMS_ACCESS_KEY_SECRET", settings.sms_access_key_secret),
            ("SMS_SIGN_NAME", settings.sms_sign_name),
            ("SMS_TEMPLATE_CODE", settings.sms_template_code),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"阿里云短信未配置：请在 .env 中设置 {' / '.join(missing)}")

    params = {
        "Action": "SendSms",
        "Version": "2017-05-25",
        "Format": "JSON",
        "RegionId": "cn-hangzhou",
        "AccessKeyId": settings.sms_access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid.uuid4().hex,
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "PhoneNumbers": phone,
        "SignName": settings.sms_sign_name,
        "TemplateCode": settings.sms_template_code,
        "TemplateParam": json.dumps({"code": code}),
    }
    canonical = "&".join(
        f"{_percent_encode(key)}={_percent_encode(value)}" for key, value in sorted(params.items())
    )
    string_to_sign = f"POST&%2F&{_percent_encode(canonical)}"
    signature = base64.b64encode(
        hmac.new(
            f"{settings.sms_access_key_secret}&".encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        ).digest()
    ).decode()
    params["Signature"] = signature

    response = requests.post(SMS_ENDPOINT, data=params, timeout=10)
    # 不要直接 raise_for_status：阿里云鉴权失败（如 RAM 未授权 SendSms）会返回 403，
    # 需要把响应体中的错误码一并暴露，便于定位配置问题。
    if response.status_code >= 400:
        raise RuntimeError(f"阿里云短信请求失败 HTTP {response.status_code}: {response.text[:500]}")
    result = response.json()
    if result.get("Code") != "OK":
        raise RuntimeError(f"阿里云短信发送失败: Code={result.get('Code')}, Message={result.get('Message')}")


def _mock_send(phone: str, code: str) -> None:
    masked = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else phone
    line = f"[短信验证码] 发送至 {masked}: {code}"
    logger.info(line)
    print(f"\n{'=' * 48}\n{line}\n{'=' * 48}\n", flush=True)


def send_sms(phone: str, code: str) -> None:
    provider = settings.sms_provider.lower()
    if provider == "mock":
        _mock_send(phone, code)
        return
    if provider == "aliyun":
        _aliyun_send(phone, code)
        return
    raise RuntimeError(f"不支持的短信服务商: {settings.sms_provider}")
