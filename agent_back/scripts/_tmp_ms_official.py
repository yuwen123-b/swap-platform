"""【一次性验证】用魔搭官方示例原样复现，区分「模型拥塞」vs「我们的参数有问题」。

官方模型卡示例：
    model = Qwen/Qwen-Image-Edit-2509 (或 2511)
    image_url = ["https://modelscope.oss-cn-beijing.aliyuncs.com/Dog.png"]
    prompt = "给图中的狗戴上一个生日帽"
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
OUT = Path(__file__).resolve().parent / "_pano_test"
LOG = OUT / "probe_official.txt"
DOG = "https://modelscope.oss-cn-beijing.aliyuncs.com/Dog.png"

CASES = [
    ("官方示例 2509", "Qwen/Qwen-Image-Edit-2509", "给图中的狗戴上一个生日帽", [DOG]),
    ("官方图 + 2511 + 旋转", "Qwen/Qwen-Image-Edit-2511", "将图片中的物品向左旋转90度，保持外观颜色材质一致，只改变视角", [DOG]),
]

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


def submit(model, prompt, urls):
    r = requests.post(
        f"{BASE}v1/images/generations",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "X-ModelScope-Async-Mode": "true"},
        data=json.dumps({"model": model, "prompt": prompt, "image_url": urls}, ensure_ascii=False).encode("utf-8"),
        timeout=60,
    )
    if r.status_code >= 400:
        log(f"  提交失败 HTTP {r.status_code}: {r.text[:250]}")
        return None
    body = r.json()
    log(f"  提交 HTTP {r.status_code}  {json.dumps(body, ensure_ascii=False)[:200]}")
    return body.get("task_id")


def poll(tid, rounds=48, interval=5):
    for i in range(rounds):
        time.sleep(interval)
        q = requests.get(
            f"{BASE}v1/tasks/{tid}",
            headers={"Authorization": f"Bearer {KEY}", "X-ModelScope-Task-Type": "image_generation"},
            timeout=30,
        )
        if q.status_code >= 400:
            log(f"  [{i}] HTTP {q.status_code}: {q.text[:200]}")
            return None
        body = q.json()
        st = body.get("task_status")
        if st != "RUNNING":
            log(f"  [{i}] {st} ({interval*(i+1)}s)")
            return body
        if i % 6 == 5:
            log(f"  [{i}] RUNNING ({interval*(i+1)}s)")
    log(f"  [超时] {rounds*interval}s 未完成")
    return None


def main():
    log(f"KEY 长度 = {len(KEY)}")
    for label, model, prompt, urls in CASES:
        log(f"\n=== {label} ===")
        log(f"  model={model}")
        t0 = time.time()
        tid = submit(model, prompt, urls)
        if not tid:
            continue
        log(f"  task_id={tid}")
        body = poll(tid)
        if body and body.get("task_status") == "SUCCEED":
            imgs = body.get("output_images")
            log("  结果: " + json.dumps(imgs, ensure_ascii=False)[:300])
            if imgs:
                u = imgs[0] if isinstance(imgs[0], str) else imgs[0].get("url")
                img = requests.get(u, timeout=120)
                dest = OUT / f"official_{model.split('-')[-1]}_{int(time.time())}.png"
                dest.write_bytes(img.content)
                log(f"  [成功] 已保存 {dest.name}  {len(img.content):,} bytes  总耗时 {time.time()-t0:.1f}s")
        elif body:
            log("  " + json.dumps(body, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
