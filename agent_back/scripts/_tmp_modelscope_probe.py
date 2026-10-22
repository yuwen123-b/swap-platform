"""【一次性探测脚本】摸清魔搭 ModelScope API-Inference 对 Qwen-Image-Edit 的正确调用方式。

已知：OpenAI 兼容的 POST /v1/images/edits 返回 404 page not found → 该端点不存在。
本脚本逐个试真实存在的图像端点，找出可行路径。
"""
import base64
import json
import sys
import time
from pathlib import Path

import requests

LOG = Path(__file__).resolve().parent / "_pano_test" / "probe_log.txt"
_OUT = []


def print(*args, **kw):  # noqa: A001
    """同时写控制台与日志文件，避免 tail 截断丢信息。"""
    import builtins
    line = " ".join(str(a) for a in args)
    _OUT.append(line)
    builtins.print(line, **kw)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text("\n".join(_OUT), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings  # noqa: E402

BASE = settings.modelscope_api_url.rstrip("/")          # https://api-inference.modelscope.cn/v1
ROOT = BASE[: -len("/v1")] if BASE.endswith("/v1") else BASE
KEY = settings.modelscope_api_key
MODEL = settings.image_model                            # Qwen/Qwen-Image-Edit-2511
SRC = Path(__file__).resolve().parent / "_pano_test" / "source_camera.jpg"

H_JSON = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def show(title, resp):
    print(f"\n--- {title} ---")
    print(f"HTTP {resp.status_code}")
    body = resp.text or ""
    print(body[:600].replace("\n", " ")[:600])
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return None


def main():
    print(f"BASE = {BASE}")
    print(f"SRC  = {SRC}  exists={SRC.exists()}")
    if not SRC.exists():
        print("缺少测试原图")
        return

    b64 = "data:image/jpeg;base64," + base64.b64encode(SRC.read_bytes()).decode()
    print(f"原图 base64 长度 = {len(b64):,}")

    sess = requests.Session()

    # 0) 列出模型 / 探活
    try:
        r = sess.get(f"{BASE}/models", headers={"Authorization": f"Bearer {KEY}"}, timeout=20)
        show("GET /v1/models", r)
    except Exception as exc:  # noqa: BLE001
        print("GET /v1/models 异常:", exc)

    # 1) 同步 images/generations（OpenAI 风格）
    for name, payload in [
        ("同步 images/generations（纯文本）", {"model": MODEL, "prompt": "一只猫", "n": 1}),
        ("同步 images/generations（带 image 字段）", {"model": MODEL, "prompt": "把图片向左旋转90度", "image": b64, "n": 1}),
    ]:
        try:
            r = sess.post(f"{BASE}/images/generations", headers=H_JSON, json=payload, timeout=60)
            show(name, r)
        except Exception as exc:  # noqa: BLE001
            print(f"\n--- {name} ---\n异常: {exc}")

    # 2) 异步任务模式（ModelScope 原生）
    print("\n=== 异步任务模式 ===")
    for name, url, payload, extra in [
        (
            "异步 images/generations",
            f"{BASE}/images/generations",
            {"model": MODEL, "prompt": "将图片中的物品向左旋转 90 度，保持外观、颜色、材质、背景完全一致，只改变视角", "image_url": b64},
            {"X-ModelScope-Async-Mode": "true"},
        ),
        (
            "异步 /images/edits",
            f"{BASE}/images/edits",
            {"model": MODEL, "prompt": "将图片中的物品向左旋转 90 度", "image_url": b64},
            {"X-ModelScope-Async-Mode": "true"},
        ),
    ]:
        try:
            r = sess.post(url, headers={**H_JSON, **extra}, json=payload, timeout=60)
            data = show(name, r)
            task_id = (data or {}).get("task_id") or (data or {}).get("output", {}).get("task_id")
            if task_id:
                print(f"  提交成功，task_id={task_id}，开始轮询…")
                for i in range(60):
                    time.sleep(3)
                    q = sess.get(
                        f"{BASE}/tasks/{task_id}",
                        headers={"Authorization": f"Bearer {KEY}", "X-ModelScope-Task-Type": "image_generation"},
                        timeout=20,
                    )
                    if q.status_code >= 400:
                        print(f"  轮询 HTTP {q.status_code}: {q.text[:200]}")
                        break
                    body = q.json()
                    st = body.get("task_status")
                    print(f"  [{i}] {st}")
                    if st == "SUCCEED" or st == "SUCCEEDED":
                        urls = body.get("output", {}).get("image_urls") or body.get("output", {}).get("images")
                        print("  结果:", json.dumps(urls, ensure_ascii=False)[:400])
                        if urls:
                            u = urls[0] if isinstance(urls[0], str) else urls[0].get("url")
                            img = sess.get(u, timeout=60)
                            dest = SRC.parent / "modelscope_async_left.jpg"
                            dest.write_bytes(img.content)
                            print(f"  已保存 -> {dest}  {len(img.content):,} bytes")
                        break
                    if st in ("FAILED", "FAIL"):
                        print("  失败:", json.dumps(body, ensure_ascii=False)[:400])
                        break
        except Exception as exc:  # noqa: BLE001
            print(f"\n--- {name} ---\n异常: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
