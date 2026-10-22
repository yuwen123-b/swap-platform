"""【一次性验证】魔搭异步接口用「公网 URL」是否比 base64 更快出结果。

区分实验：base64 跑了 180s 仍 RUNNING。
若公网 URL 很快 SUCCEED → 瓶颈在 base64 输入；
若一样卡 → 瓶颈是排队（免费额度拥塞）。
"""
import json
import sys
import time
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings  # noqa: E402

BASE = "https://api-inference.modelscope.cn/"
KEY = settings.modelscope_api_key
MODEL = "Qwen/Qwen-Image-Edit-2511"
OUT = Path(__file__).resolve().parent / "_pano_test"
LOG = OUT / "probe_public_url.txt"
PROMPT = "将图片中的物品向左旋转 90 度，保持物品的外观、颜色、材质、背景完全一致，只改变视角"

# 公网可达的真实物品图（就是 item 55 在用的 Unsplash 原图）
PUBLIC_IMG = "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?auto=format&fit=crop&w=800&q=80"

_lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        LOG.write_text("\n".join(_lines), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main():
    h = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    log(f"MODEL = {MODEL}")
    log(f"PUBLIC_IMG = {PUBLIC_IMG}")

    t0 = time.time()
    r = requests.post(
        f"{BASE}v1/images/generations",
        headers={**h, "X-ModelScope-Async-Mode": "true"},
        data=json.dumps({"model": MODEL, "prompt": PROMPT, "image_url": [PUBLIC_IMG]}, ensure_ascii=False).encode("utf-8"),
        timeout=60,
    )
    log(f"提交 HTTP {r.status_code} ({time.time()-t0:.1f}s)  {r.text[:300]}")
    if r.status_code >= 400:
        return
    task_id = r.json().get("task_id")
    log(f"task_id = {task_id}")

    for i in range(60):
        time.sleep(5)
        q = requests.get(
            f"{BASE}v1/tasks/{task_id}",
            headers={"Authorization": f"Bearer {KEY}", "X-ModelScope-Task-Type": "image_generation"},
            timeout=30,
        )
        if q.status_code >= 400:
            log(f"[{i}] HTTP {q.status_code}: {q.text[:200]}")
            return
        body = q.json()
        st = body.get("task_status")
        log(f"[{i}] {st}  ({5*(i+1)}s)")
        if st == "SUCCEED":
            imgs = body.get("output_images") or body.get("output", {}).get("images")
            log("结果: " + json.dumps(imgs, ensure_ascii=False)[:300])
            if imgs:
                u = imgs[0] if isinstance(imgs[0], str) else imgs[0].get("url")
                img = requests.get(u, timeout=120)
                dest = OUT / "modelscope_public_url_left.jpg"
                dest.write_bytes(img.content)
                log(f"[成功] 已保存 -> {dest.name}  {len(img.content):,} bytes  总耗时 {time.time()-t0:.1f}s")
            return
        if st in ("FAILED", "FAIL"):
            log("失败: " + json.dumps(body, ensure_ascii=False)[:500])
            return
    log(f"[超时] 300s 内未完成，总耗时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
