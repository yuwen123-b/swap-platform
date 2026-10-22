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
    """主链路（qwen3-asr-flash）失败且没有公网 URL 时：错误里必须同时说明两层原因。

    旧版这里断言的是"没配 PUBLIC_BASE_URL 就直接失败"——那是 paraformer 单链路时代的结论。
    现在主链路是本地直传的 qwen3，不再依赖公网地址；只有它失败后才轮到需要 URL 的
    paraformer，因此该测试改为显式让主链路失败，验证兜底原因被如实抛出（而不是静默降级）。
    """
    monkeypatch.setattr("app.services.voice_service.settings.public_base_url", "")
    monkeypatch.setattr("app.services.voice_service.settings.modelscope_api_key", "")
    monkeypatch.setattr("app.services.voice_service.settings.asr_provider", "dashscope")

    def boom(_path):
        raise RuntimeError("模型未开通")

    monkeypatch.setattr("app.services.llm_client._transcribe_qwen_asr", boom)
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        voice_service.transcribe(__import__("pathlib").Path("a.webm"))


def test_transcribe_calls_llm_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.voice_service.settings.public_base_url", "https://example.com"
    )
    called = {}

    def fake_transcribe(file_path, file_url=""):
        called["url"] = file_url
        return "我想换电饭煲"

    monkeypatch.setattr("app.services.voice_service.llm_client.transcribe_audio", fake_transcribe)
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"fake")
    assert voice_service.transcribe(audio) == "我想换电饭煲"
    assert called["url"].endswith("/api/v1/static/voice/a.webm")


def test_synthesize_disabled_without_key(monkeypatch):
    """未配置大模型密钥时 TTS 降级：返回空 URL，不发起任何请求。"""
    # 同上：显式清空两个供应商的 Key，不依赖真实 .env 状态
    monkeypatch.setattr("app.services.voice_service.settings.dashscope_api_key", "")
    monkeypatch.setattr("app.services.voice_service.settings.modelscope_api_key", "")
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        return b"audio"

    monkeypatch.setattr("app.services.voice_service.llm_client.synthesize_speech", boom)
    assert voice_service.synthesize("找到电饭煲了") == ""
    assert called["n"] == 0


def _wav_bytes(size: int = 400) -> bytes:
    """最小合法 WAV：RIFF 头 + 单声道 8bit 静音样本。"""
    return (
        b"RIFF" + (size + 36).to_bytes(4, "little") + b"WAVE"
        + b"fmt " + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")   # PCM / 单声道
        + (8000).to_bytes(4, "little") + (8000).to_bytes(4, "little")
        + (1).to_bytes(2, "little") + (8).to_bytes(2, "little")   # 块对齐 / 位深
        + b"data" + size.to_bytes(4, "little") + b"\x80" * size
    )


def _mp3_bytes(size: int = 400) -> bytes:
    """带 ID3 头的 MP3 头（只验证容器识别，不要求可解码）。"""
    return b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * size


def _cache_base(text: str, lang: str = "zh_CN", rate: float = 0.8) -> str:
    import hashlib

    return hashlib.md5(f"{lang}|{rate}|{text}".encode("utf-8")).hexdigest()


def test_audio_ext_sniffing():
    """容器识别只看字节：同一套代码可能拿到 WAV，也可能拿到 MP3。"""
    assert voice_service.audio_ext(_wav_bytes()) == ".wav"
    assert voice_service.audio_ext(_mp3_bytes()) == ".mp3"
    assert voice_service.audio_ext(b"\xff\xfb\x90\x00" + b"\x00" * 20) == ".mp3"
    assert voice_service.audio_ext(b"OggS" + b"\x00" * 20) == ".ogg"
    assert voice_service.audio_ext(b"audio") == ""
    assert voice_service.audio_ext(b'{"error":"quota"}') == ""


def test_synthesize_writes_file_and_downgrades(monkeypatch, tmp_path):
    """合成成功落盘并返回带签名的静态 URL；合成失败时静默降级为空 URL。"""
    monkeypatch.setattr("app.services.voice_service.settings.dashscope_api_key", "sk-test")
    monkeypatch.setattr("app.services.voice_service.settings.upload_dir", str(tmp_path))
    monkeypatch.setattr("app.services.voice_service.settings.api_prefix", "/api/v1")
    monkeypatch.setattr(
        "app.services.voice_service.llm_client.synthesize_speech",
        lambda text, rate=1.0: _wav_bytes(),
    )
    url = voice_service.synthesize("找到电饭煲了", "zh_CN", rate=0.8)
    # 扩展名必须与真实容器一致：WAV 内容写 .mp3 会被 iOS 的 nosniff 直接拒播
    assert url.startswith("/api/v1/static/tts/") and ".wav?" in url
    # 必须是签名 URL：静态路由未签名一律 403，这正是「后端音频从来没播出来」的根因
    assert "exp=" in url and "sig=" in url
    # 落盘文件存在，且第二次调用命中缓存不再请求
    audio_file = tmp_path / "tts" / url.rsplit("/", 1)[-1].split("?")[0]
    assert audio_file.read_bytes() == _wav_bytes()
    calls = {"n": 0}

    def counting(*a, **k):
        calls["n"] += 1
        return _wav_bytes()

    monkeypatch.setattr("app.services.voice_service.llm_client.synthesize_speech", counting)
    assert voice_service.synthesize("找到电饭煲了", "zh_CN", rate=0.8).startswith("/api/v1/static/tts/")
    assert calls["n"] == 0
    # 合成失败：返回空串且不抛异常
    def failing(*a, **k):
        raise RuntimeError("TTS 服务不可用")

    monkeypatch.setattr("app.services.voice_service.llm_client.synthesize_speech", failing)
    assert voice_service.synthesize("另一段文本", "zh_CN", rate=0.8) == ""


def test_synthesize_repairs_legacy_wrong_extension(monkeypatch, tmp_path):
    """历史缓存是「WAV 内容 + .mp3 后缀」：命中时改名，不再按错误 MIME 发出去。"""
    monkeypatch.setattr("app.services.voice_service.settings.dashscope_api_key", "sk-test")
    monkeypatch.setattr("app.services.voice_service.settings.upload_dir", str(tmp_path))
    monkeypatch.setattr("app.services.voice_service.settings.api_prefix", "/api/v1")
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir(parents=True)
    base = _cache_base("找到电饭煲了")
    (tts_dir / f"{base}.mp3").write_bytes(_wav_bytes())
    monkeypatch.setattr(
        "app.services.voice_service.llm_client.synthesize_speech",
        lambda *a, **k: pytest.fail("命中缓存不应重新合成"),
    )

    url = voice_service.synthesize("找到电饭煲了", "zh_CN", rate=0.8)

    assert f"{base}.wav?" in url
    assert (tts_dir / f"{base}.wav").is_file()
    assert not (tts_dir / f"{base}.mp3").exists()


def test_synthesize_drops_corrupt_cache(monkeypatch, tmp_path):
    """5 字节的坏缓存（实测出现过 "audio"）必须删除并重新合成，不能永久命中。"""
    monkeypatch.setattr("app.services.voice_service.settings.dashscope_api_key", "sk-test")
    monkeypatch.setattr("app.services.voice_service.settings.upload_dir", str(tmp_path))
    monkeypatch.setattr("app.services.voice_service.settings.api_prefix", "/api/v1")
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir(parents=True)
    base = _cache_base("找到电饭煲了")
    (tts_dir / f"{base}.mp3").write_bytes(b"audio")
    calls = {"n": 0}

    def synth(*a, **k):
        calls["n"] += 1
        return _wav_bytes()

    monkeypatch.setattr("app.services.voice_service.llm_client.synthesize_speech", synth)

    url = voice_service.synthesize("找到电饭煲了", "zh_CN", rate=0.8)

    assert calls["n"] == 1
    assert f"{base}.wav?" in url


def test_synthesize_never_caches_non_audio_bytes(monkeypatch, tmp_path):
    """上游返回 JSON 报错/空字节时不能落盘：否则这段文本永远播不出来。"""
    monkeypatch.setattr("app.services.voice_service.settings.dashscope_api_key", "sk-test")
    monkeypatch.setattr("app.services.voice_service.settings.upload_dir", str(tmp_path))
    monkeypatch.setattr("app.services.voice_service.settings.api_prefix", "/api/v1")
    monkeypatch.setattr(
        "app.services.voice_service.llm_client.synthesize_speech",
        lambda *a, **k: b'{"code":"InvalidApiKey"}',
    )

    assert voice_service.synthesize("找到电饭煲了", "zh_CN", rate=0.8) == ""
    assert not (tmp_path / "tts").exists() or not any((tmp_path / "tts").iterdir())
