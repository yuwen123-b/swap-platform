"""账户安全接口单元测试：改密码 / 换绑手机 / 换绑邮箱（数据库 mock，不连真实 MySQL）。

验证码与短信/邮件通道全部 monkeypatch，不触发真实外发。
"""
import pytest
from fastapi import HTTPException

from conftest import FakeCursor, make_connection

from app.api.v1 import user as user_api
from app.core.security import hash_password
from app.schemas.user import (
    EmailBindRequest,
    EmailSendCodeRequest,
    PasswordUpdate,
    PhoneBindRequest,
    PhoneSendCodeRequest,
)

OLD_PASSWORD = "OldPass123"
NEW_PASSWORD = "NewPass456"
SALT = "abcd1234abcd1234"
NEW_PHONE = "13900001111"
NEW_EMAIL = "new@example.com"


def _patch(monkeypatch, rows=None, rowcount=1):
    cursor = FakeCursor(rows=rows, rowcount=rowcount)
    monkeypatch.setattr(user_api, "connection", make_connection(cursor))
    return cursor


def _stub_code(monkeypatch, verify_result=True, created="123456"):
    """替换验证码服务的发送/校验，避免真实外发与内存状态污染。"""
    monkeypatch.setattr(user_api, "verify_code", lambda *a, **k: verify_result)
    monkeypatch.setattr(user_api, "create_code", lambda *a, **k: created)


def _capture_channels(monkeypatch):
    sent = {"sms": [], "email": []}
    monkeypatch.setattr(user_api, "send_sms", lambda target, code: sent["sms"].append((target, code)))
    monkeypatch.setattr(user_api, "send_email", lambda target, code: sent["email"].append((target, code)))
    return sent


# ============================================================
# 1. 修改密码
# ============================================================
def test_change_password_old_password_wrong(monkeypatch):
    """旧密码不匹配 -> 400 原密码错误，且不执行 UPDATE。"""
    cursor = _patch(monkeypatch, rows=[{"password_md5": "deadbeef", "salt": SALT}])
    with pytest.raises(HTTPException) as exc:
        user_api.change_password(PasswordUpdate(old_password=OLD_PASSWORD, new_password=NEW_PASSWORD), 7)
    assert exc.value.status_code == 400
    assert "原密码错误" in exc.value.detail
    # 只查了库，没有写库
    assert len(cursor.executed) == 1


def test_change_password_no_user_leaks_nothing(monkeypatch):
    """用户不存在时返回与「密码错误」完全一致的提示，不泄露账号存在性。"""
    _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.change_password(PasswordUpdate(old_password=OLD_PASSWORD, new_password=NEW_PASSWORD), 7)
    assert exc.value.status_code == 400
    assert exc.value.detail == "原密码错误"


def test_change_password_too_short_rejected(monkeypatch):
    """新密码长度不足 8 位 -> 400，且不触库。"""
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.change_password(PasswordUpdate(old_password=OLD_PASSWORD, new_password="Ab1"), 7)
    assert exc.value.status_code == 400
    assert "8-32" in exc.value.detail
    assert cursor.executed == []


def test_change_password_requires_letter_and_digit(monkeypatch):
    """新密码缺少字母或数字 -> 400。"""
    _patch(monkeypatch, rows=[])
    for weak in ("onlyletters", "1234567890"):
        with pytest.raises(HTTPException) as exc:
            user_api.change_password(PasswordUpdate(old_password=OLD_PASSWORD, new_password=weak), 7)
        assert exc.value.status_code == 400
        assert "字母和数字" in exc.value.detail


def test_change_password_same_as_old_rejected(monkeypatch):
    """新密码与原密码相同 -> 400。"""
    _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.change_password(PasswordUpdate(old_password=OLD_PASSWORD, new_password=OLD_PASSWORD), 7)
    assert exc.value.status_code == 400
    assert "不能与原密码相同" in exc.value.detail


def test_change_password_success_rotates_salt_and_hash(monkeypatch):
    """成功路径：同时更新 password_md5 与 salt，新哈希由新盐算出。"""
    old_hash = hash_password(OLD_PASSWORD, SALT)
    cursor = _patch(monkeypatch, rows=[{"password_md5": old_hash, "salt": SALT}])

    resp = user_api.change_password(PasswordUpdate(old_password=OLD_PASSWORD, new_password=NEW_PASSWORD), 7)

    assert resp["code"] == 0
    assert resp["data"] == {"success": True}
    # 第 2 条语句是 UPDATE，且同时写了哈希与盐
    update_sql, params = cursor.executed[1]
    assert update_sql == "UPDATE user SET password_md5=%s, salt=%s WHERE id=%s"
    new_hash, new_salt_value, target_id = params
    assert target_id == 7
    # 盐已轮换，哈希基于新盐且可复算
    assert new_salt_value != SALT
    assert new_hash != old_hash
    assert new_hash == hash_password(NEW_PASSWORD, new_salt_value)


# ============================================================
# 2. 换绑手机
# ============================================================
def test_send_phone_code_invalid_format(monkeypatch):
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.send_phone_bind_code(PhoneSendCodeRequest(new_phone="12345"), 7)
    assert exc.value.status_code == 400
    assert "手机号格式不正确" in exc.value.detail
    assert cursor.executed == []


def test_send_phone_code_already_used(monkeypatch):
    """新手机号已被他人占用 -> 400，且不发送验证码。"""
    sent = _capture_channels(monkeypatch)
    _stub_code(monkeypatch)
    _patch(monkeypatch, rows=[{"id": 99}])
    with pytest.raises(HTTPException) as exc:
        user_api.send_phone_bind_code(PhoneSendCodeRequest(new_phone=NEW_PHONE), 7)
    assert exc.value.status_code == 400
    assert "已被使用" in exc.value.detail
    assert sent["sms"] == []


def test_send_phone_code_success(monkeypatch):
    sent = _capture_channels(monkeypatch)
    _stub_code(monkeypatch, created="654321")
    cursor = _patch(monkeypatch, rows=[])

    resp = user_api.send_phone_bind_code(PhoneSendCodeRequest(new_phone=NEW_PHONE), 7)

    assert resp["code"] == 0
    assert resp["data"]["expires_in"] == 300
    assert resp["data"]["success"] is True
    assert sent["sms"] == [(NEW_PHONE, "654321")]
    # 占用检查把「自己」排除，避免换绑到当前已用的号码被误判
    sql, params = cursor.executed[0]
    assert "id<>%s" in sql
    assert params == (NEW_PHONE, 7)


def test_send_phone_code_too_frequent_returns_429(monkeypatch):
    """60 秒内重复发送：code_service 抛 ValueError -> 429。"""
    _capture_channels(monkeypatch)
    monkeypatch.setattr(user_api, "verify_code", lambda *a, **k: True)

    def _boom(*_args, **_kwargs):
        raise ValueError("验证码发送过于频繁，请稍后再试")

    monkeypatch.setattr(user_api, "create_code", _boom)
    _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.send_phone_bind_code(PhoneSendCodeRequest(new_phone=NEW_PHONE), 7)
    assert exc.value.status_code == 429


def test_bind_phone_wrong_code(monkeypatch):
    _stub_code(monkeypatch, verify_result=False)
    cursor = _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.bind_phone(PhoneBindRequest(new_phone=NEW_PHONE, code="000000"), 7)
    assert exc.value.status_code == 400
    assert "验证码错误或已过期" in exc.value.detail
    assert cursor.executed == []


def test_bind_phone_already_used(monkeypatch):
    """验证码正确但号码已被占用 -> 400（并发防护）。"""
    _stub_code(monkeypatch, verify_result=True)
    cursor = _patch(monkeypatch, rows=[{"id": 88}])
    with pytest.raises(HTTPException) as exc:
        user_api.bind_phone(PhoneBindRequest(new_phone=NEW_PHONE, code="123456"), 7)
    assert exc.value.status_code == 400
    assert "已被使用" in exc.value.detail
    # 只有占用检查，没有 UPDATE
    assert len(cursor.executed) == 1


def test_bind_phone_success_returns_masked(monkeypatch):
    _stub_code(monkeypatch, verify_result=True)
    cursor = _patch(monkeypatch, rows=[])

    resp = user_api.bind_phone(PhoneBindRequest(new_phone=NEW_PHONE, code="123456"), 7)

    assert resp["code"] == 0
    assert resp["data"]["phone"] == "139****1111"
    update_sql, params = cursor.executed[1]
    assert update_sql == "UPDATE user SET phone=%s WHERE id=%s"
    assert params == (NEW_PHONE, 7)


# ============================================================
# 3. 换绑邮箱
# ============================================================
def test_send_email_code_invalid_format(monkeypatch):
    _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.send_email_bind_code(EmailSendCodeRequest(new_email="not-an-email"), 7)
    assert exc.value.status_code == 400
    assert "邮箱格式不正确" in exc.value.detail


def test_send_email_code_success(monkeypatch):
    sent = _capture_channels(monkeypatch)
    _stub_code(monkeypatch, created="246810")
    _patch(monkeypatch, rows=[])
    resp = user_api.send_email_bind_code(EmailSendCodeRequest(new_email=NEW_EMAIL), 7)
    assert resp["data"]["expires_in"] == 300
    assert sent["email"] == [(NEW_EMAIL, "246810")]


def test_bind_email_wrong_code(monkeypatch):
    _stub_code(monkeypatch, verify_result=False)
    _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.bind_email(EmailBindRequest(new_email=NEW_EMAIL, code="000000"), 7)
    assert exc.value.status_code == 400
    assert "验证码错误或已过期" in exc.value.detail


def test_bind_email_success_returns_masked(monkeypatch):
    _stub_code(monkeypatch, verify_result=True)
    cursor = _patch(monkeypatch, rows=[])

    resp = user_api.bind_email(EmailBindRequest(new_email=NEW_EMAIL, code="123456"), 7)

    assert resp["data"]["email"] == "ne***@example.com"
    update_sql, params = cursor.executed[1]
    assert update_sql == "UPDATE user SET email=%s WHERE id=%s"
    assert params == (NEW_EMAIL, 7)


def test_bind_email_already_used(monkeypatch):
    _stub_code(monkeypatch, verify_result=True)
    _patch(monkeypatch, rows=[{"id": 77}])
    with pytest.raises(HTTPException) as exc:
        user_api.bind_email(EmailBindRequest(new_email=NEW_EMAIL, code="123456"), 7)
    assert exc.value.status_code == 400
    assert "已被使用" in exc.value.detail
