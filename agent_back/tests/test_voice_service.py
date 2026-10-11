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


def test_synthesize_disabled_without_key(monkeypatch):
    """未配置大模型密钥时 TTS 降级：返回空 URL，不发起任何请求。"""
    monkeypatch.setattr("app.services.voice_service.settings.llm_api_key", "")
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        return b"audio"

    monkeypatch.setattr("app.services.voice_service.llm_client.synthesize_speech", boom)
    assert voice_service.synthesize("找到电饭煲了") == ""
    assert called["n"] == 0


def test_synthesize_writes_file_and_downgrades(monkeypatch, tmp_path):
    """合成成功落盘并返回静态 URL；合成失败时静默降级为空 URL。"""
    monkeypatch.setattr("app.services.voice_service.settings.llm_api_key", "sk-test")
    monkeypatch.setattr("app.services.voice_service.settings.upload_dir", str(tmp_path))
    monkeypatch.setattr("app.services.voice_service.settings.api_prefix", "/api/v1")
    monkeypatch.setattr(
        "app.services.voice_service.llm_client.synthesize_speech",
        lambda text, rate=1.0: b"fake-mp3-bytes",
    )
    url = voice_service.synthesize("找到电饭煲了", "zh_CN", rate=0.8)
    assert url.startswith("/api/v1/static/tts/") and url.endswith(".mp3")
    # 落盘文件存在，且第二次调用命中缓存不再请求
    audio_file = tmp_path / "tts" / url.rsplit("/", 1)[-1]
    assert audio_file.read_bytes() == b"fake-mp3-bytes"
    calls = {"n": 0}

    def counting(*a, **k):
        calls["n"] += 1
        return b"fake-mp3-bytes"

    monkeypatch.setattr("app.services.voice_service.llm_client.synthesize_speech", counting)
    voice_service.synthesize("找到电饭煲了", "zh_CN", rate=0.8)
    assert calls["n"] == 0
    # 合成失败：返回空串且不抛异常
    def failing(*a, **k):
        raise RuntimeError("TTS 服务不可用")

    monkeypatch.setattr("app.services.voice_service.llm_client.synthesize_speech", failing)
    assert voice_service.synthesize("另一段文本", "zh_CN", rate=0.8) == ""
