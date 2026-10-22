"""静态路由音频白名单测试：TTS 播报音频必须能带签名取到，且 Content-Type 正确。

背景：助老模式「有时有声音、有时没声音」的根因之一就在这里 ——
/uploads/tts 下的音频走同一套 HMAC 签名路由，但白名单只有图片和 3D 模型，
.mp3/.wav 一律 403「不支持的文件类型」。前端 `<audio>` 必然 error，
只能永远退回浏览器合成，iOS 上又被自动播放策略拦掉。
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import sign_file_path


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def _static_url(relative: str) -> str:
    return f"{settings.api_prefix}/static/{relative}?{sign_file_path(relative)}"


@pytest.mark.parametrize(
    "name, mime",
    [
        ("abc.wav", "audio/wav"),
        ("abc.mp3", "audio/mpeg"),
        ("abc.m4a", "audio/mp4"),
        ("abc.ogg", "audio/ogg"),
    ],
)
def test_static_route_serves_audio_with_correct_mime(tmp_path, monkeypatch, name, mime):
    client = _client(tmp_path, monkeypatch)
    target = tmp_path / "uploads" / "tts" / name
    target.parent.mkdir(parents=True)
    target.write_bytes(b"RIFF0000WAVE")

    resp = client.get(_static_url(f"tts/{name}"))

    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == mime
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.content == b"RIFF0000WAVE"


def test_static_audio_still_requires_signature(tmp_path, monkeypatch):
    """放行音频扩展名不能变成「免签名直连」。"""
    client = _client(tmp_path, monkeypatch)
    target = tmp_path / "uploads" / "tts" / "abc.wav"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"RIFF0000WAVE")

    unsigned = f"{settings.api_prefix}/static/tts/abc.wav"
    assert client.get(unsigned).status_code == 400
    assert client.get(f"{unsigned}?exp=1&sig=forged").status_code == 403
    assert client.get(_static_url("tts/abc.wav")).status_code == 200
