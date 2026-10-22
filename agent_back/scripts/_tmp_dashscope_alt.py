"""【一次性验证】百炼侧还有哪些图像编辑路径可用。

E2: wanx2.1-imageedit 是否接受 base64 data URL（若可以，本地开发就不用 ngrok）
E3: 列出百炼可用模型，确认 qwen-image-edit 是否真的不存在
"""
import base64
import json
import sys
import time
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings  # noqa: E402

OUT = Path(__file__).resolve().parent / "_pano_test"
SRC = OUT / "source_camera.jpg"
KEY = settings.dashscope_api_key
PROMPT = "将图片中的物品向左旋转 90 度，保持物品的外观、颜色、材质、背景完全一致，只改变视角"

_lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "probe_dashscope_alt.txt").write_text("\n".join(_lines), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main():
    log(f"IMAGE_EDIT_API_URL = {settings.image_edit_api_url}")
    log(f"LLM_IMAGE_EDIT_MODEL = {settings.llm_image_edit_model}")
    log("")

    # E3: 模型列表
    log("=== E3 百炼可用模型（OpenAI 兼容列表）===")
    try:
        r = requests.get(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
            headers={"Authorization": f"Bearer {KEY}"},
            timeout=30,
        )
        log(f"HTTP {r.status_code}")
        if r.status_code == 200:
            ids = [m.get("id") for m in r.json().get("data", [])]
            img = [i for i in ids if any(k in (i or "").lower() for k in ("image", "wanx", "qwen-image", "edit"))]
            log(f"共 {len(ids)} 个模型；图像相关: {json.dumps(img, ensure_ascii=False)[:800]}")
    except Exception as exc:  # noqa: BLE001
        log(f"异常: {exc}")

    # E2: wanx2.1-imageedit + base64
    log("")
    log("=== E2 wanx2.1-imageedit 传 base64 data URL ===")
    if not SRC.exists():
        log("缺少原图")
        return
    b64 = "data:image/jpeg;base64," + base64.b64encode(SRC.read_bytes()).decode()
    payload = {
        "model": settings.llm_image_edit_model,
        "input": {"function": "description_edit", "prompt": PROMPT, "base_image_url": b64},
        "parameters": {"n": 1},
    }
    t0 = time.time()
    try:
        r = requests.post(
            settings.image_edit_api_url,
            headers={
                "Authorization": f"Bearer {KEY}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
            json=payload,
            timeout=60,
        )
        log(f"提交 HTTP {r.status_code} ({time.time()-t0:.1f}s)")
        log(r.text[:500])
        if r.status_code < 400:
            tid = r.json().get("output", {}).get("task_id")
            log(f"task_id={tid}")
            for i in range(30):
                time.sleep(4)
                q = requests.get(
                    settings.task_api_url.format(task_id=tid),
                    headers={"Authorization": f"Bearer {KEY}"},
                    timeout=30,
                )
                out = q.json().get("output", {})
                st = out.get("task_status")
                if st != "RUNNING":
                    log(f"[{i}] {st}  总耗时 {time.time()-t0:.1f}s")
                    log("  " + json.dumps(out, ensure_ascii=False)[:500])
                    if st == "SUCCEEDED":
                        urls = out.get("results") or []
                        if urls:
                            u = urls[0].get("url")
                            img = requests.get(u, timeout=120)
                            dest = OUT / "dashscope_wanx_base64_left.png"
                            dest.write_bytes(img.content)
                            log(f"  [成功] 已保存 {dest.name}  {len(img.content):,} bytes")
                    return
            log("[超时] 120s 未完成")
    except Exception as exc:  # noqa: BLE001
        log(f"异常: {type(exc).__name__}: {str(exc)[:300]}")


if __name__ == "__main__":
    main()
