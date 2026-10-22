"""3D 生成服务测试：provider 分派、混元 TokenHub 链路、GLB 落盘校验、错误归一化。

与 `test_model_api.py`（接口层）互补——这里测的是 service 层的真实逻辑：
提交参数、轮询状态机、失败原因落库、下载产物校验。全部 mock，不发真实网络请求。
"""
import base64
import os

import pytest
from conftest import FakeCursor, make_connection
from PIL import Image

from app.services import three_d_service as svc

# ============================================================
# 通用桩：假 HTTP 响应
# ============================================================


class _Resp:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or (str(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _hunyuan_env(monkeypatch, **overrides):
    """把 settings 固定成混元可用状态（避免依赖本机 .env）。"""
    s = svc.settings
    monkeypatch.setattr(s, "model_3d_enabled", True)
    monkeypatch.setattr(s, "model_3d_provider", "hunyuan")
    monkeypatch.setattr(s, "tokenhub_api_key", "sk-test")
    monkeypatch.setattr(s, "tokenhub_api_url", "https://tokenhub.tencentmaas.com")
    monkeypatch.setattr(s, "hunyuan_3d_model", "hy-3d-express")
    monkeypatch.setattr(s, "hunyuan_3d_pbr", False)
    monkeypatch.setattr(s, "hunyuan_3d_timeout_seconds", 300)
    monkeypatch.setattr(s, "hunyuan_3d_poll_interval_seconds", 0.0)
    monkeypatch.setattr(s, "hunyuan_3d_max_image_bytes", 6 * 1024 * 1024)
    for key, value in overrides.items():
        monkeypatch.setattr(s, key, value)
    return s


def _jpeg(path, size=(64, 64), color=(120, 160, 200)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "JPEG", quality=90)
    return path


def _glb_bytes(tail: bytes = b"\x00" * 512) -> bytes:
    """最小可用 GLB 头：magic(b'glTF') + version + length。"""
    return b"glTF" + (2).to_bytes(4, "little") + (12 + len(tail)).to_bytes(4, "little") + tail


# ============================================================
# provider 解析与前置校验
# ============================================================
def test_current_provider_defaults_and_normalizes(monkeypatch):
    monkeypatch.setattr(svc.settings, "model_3d_provider", "  HuNyUaN  ")
    assert svc.current_provider() == "hunyuan"
    monkeypatch.setattr(svc.settings, "model_3d_provider", "")
    assert svc.current_provider() == "hunyuan"


def test_require_ready_disabled(monkeypatch):
    monkeypatch.setattr(svc.settings, "model_3d_enabled", False)
    with pytest.raises(RuntimeError, match="未开启"):
        svc._require_ready()


def test_require_ready_hunyuan_needs_tokenhub_key(monkeypatch):
    _hunyuan_env(monkeypatch, tokenhub_api_key="")
    with pytest.raises(RuntimeError, match="TOKENHUB_API_KEY"):
        svc._require_ready()


def test_require_ready_hunyuan_needs_gateway_url(monkeypatch):
    _hunyuan_env(monkeypatch, tokenhub_api_url="")
    with pytest.raises(RuntimeError, match="TOKENHUB_API_URL"):
        svc._require_ready()


def test_require_ready_hunyuan_does_not_need_public_base_url(monkeypatch):
    """混元走 base64 上传，PUBLIC_BASE_URL 未配置也必须能通过前置校验。"""
    _hunyuan_env(monkeypatch)
    monkeypatch.setattr(svc.settings, "public_base_url", "")
    monkeypatch.setattr(svc.settings, "dashscope_api_key", "")
    svc._require_ready()


def test_require_ready_tripo_needs_dashscope_and_public_url(monkeypatch):
    monkeypatch.setattr(svc.settings, "model_3d_enabled", True)
    monkeypatch.setattr(svc.settings, "model_3d_provider", "tripo")
    monkeypatch.setattr(svc.settings, "dashscope_api_key", "")
    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        svc._require_ready()
    monkeypatch.setattr(svc.settings, "dashscope_api_key", "sk-ds")
    monkeypatch.setattr(svc.settings, "public_base_url", "")
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        svc._require_ready()


def test_require_ready_unknown_provider(monkeypatch):
    monkeypatch.setattr(svc.settings, "model_3d_enabled", True)
    monkeypatch.setattr(svc.settings, "model_3d_provider", "midjourney")
    with pytest.raises(RuntimeError, match="未知的 3D 服务商"):
        svc._require_ready()


# ============================================================
# URL 与错误归一化
# ============================================================
def test_hunyuan_url_handles_trailing_slash(monkeypatch):
    _hunyuan_env(monkeypatch, tokenhub_api_url="https://tokenhub.tencentmaas.com/")
    assert svc._hunyuan_url("submit") == "https://tokenhub.tencentmaas.com/v1/api/3d/submit"
    assert svc._hunyuan_url("query") == "https://tokenhub.tencentmaas.com/v1/api/3d/query"


@pytest.mark.parametrize(
    "code,message,fragment",
    [
        ("FailedOperation.ConcurrencyLimit", "并发超限", "同时只能处理 1 个任务"),
        ("FailedOperation.Arrearage", "账户欠费", "欠费"),
        ("AuthFailure", "Unauthorized", "TOKENHUB_API_KEY"),
        ("FailedOperation.ContentRisk", "risk control", "内容风控"),
        ("FailedOperation.JobNotFound", "任务不存在", "任务不存在或已过期"),
    ],
)
def test_hunyuan_friendly_maps_known_errors(code, message, fragment):
    assert fragment in svc._hunyuan_friendly(code, message)


def test_hunyuan_friendly_keeps_raw_for_unknown():
    text = svc._hunyuan_friendly("FailedOperation.Weird", "something new")
    assert "混元 3D 生成失败" in text
    assert "FailedOperation.Weird" in text


def test_hunyuan_error_flattens_envelope():
    assert svc._hunyuan_error(
        {"error": {"code": "AuthFailure", "message": "bad key"}}
    ) == "AuthFailure bad key"
    assert svc._hunyuan_error({"error": "boom"}) == "boom"
    assert svc._hunyuan_error({}) == ""


# ============================================================
# 图片 base64 与压缩
# ============================================================
def test_encode_image_base64_small_file(monkeypatch, tmp_path):
    _hunyuan_env(monkeypatch)
    path = _jpeg(tmp_path / "a.jpg")
    encoded = svc._encode_image_base64(path)
    assert base64.b64decode(encoded) == path.read_bytes()


def test_encode_image_base64_shrinks_oversized(monkeypatch, tmp_path):
    """超过 6MB 上限时必须自动降质/缩边，而不是直接把原图丢上去吃 400。"""
    limit = 200_000
    _hunyuan_env(monkeypatch, hunyuan_3d_max_image_bytes=limit)
    # 纯噪声图（JPEG 最难压）→ 保证初次编码必然超限
    raw = os.urandom(1000 * 1000 * 3)
    path = tmp_path / "noise.jpg"
    Image.frombytes("RGB", (1000, 1000), raw).save(path, "JPEG", quality=100)
    assert path.stat().st_size > limit

    decoded = base64.b64decode(svc._encode_image_base64(path))
    assert len(decoded) <= limit
    assert decoded[:2] == b"\xff\xd8"  # 仍是合法 JPEG


def test_shrink_jpeg_raises_when_impossible(monkeypatch, tmp_path):
    _hunyuan_env(monkeypatch, hunyuan_3d_max_image_bytes=1)
    path = _jpeg(tmp_path / "a.jpg")
    with pytest.raises(RuntimeError, match="过大"):
        svc._shrink_jpeg(path, 1)


# ============================================================
# 提交
# ============================================================
def test_hunyuan_submit_success_payload(monkeypatch, tmp_path):
    _hunyuan_env(monkeypatch)
    path = _jpeg(tmp_path / "a.jpg")
    captured = {}

    def _post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp({"id": "14721", "status": "queued"})

    monkeypatch.setattr(svc.requests, "post", _post)
    job_id = svc._hunyuan_submit(path)

    assert job_id == "14721"
    assert captured["url"].endswith("/v1/api/3d/submit")
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    body = captured["json"]
    # 三选一：只传 image_base64，绝不与 prompt 同时出现
    assert "prompt" not in body
    assert base64.b64decode(body["image_base64"]) == path.read_bytes()
    # 默认返回 obj，前端只吃 glb → 必须显式指定；且真机只认大写
    assert body["result_format"] == "GLB"
    assert body["enable_pbr"] is False
    assert body["model"] == "hy-3d-express"


def test_hunyuan_submit_passes_pbr_switch(monkeypatch, tmp_path):
    _hunyuan_env(monkeypatch, hunyuan_3d_pbr=True)
    captured = {}

    def _post(url, headers=None, json=None, timeout=None):
        captured.update(json)
        return _Resp({"id": "1", "status": "queued"})

    monkeypatch.setattr(svc.requests, "post", _post)
    svc._hunyuan_submit(_jpeg(tmp_path / "a.jpg"))
    assert captured["enable_pbr"] is True


def test_hunyuan_submit_http_error(monkeypatch, tmp_path):
    _hunyuan_env(monkeypatch)
    monkeypatch.setattr(
        svc.requests, "post", lambda *a, **k: _Resp(None, status_code=500, text="boom")
    )
    with pytest.raises(RuntimeError, match="提交失败 HTTP 500"):
        svc._hunyuan_submit(_jpeg(tmp_path / "a.jpg"))


def test_hunyuan_submit_error_envelope_is_normalized(monkeypatch, tmp_path):
    _hunyuan_env(monkeypatch)
    payload = {"error": {"code": "FailedOperation.ConcurrencyLimit", "message": "busy"}}
    monkeypatch.setattr(svc.requests, "post", lambda *a, **k: _Resp(payload))
    with pytest.raises(RuntimeError, match="同时只能处理 1 个任务"):
        svc._hunyuan_submit(_jpeg(tmp_path / "a.jpg"))


def test_hunyuan_submit_missing_id(monkeypatch, tmp_path):
    _hunyuan_env(monkeypatch)
    monkeypatch.setattr(svc.requests, "post", lambda *a, **k: _Resp({"status": "queued"}))
    with pytest.raises(RuntimeError, match="缺少 id"):
        svc._hunyuan_submit(_jpeg(tmp_path / "a.jpg"))


def test_hunyuan_submit_non_json_body(monkeypatch, tmp_path):
    _hunyuan_env(monkeypatch)
    monkeypatch.setattr(
        svc.requests, "post", lambda *a, **k: _Resp(None, text="<html>502</html>")
    )
    with pytest.raises(RuntimeError, match="返回非 JSON"):
        svc._hunyuan_submit(_jpeg(tmp_path / "a.jpg"))


# ============================================================
# 轮询
# ============================================================
def test_hunyuan_wait_returns_data_on_completed(monkeypatch):
    _hunyuan_env(monkeypatch)
    seq = [_Resp({"status": "queued"}), _Resp({"status": "in_progress"}),
           _Resp({"status": "completed", "data": [{"type": "glb", "url": "u"}]})]
    monkeypatch.setattr(svc.requests, "post", lambda *a, **k: seq.pop(0))
    assert svc._hunyuan_wait("1")[0]["url"] == "u"


def test_hunyuan_wait_raises_on_failed(monkeypatch):
    _hunyuan_env(monkeypatch)
    monkeypatch.setattr(svc.requests, "post", lambda *a, **k: _Resp({"status": "failed"}))
    with pytest.raises(RuntimeError, match="执行失败"):
        svc._hunyuan_wait("1")


def test_hunyuan_wait_raises_on_error_envelope(monkeypatch):
    _hunyuan_env(monkeypatch)
    payload = {"error": {"code": "FailedOperation.JobNotFound", "message": "任务不存在。"}}
    monkeypatch.setattr(svc.requests, "post", lambda *a, **k: _Resp(payload))
    with pytest.raises(RuntimeError, match="任务不存在或已过期"):
        svc._hunyuan_wait("1")


def test_hunyuan_wait_timeout(monkeypatch):
    """超时必须报「超时」并带上最后状态，而不是无限转圈。"""
    _hunyuan_env(monkeypatch, hunyuan_3d_timeout_seconds=0)
    monkeypatch.setattr(svc.requests, "post", lambda *a, **k: _Resp({"status": "in_progress"}))
    with pytest.raises(RuntimeError, match="超时"):
        svc._hunyuan_wait("1")


def test_hunyuan_wait_completed_without_data(monkeypatch):
    _hunyuan_env(monkeypatch)
    monkeypatch.setattr(svc.requests, "post", lambda *a, **k: _Resp({"status": "completed"}))
    with pytest.raises(RuntimeError, match="未返回模型文件"):
        svc._hunyuan_wait("1")


def test_hunyuan_wait_query_http_error(monkeypatch):
    _hunyuan_env(monkeypatch)
    monkeypatch.setattr(
        svc.requests, "post", lambda *a, **k: _Resp(None, status_code=502, text="bad gateway")
    )
    with pytest.raises(RuntimeError, match="查询失败 HTTP 502"):
        svc._hunyuan_wait("1")


# ============================================================
# 结果解析
# ============================================================
def test_extract_glb_url_prefers_glb_type():
    data = [{"type": "obj", "url": "o"}, {"type": "glb", "url": "g"}]
    assert svc._hunyuan_extract_glb_url(data) == "g"


def test_extract_glb_url_falls_back_to_first_url():
    assert svc._hunyuan_extract_glb_url([{"type": "unknown", "url": "only"}]) == "only"


def test_extract_glb_url_missing():
    with pytest.raises(RuntimeError, match="缺少 GLB 下载地址"):
        svc._hunyuan_extract_glb_url([{"type": "obj"}])


# ============================================================
# GLB 下载与魔数校验
# ============================================================
class _StreamResp:
    def __init__(self, chunks, status_code=200):
        self._chunks = chunks
        self.status_code = status_code

    def iter_content(self, chunk_size=0):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_download_model_writes_glb(monkeypatch, tmp_path):
    monkeypatch.setattr(
        svc.requests, "get", lambda *a, **k: _StreamResp([_glb_bytes()])
    )
    dest = tmp_path / "model.glb"
    size = svc._download_model("http://x/model.glb", dest)
    assert size == dest.stat().st_size
    assert dest.read_bytes()[:4] == b"glTF"
    assert not dest.with_suffix(".glb.part").exists()


def test_download_model_rejects_non_glb(monkeypatch, tmp_path):
    """混元 result_format 若未生效会返回 obj 文本 → 必须早期失败而不是让前端白屏。"""
    monkeypatch.setattr(svc.requests, "get", lambda *a, **k: _StreamResp([b"# OBJ\nv 0 0 0\n"]))
    dest = tmp_path / "model.glb"
    with pytest.raises(RuntimeError, match="不是合法的 GLB"):
        svc._download_model("http://x/model.glb", dest)
    assert not dest.exists()
    assert not dest.with_suffix(".glb.part").exists()


def test_download_model_rejects_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(svc.requests, "get", lambda *a, **k: _StreamResp([]))
    with pytest.raises(RuntimeError, match="下载结果为空"):
        svc._download_model("http://x/model.glb", tmp_path / "model.glb")


def test_download_model_http_error(monkeypatch, tmp_path):
    monkeypatch.setattr(svc.requests, "get", lambda *a, **k: _StreamResp([b"x"], status_code=403))
    with pytest.raises(RuntimeError, match="下载失败 HTTP 403"):
        svc._download_model("http://x/model.glb", tmp_path / "model.glb")


# ============================================================
# generate_3d_model 分派
# ============================================================
def test_generate_dispatches_to_hunyuan(monkeypatch, tmp_path):
    _hunyuan_env(monkeypatch)
    monkeypatch.setattr(svc, "_load_source_url", lambda item_id: "items/9/a.jpg")
    monkeypatch.setattr(svc, "ensure_local_jpeg", lambda url, dest=None: _jpeg(tmp_path / "s.jpg"))
    monkeypatch.setattr(svc, "_hunyuan_submit", lambda p: "job-1")
    monkeypatch.setattr(svc, "_hunyuan_wait", lambda jid: [{"type": "glb", "url": "u"}])

    def _download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_glb_bytes())
        return dest.stat().st_size

    monkeypatch.setattr(svc, "_download_model", _download)
    written = {}
    monkeypatch.setattr(
        svc, "_update_status", lambda item_id, status, url=None, error=None: written.update(
            {"status": status, "url": url}
        )
    )
    monkeypatch.setattr(svc, "models_dir", lambda item_id: tmp_path)

    result = svc.generate_3d_model(9)
    assert result["provider"] == "hunyuan"
    assert result["task_id"] == "job-1"
    assert result["status"] == "ready"
    assert written["status"] == "ready"
    # DB 只存不带签名的相对路径
    assert written["url"] == svc.model_url(9)
    assert "?" not in written["url"]


def test_generate_wraps_image_source_error(monkeypatch, tmp_path):
    from app.services.image_utils import ImageSourceError

    _hunyuan_env(monkeypatch)
    monkeypatch.setattr(svc, "_load_source_url", lambda item_id: "items/9/a.webp")

    def _boom(url, dest=None):
        raise ImageSourceError("物品图片文件不存在")

    monkeypatch.setattr(svc, "ensure_local_jpeg", _boom)
    monkeypatch.setattr(svc, "models_dir", lambda item_id: tmp_path)
    with pytest.raises(RuntimeError, match="物品原图无法用于 3D 生成"):
        svc.generate_3d_model(9)


def test_generate_rejects_unknown_provider_after_ready(monkeypatch, tmp_path):
    """前置校验能过、但分派阶段遇到非法 provider 也不能静默成功。"""
    _hunyuan_env(monkeypatch, model_3d_provider="hunyuan")
    monkeypatch.setattr(svc, "_load_source_url", lambda item_id: "items/9/a.jpg")
    monkeypatch.setattr(svc, "ensure_local_jpeg", lambda url, dest=None: _jpeg(tmp_path / "s.jpg"))
    monkeypatch.setattr(svc, "models_dir", lambda item_id: tmp_path)
    # 绕过 _require_ready 的枚举校验，模拟运行期配置被改坏
    monkeypatch.setattr(svc, "_require_ready", lambda: None)
    monkeypatch.setattr(svc, "current_provider", lambda: "foo")
    with pytest.raises(RuntimeError, match="未知的 3D 服务商"):
        svc.generate_3d_model(9)


def test_generate_tripo_branch_uses_public_url(monkeypatch, tmp_path):
    """回退分支必须仍然走「签名公网 URL」老路径（行为与切换前一致）。"""
    monkeypatch.setattr(svc.settings, "model_3d_enabled", True)
    monkeypatch.setattr(svc.settings, "model_3d_provider", "tripo")
    monkeypatch.setattr(svc.settings, "dashscope_api_key", "sk-ds")
    monkeypatch.setattr(svc.settings, "public_base_url", "https://pub.example")
    monkeypatch.setattr(svc.settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(svc.settings, "api_prefix", "/api/v1")

    uploaded = _jpeg(tmp_path / "items" / "9" / "models" / "source.jpg")
    monkeypatch.setattr(svc, "_load_source_url", lambda item_id: "x")
    monkeypatch.setattr(svc, "ensure_local_jpeg", lambda url, dest=None: uploaded)

    captured = {}
    monkeypatch.setattr(
        svc, "_tripo_submit_task", lambda u: captured.setdefault("url", u) or "t1"
    )
    monkeypatch.setattr(
        svc, "_tripo_wait_task",
        lambda tid: {"results": [{"pbr_model_url": "https://cdn/glb"}]},
    )

    def _download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_glb_bytes())
        return dest.stat().st_size

    monkeypatch.setattr(svc, "_download_model", _download)
    monkeypatch.setattr(svc, "_update_status", lambda *a, **k: None)

    result = svc.generate_3d_model(9)
    assert result["provider"] == "tripo"
    # 回退分支仍依赖「签名公网 URL」：必须带 PUBLIC_BASE_URL 前缀与实时签名
    assert captured["url"].startswith("https://pub.example/api/v1/static/")
    assert "exp=" in captured["url"] and "sig=" in captured["url"]


# ============================================================
# run_generate / get_model
# ============================================================
def test_run_generate_writes_failure_reason(monkeypatch):
    """失败原因必须落库（前端唯一的解释来源），且 run_generate 不向外抛。"""
    calls = []
    monkeypatch.setattr(
        svc, "_update_status",
        lambda item_id, status, url=None, error=None: calls.append((status, error)),
    )
    monkeypatch.setattr(
        svc, "generate_3d_model",
        lambda item_id: (_ for _ in ()).throw(RuntimeError("混元 3D 生成失败：boom")),
    )
    svc.run_generate(9)
    assert calls[0][0] == "generating"
    assert calls[1][0] == "failed"
    assert "boom" in calls[1][1]


def test_run_generate_ignores_status_write_failure(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(svc, "_update_status", _boom)
    monkeypatch.setattr(
        svc, "generate_3d_model", lambda item_id: pytest.fail("置位失败就不该继续生成")
    )
    svc.run_generate(9)  # 不抛异常


def _patch_get_model(monkeypatch, row, *, update=None):
    cursor = FakeCursor(rows=[row])
    monkeypatch.setattr(svc, "connection", make_connection(cursor))
    if update is not None:
        monkeypatch.setattr(svc, "_update_status", update)
    return cursor


def test_get_model_ready_returns_signed_url(monkeypatch):
    monkeypatch.setattr(svc, "sign_model_url", lambda u: f"{u}?signed")
    _patch_get_model(monkeypatch, {
        "model_status": "ready", "model_url": "/api/v1/static/items/9/models/model.glb",
        "model_generated_at": None, "model_error": None,
    })
    out = svc.get_model(9)
    assert out["model_status"] == "ready"
    assert out["model_url"].endswith("?signed")
    assert out["model_error"] is None


def test_get_model_hides_error_unless_failed(monkeypatch):
    _patch_get_model(monkeypatch, {
        "model_status": "ready", "model_url": "/x", "model_generated_at": None,
        "model_error": "上一轮的旧错因",
    })
    assert svc.get_model(9)["model_error"] is None


def test_get_model_returns_error_when_failed(monkeypatch):
    _patch_get_model(monkeypatch, {
        "model_status": "failed", "model_url": None, "model_generated_at": None,
        "model_error": "混元 3D 生成失败：xxx",
    })
    out = svc.get_model(9)
    assert out["model_url"] is None
    assert "混元 3D 生成失败" in out["model_error"]


def test_get_model_marks_stuck_generating_as_failed(monkeypatch):
    """后台线程随重启丢失时，读时兜底必须把卡死的 generating 判成 failed。"""
    from datetime import datetime, timedelta

    written = {}
    _patch_get_model(
        monkeypatch,
        {
            "model_status": "generating", "model_url": None,
            "model_generated_at": datetime.now() - timedelta(minutes=30),
            "model_error": None,
        },
        update=lambda item_id, status, url=None, error=None: written.update(
            {"status": status, "error": error}
        ),
    )
    out = svc.get_model(9)
    assert out["model_status"] == "failed"
    assert "未完成" in out["model_error"]
    assert written["status"] == "failed"


def test_get_model_missing_item(monkeypatch):
    _patch_get_model(monkeypatch, None)
    with pytest.raises(ValueError, match="物品不存在"):
        svc.get_model(404)
