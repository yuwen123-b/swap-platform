"""accessibility_service 与 match_service 单元测试。"""
import pytest
from conftest import FakeCursor, make_connection

from app.services import accessibility_service, match_service


def _patch_db(monkeypatch, rows, rowcount=1):
    cursor = FakeCursor(rows=rows, rowcount=rowcount)
    monkeypatch.setattr("app.services.accessibility_service.connection", make_connection(cursor))
    return cursor


def test_set_mode_invalid():
    with pytest.raises(ValueError, match="不支持"):
        accessibility_service.set_mode(1, "super_mode")


def test_set_mode_visual_returns_ui_config(monkeypatch):
    _patch_db(monkeypatch, [])
    result = accessibility_service.set_mode(1, "visually_impaired")
    assert result["success"] is True
    assert result["ui_config"]["voice_navigation"] is True
    assert result["ui_config"]["high_contrast"] is True


def test_set_mode_user_not_found(monkeypatch):
    _patch_db(monkeypatch, [], rowcount=0)
    with pytest.raises(ValueError, match="用户不存在"):
        accessibility_service.set_mode(999, "normal")


def test_ui_config_mobility_skips_self_pickup():
    config = accessibility_service.ui_config_for("mobility_impaired")
    assert config["skip_self_pickup"] is True
    assert config["volunteer_entry"] is True


def test_get_profile_defaults(monkeypatch):
    _patch_db(monkeypatch, [{"mobility_level": None, "accessibility_mode": None, "preferred_lang": None}])
    profile = accessibility_service.get_profile(1)
    assert profile["mobility_level"] == "free"
    assert profile["accessibility_mode"] == "normal"
    assert profile["preferred_lang"] == "zh_CN"


def test_voice_label_via_llm(monkeypatch):
    _patch_db(monkeypatch, [{"title": "美的电饭煲", "description": "蓝色，轻微使用痕迹", "condition_level": 1}])
    monkeypatch.setattr(
        "app.services.accessibility_service.llm_client.chat_text",
        lambda messages, timeout=30: "美的电饭煲，九成新，蓝色，有轻微使用痕迹",
    )
    label = accessibility_service.generate_voice_label(5)
    assert "美的电饭煲" in label


def test_voice_label_fallback_on_llm_failure(monkeypatch):
    _patch_db(monkeypatch, [{"title": "美的电饭煲", "description": "", "condition_level": 1}])

    def boom(messages, timeout=30):
        raise RuntimeError("LLM 不可用")

    monkeypatch.setattr("app.services.accessibility_service.llm_client.chat_text", boom)
    assert accessibility_service.generate_voice_label(5) == "美的电饭煲，九成新"


def test_match_handover_limited_excludes_self_pickup(monkeypatch):
    monkeypatch.setattr(
        "app.services.match_service.accessibility_service.get_profile",
        lambda user_id: {"mobility_level": "limited"},
    )
    result = match_service.evaluate_handover(1)
    assert "self_pickup" not in result["methods"]
    assert result["recommended"] == "door_delivery"


def test_match_handover_free_allows_self_pickup(monkeypatch):
    monkeypatch.setattr(
        "app.services.match_service.accessibility_service.get_profile",
        lambda user_id: {"mobility_level": "free"},
    )
    result = match_service.evaluate_handover(1)
    assert "self_pickup" in result["methods"]
    assert result["recommended"] == "self_pickup"
