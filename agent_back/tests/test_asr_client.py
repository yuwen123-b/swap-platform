"""ASR 客户端测试：qwen3-asr-flash 主链路、音频魔数识别、三级降级顺序。

背景（2026-10-20 实测）：魔搭网关无音频端点（/v1/audio/* 全 404），
paraformer-v2 文件转写在本账号返回 SERVER_ERROR，唯一可用的是
qwen3-asr-flash 多模态接口 + base64 直传。本文件锁定该链路的契约。
"""
import base64

import pytest

from app.services import llm_client


def _write(tmp_path, name, head: bytes, size: int = 64):
    p = tmp_path / name
    p.write_bytes(head + b"\x00" * max(0, size - len(head)))
    return p


# ---------- 1. 音频格式：必须按真实字节判断，不看扩展名 ----------

def test_audio_format_wav(tmp_path):
    p = _write(tmp_path, "a.webm", b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE")
    # 文件名叫 .webm，但内容是 WAV —— 以内容为准
    assert llm_client.audio_format(p) == "wav"


def test_audio_format_webm(tmp_path):
    p = _write(tmp_path, "a.webm", b"\x1a\x45\xdf\xa3")
    assert llm_client.audio_format(p) == "webm"


def test_audio_format_mp4_from_ftyp(tmp_path):
    """Chrome 新版 MediaRecorder 产出 audio/mp4，文件名却常是 .webm。"""
    p = _write(tmp_path, "a.webm", b"\x00\x00\x00\x20ftypiso5")
    assert llm_client.audio_format(p) == "mp4"


def test_audio_format_m4a_brand(tmp_path):
    p = _write(tmp_path, "a.m4a", b"\x00\x00\x00\x20ftypM4A ")
    assert llm_client.audio_format(p) == "m4a"


def test_audio_format_mp3_with_id3(tmp_path):
    p = _write(tmp_path, "a.mp3", b"ID3")
    assert llm_client.audio_format(p) == "mp3"


def test_audio_format_unknown_falls_back_to_wav(tmp_path):
    p = _write(tmp_path, "a.bin", b"\xde\xad\xbe\xef")
    assert llm_client.audio_format(p) == "wav"


# ---------- 2. qwen3-asr-flash 请求与响应解析 ----------

class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or ""

    def json(self):
        return self._payload


def test_qwen_asr_posts_base64_and_parses(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return _Resp(payload={"output": {"choices": [
            {"message": {"content": [{"text": " 喂喂喂。"}]}},
        ]}})

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    monkeypatch.setattr(llm_client.settings, "dashscope_api_key", "sk-test")

    audio = _write(tmp_path, "rec.webm", b"\x1a\x45\xdf\xa3")
    text = llm_client._transcribe_qwen_asr(audio)

    assert text == "喂喂喂。"
    audio_part = captured["payload"]["input"]["messages"][0]["content"][0]["audio"]
    prefix = f"data:audio/webm;base64,"
    assert audio_part.startswith(prefix)
    assert base64.b64decode(audio_part[len(prefix):]) == audio.read_bytes()
    assert captured["payload"]["model"] == llm_client.settings.llm_asr_model
    assert captured["payload"]["parameters"]["asr_options"]["enable_lid"] is True
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_qwen_asr_raises_on_http_error(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_client.requests, "post",
                        lambda *a, **k: _Resp(status_code=400, text='{"code":"InvalidParameter"}'))
    monkeypatch.setattr(llm_client.settings, "dashscope_api_key", "sk-test")
    with pytest.raises(RuntimeError, match="HTTP 400"):
        llm_client._transcribe_qwen_asr(_write(tmp_path, "a.webm", b"\x1a\x45\xdf\xa3"))


def test_qwen_asr_raises_on_empty_text(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_client.requests, "post",
                        lambda *a, **k: _Resp(payload={"output": {"choices": []}}))
    monkeypatch.setattr(llm_client.settings, "dashscope_api_key", "sk-test")
    with pytest.raises(RuntimeError, match="识别结果为空"):
        llm_client._transcribe_qwen_asr(_write(tmp_path, "a.webm", b"\x1a\x45\xdf\xa3"))


# ---------- 3. 三级降级顺序 ----------

def test_transcribe_prefers_qwen(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_client.settings, "asr_provider", "dashscope")
    called = {"para": 0}

    monkeypatch.setattr(llm_client, "_transcribe_qwen_asr", lambda p: "我想换电饭煲")
    monkeypatch.setattr(llm_client, "_transcribe_dashscope",
                        lambda url: called.__setitem__("para", 1) or "不该走到这里")

    assert llm_client.transcribe_audio(_write(tmp_path, "a.webm", b"\x1a\x45\xdf\xa3"),
                                       "https://example.com/a.webm") == "我想换电饭煲"
    assert called["para"] == 0, "主链路成功时不应触发 paraformer"


def test_transcribe_falls_back_to_paraformer_with_url(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_client.settings, "asr_provider", "dashscope")

    def boom(_p):
        raise RuntimeError("模型未开通")

    monkeypatch.setattr(llm_client, "_transcribe_qwen_asr", boom)
    monkeypatch.setattr(llm_client, "_transcribe_dashscope", lambda url: "兜底识别")
    assert llm_client.transcribe_audio(_write(tmp_path, "a.webm", b"\x1a\x45\xdf\xa3"),
                                       "https://example.com/a.webm") == "兜底识别"


def test_transcribe_reports_all_failure_reasons(monkeypatch, tmp_path):
    """全部失败时必须把原因串起来抛出，前端/日志能直接定位。"""
    monkeypatch.setattr(llm_client.settings, "asr_provider", "dashscope")
    monkeypatch.setattr(llm_client.settings, "modelscope_api_key", "")

    def boom(_p):
        raise RuntimeError("模型未开通")

    monkeypatch.setattr(llm_client, "_transcribe_qwen_asr", boom)
    with pytest.raises(RuntimeError) as exc:
        llm_client.transcribe_audio(_write(tmp_path, "a.webm", b"\x1a\x45\xdf\xa3"), "")
    msg = str(exc.value)
    assert "qwen3-asr-flash" in msg and "PUBLIC_BASE_URL" in msg


def test_transcribe_skips_modelscope_when_provider_is_dashscope(monkeypatch, tmp_path):
    """ASR_PROVIDER=dashscope 时不应再去撞魔搭的 404（省一次往返）。"""
    monkeypatch.setattr(llm_client.settings, "asr_provider", "dashscope")
    monkeypatch.setattr(llm_client.settings, "modelscope_api_key", "ms-test")
    called = {"ms": 0}

    def ms(_p):
        called["ms"] += 1
        return "魔搭结果"

    monkeypatch.setattr(llm_client, "_transcribe_modelscope", ms)
    monkeypatch.setattr(llm_client, "_transcribe_qwen_asr", lambda p: "百炼结果")
    result = llm_client.transcribe_audio(_write(tmp_path, "a.webm", b"\x1a\x45\xdf\xa3"), "")
    assert result == "百炼结果"
    assert called["ms"] == 0
