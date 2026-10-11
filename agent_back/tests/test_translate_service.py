"""translate_service 单元测试。"""
import pytest

from app.services import translate_service


def test_translate_same_language_returns_original():
    result = translate_service.translate("你好", "zh_CN", "zh_CN")
    assert result["translated_text"] == "你好"
    assert result["confidence"] == 1.0
    assert result["note"] == ""


def test_translate_empty_text_raises():
    with pytest.raises(ValueError, match="翻译内容不能为空"):
        translate_service.translate("", "zh_CN", "en_US")


def test_translate_zh_to_en(monkeypatch):
    def fake_translate(text, prompt):
        return {"translation": "Hello", "confidence": 0.95}

    monkeypatch.setattr("app.services.translate_service.llm_client.translate_text", fake_translate)
    result = translate_service.translate("你好", "zh_CN", "en_US")
    assert result["translated_text"] == "Hello"
    assert result["confidence"] == 0.95
    assert result["note"] == translate_service.AI_TRANSLATED_NOTE["en_US"]


def test_translate_en_to_zh(monkeypatch):
    def fake_translate(text, prompt):
        return {"translation": "你好", "confidence": 0.91}

    monkeypatch.setattr("app.services.translate_service.llm_client.translate_text", fake_translate)
    result = translate_service.translate("Hello", "en_US", "zh_CN")
    assert result["translated_text"] == "你好"
    assert result["note"] == translate_service.AI_TRANSLATED_NOTE["zh_CN"]
