"""静态路由 3D 白名单测试：.glb 能通过签名访问，非白名单扩展名仍被拒。

背景：uploads 目录第 7 批安全改造后改走 HMAC 签名路由，路由按扩展名白名单
映射 Content-Type。白名单原先只有图片格式 —— 3D 模型（.glb）会被 403
「不支持的文件类型」直接拦掉，前端拿不到模型文件。这里用真实 TestClient
（真实签名校验 + 真实路径穿越防护）坐实修复。
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


def test_static_route_serves_glb_with_model_mime(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    target = tmp_path / "uploads" / "items" / "7" / "models" / "model.glb"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"glTF" + b"\x00" * 32)

    resp = client.get(_static_url("items/7/models/model.glb"))

    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "model/gltf-binary"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.content.startswith(b"glTF")


def test_static_route_serves_gltf_json_mime(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    target = tmp_path / "uploads" / "items" / "8" / "models" / "model.gltf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"asset":{"version":"2.0"}}')

    resp = client.get(_static_url("items/8/models/model.gltf"))

    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "model/gltf+json"


def test_static_route_still_rejects_unknown_extension(tmp_path, monkeypatch):
    """白名单扩容不能变成放行一切：非白名单扩展名仍然 403。"""
    client = _client(tmp_path, monkeypatch)
    target = tmp_path / "uploads" / "secret.txt"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"hello")

    resp = client.get(_static_url("secret.txt"))

    assert resp.status_code == 403
    assert "不支持的文件类型" in resp.json()["message"]


def test_static_route_still_requires_signature(tmp_path, monkeypatch):
    """签名校验不受本次改动影响：未签名仍 400、坏签名仍 403。"""
    client = _client(tmp_path, monkeypatch)
    target = tmp_path / "uploads" / "items" / "7" / "models" / "model.glb"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"glTF")

    unsigned = f"{settings.api_prefix}/static/items/7/models/model.glb"
    assert client.get(unsigned).status_code == 400
    assert client.get(f"{unsigned}?exp=1&sig=forged").status_code == 403
    assert client.get(_static_url("items/7/models/model.glb")).status_code == 200
