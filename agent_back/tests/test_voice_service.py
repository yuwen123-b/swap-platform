"""voice_service 单元测试。"""
import pytest

from app.services import voice_service


def test_build_speech_text_elderly_rate_and_sentence_limit():
    text = "找到了，这个可以换。美的电饭煲，九成新，外观干净无划痕，功能都正常。"
    result = voice_service.build_speech_text(text, mode="elderly", language="zh_CN")
    assert result["rate"] == 0.8
    assert result["voice"] == "zh-CN"
    assert result["sentences"], "应至少有一句"
    assert all(len(s) <= 20 for s in result["sentences"])


def test_build_speech_text_normal_full_sentence():
    text = "这是一条长度超过二十个字的普通模式播报文本，不应被切句处理。"
    result = voice_service.build_speech_text(text, mode="normal", language="en_US")
    assert result["rate"] == 1.0
    assert result["voice"] == "en-US"
    assert result["sentences"] == [text]


def test_transcribe_requires_public_base_url(monkeypatch):
    monkeypatch.setattr("app.services.voice_service.settings.public_base_url", "")
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        voice_service.transcribe(__import__("pathlib").Path("a.webm"))


def test_transcribe_calls_llm_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.voice_service.settings.public_base_url", "https://example.com"
    )
    called = {}

    def fake_transcribe(file_url):
        called["url"] = file_url
        return "我想换电饭煲"

    monkeypatch.setattr("app.services.voice_service.llm_client.transcribe_audio", fake_transcribe)
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"fake")
    assert voice_service.transcribe(audio) == "我想换电饭煲"
    assert called["url"].endswith("/api/v1/static/voice/a.webm")
