"""个人中心 profile 接口单元测试（数据库 mock，不连真实 MySQL）。"""
from datetime import datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from conftest import FakeCursor, make_connection

from app.api.v1 import user as user_api
from app.schemas.user import ProfileUpdate

PROFILE_ROW = {
    "id": 7,
    "nickname": "小满妈妈",
    "elderly_mode": 1,
    "accessibility_mode": "mobility_impaired",
    "mobility_level": "assisted",
    "high_contrast": 0,
    "preferred_lang": "en_US",
}


def _patch(monkeypatch, rows=None, rowcount=1):
    cursor = FakeCursor(rows=rows, rowcount=rowcount)
    monkeypatch.setattr(user_api, "connection", make_connection(cursor))
    return cursor


def test_get_profile_maps_preferred_lang_to_language(monkeypatch):
    _patch(monkeypatch, rows=[dict(PROFILE_ROW)])
    resp = user_api.get_profile(7)
    data = resp["data"]
    # 基础字段映射
    assert data["user_id"] == 7
    assert data["nickname"] == "小满妈妈"
    assert data["elderly_mode"] == 1
    assert data["accessibility_mode"] == "mobility_impaired"
    assert data["mobility_level"] == "assisted"
    assert data["high_contrast"] == 0
    # 关键映射：preferred_lang -> language
    assert data["language"] == "en_US"
    # 第二区新增字段存在且取默认值（行中未提供）
    assert data["avatar"] is None
    assert data["created_at"] is None
    assert data["points"] == 0
    assert data["carbon_total"] == 0
    assert data["community"] is None


def test_get_profile_uses_defaults_when_columns_null(monkeypatch):
    row = {"id": 1, "nickname": None, "elderly_mode": 0, "accessibility_mode": None,
           "mobility_level": None, "high_contrast": 0, "preferred_lang": None}
    _patch(monkeypatch, rows=[row])
    data = user_api.get_profile(1)["data"]
    assert data["accessibility_mode"] == "normal"
    assert data["mobility_level"] == "free"
    assert data["language"] == "zh_CN"


def test_get_profile_404_when_missing(monkeypatch):
    _patch(monkeypatch, rows=[])
    with pytest.raises(HTTPException) as exc:
        user_api.get_profile(404)
    assert exc.value.status_code == 404


def test_update_profile_persists_and_returns_full_profile(monkeypatch):
    cursor = _patch(monkeypatch, rows=[{**PROFILE_ROW, "elderly_mode": 0,
                                       "high_contrast": 1, "preferred_lang": "zh_CN"}])
    body = ProfileUpdate(elderly_mode=0, high_contrast=1, language="zh_CN")
    # 接口收口后签名为 (body, user_id=Depends(...))，user_id 改为第二实参传入
    data = user_api.update_profile(body, 7)["data"]
    # UPDATE 语句应包含白名单列且 language 映射到 preferred_lang
    update_sql, params = cursor.executed[0]
    assert update_sql.startswith("UPDATE user SET")
    assert "elderly_mode=%s" in update_sql
    assert "high_contrast=%s" in update_sql
    assert "preferred_lang=%s" in update_sql
    assert params == [0, 1, "zh_CN", 7]
    # 返回更新后的完整 profile
    assert data["high_contrast"] == 1
    assert data["language"] == "zh_CN"


def test_update_profile_404_when_no_row(monkeypatch):
    _patch(monkeypatch, rows=[], rowcount=0)
    with pytest.raises(HTTPException) as exc:
        user_api.update_profile(ProfileUpdate(elderly_mode=1), 9)
    assert exc.value.status_code == 404


def test_update_empty_payload_rejected():
    with pytest.raises(ValidationError):
        ProfileUpdate(elderly_mode=2)  # 只允许 0/1
    with pytest.raises(ValidationError):
        ProfileUpdate(accessibility_mode="weird")
    with pytest.raises(ValidationError):
        ProfileUpdate(language="fr_FR")


def test_get_profile_returns_new_fields(monkeypatch):
    """第 2 批新增字段：存在性、类型与日期可解析性。

    仅校验新增字段本身，不做精确 dict 断言，避免响应结构扩展时再次锁死。
    """
    row = {
        **PROFILE_ROW,
        "avatar": "/api/v1/static/avatars/abc.jpg",
        "created_at": "2026-06-01 08:30:00",
        "points": 328,
        "carbon_total": 12.5,
        "community": "阳光花园小区",
    }
    _patch(monkeypatch, rows=[row])
    data = user_api.get_profile(7)["data"]

    # 1. 五个新字段均存在于响应中
    for field in ("avatar", "created_at", "points", "carbon_total", "community"):
        assert field in data, f"响应缺少新增字段：{field}"

    # 2. 类型断言：points 为整数，carbon_total 为浮点数
    assert isinstance(data["points"], int)
    assert isinstance(data["carbon_total"], float)

    # 3. created_at 可解析为日期
    assert isinstance(data["created_at"], datetime)

    # 4. 值透传正确（非精确 dict 断言，逐字段核对）
    assert data["avatar"].startswith("/api/v1/static/avatars/")
    assert data["community"] == "阳光花园小区"
    assert data["points"] == 328
    assert data["carbon_total"] == 12.5
    assert data["created_at"].year == 2026


# ============================================================
# 头像签名口径：DB 只存相对路径，签名每次读取现场补
# （与物品封面同一约定；存量「已签名 URL」必须先剥旧签名再重签，
#   否则原样返回会在 1 小时后 403）
# ============================================================
def test_avatar_bare_relative_path_gets_fresh_signature(monkeypatch):
    """裸相对路径 → 补签名，exp 是当前时刻 +1h（不是任何历史时间戳）。"""
    url = user_api._avatar_signed_url("avatars/abc.jpg")
    assert url.startswith("/api/v1/static/avatars/abc.jpg?exp=")
    assert "sig=" in url


def test_avatar_legacy_signed_url_is_resigned(monkeypatch):
    """★ 存量已签名头像：剥掉旧签名重签，绝不原样返回过期 URL。"""
    legacy = "avatars/abc.jpg?exp=1000000000&sig=deadbeef"
    url = user_api._avatar_signed_url(legacy)

    assert "1000000000" not in url        # 旧 exp 已丢弃
    assert "deadbeef" not in url          # 旧 sig 已丢弃
    assert url.count("exp=") == 1 and url.count("sig=") == 1
    assert url.startswith("/api/v1/static/avatars/abc.jpg?")


def test_avatar_external_and_empty_pass_through():
    """外链原样返回；空值返回 None（前端据此显示默认头像）。"""
    assert user_api._avatar_signed_url("https://cdn.example.com/a.png") == "https://cdn.example.com/a.png"
    assert user_api._avatar_signed_url(None) is None
    assert user_api._avatar_signed_url("") is None
