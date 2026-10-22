"""【一次性验证】回查已提交任务的最终状态 + 文生图对照。

信息价值：
- 直接查 2 个已提交 task_id 的当前状态 → 得知魔搭真实出图延迟量级（无需重新提交）
- 再提交一个「纯文生图」（无 image_url）作为对照 → 区分「排队慢」vs「编辑模型不可用」
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
LOG = OUT / "probe_late.txt"

KNOWN = [
    ("base64 编辑任务（21:21 提交）", "620b21a8-538e-479b-9ed2-d918f7d7b7ed"),
    ("公网URL 编辑任务（21:25 提交）", "a266afe0-87a8-4203-99c5-d7a7281e8bda"),
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


def query(task_id: str) -> dict:
    q = requests.get(
        f"{BASE}v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {KEY}", "X-ModelScope-Task-Type": "image_generation"},
        timeout=30,
    )
    if q.status_code >= 400:
        return {"_http": q.status_code, "_text": q.text[:300]}
    return q.json()


def main():
    log("=== 回查历史任务最终状态 ===")
    for label, tid in KNOWN:
        try:
            body = query(tid)
            st = body.get("task_status", "<no task_status>")
            log(f"[{label}] {st}")
            log("   " + json.dumps(body, ensure_ascii=False)[:500])
            imgs = body.get("output_images")
            if st == "SUCCEED" and imgs:
                u = imgs[0] if isinstance(imgs[0], str) else imgs[0].get("url")
                img = requests.get(u, timeout=120)
                dest = OUT / f"late_{tid[:8]}_left.jpg"
                dest.write_bytes(img.content)
                log(f"   [已保存] {dest.name}  {len(img.content):,} bytes")
        except Exception as exc:  # noqa: BLE001
            log(f"[{label}] 查询异常: {type(exc).__name__}: {exc}")

    log("")
    log("=== 对照实验：纯文生图（无 image_url）===")
    t0 = time.time()
    r = requests.post(
        f"{BASE}v1/images/generations",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "X-ModelScope-Async-Mode": "true"},
        data=json.dumps({"model": "Qwen/Qwen-Image", "prompt": "一只橘猫坐在木地板上"}, ensure_ascii=False).encode("utf-8"),
        timeout=60,
    )
    log(f"提交 HTTP {r.status_code} ({time.time()-t0:.1f}s)  {r.text[:250]}")
    if r.status_code >= 400:
        return
    tid = r.json().get("task_id")
    for i in range(40):
        time.sleep(5)
        try:
            body = query(tid)
        except Exception as exc:  # noqa: BLE001
            log(f"[{i}] 查询异常 {exc}")
            return
        st = body.get("task_status")
        log(f"[{i}] {st} ({5*(i+1)}s)")
        if st in ("SUCCEED", "FAILED", "FAIL"):
            log("  " + json.dumps(body, ensure_ascii=False)[:400])
            return


if __name__ == "__main__":
    main()
