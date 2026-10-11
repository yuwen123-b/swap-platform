"""个人中心 profile 接口单元测试（数据库 mock，不连真实 MySQL）。"""
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
    assert data == {
        "user_id": 7,
        "nickname": "小满妈妈",
        "elderly_mode": 1,
        "accessibility_mode": "mobility_impaired",
        "mobility_level": "assisted",
        "high_contrast": 0,
        "language": "en_US",
    }


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
    data = user_api.update_profile(7, body)["data"]
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
        user_api.update_profile(9, ProfileUpdate(elderly_mode=1))
    assert exc.value.status_code == 404


def test_update_empty_payload_rejected():
    with pytest.raises(ValidationError):
        ProfileUpdate(elderly_mode=2)  # 只允许 0/1
    with pytest.raises(ValidationError):
        ProfileUpdate(accessibility_mode="weird")
    with pytest.raises(ValidationError):
        ProfileUpdate(language="fr_FR")
