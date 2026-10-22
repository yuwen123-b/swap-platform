"""【一次性验证脚本】魔搭 Qwen-Image-Edit-2511 视角外推可行性实测。

目的：D1 决策前先验证「同款物品、只改视角」这件事到底能不能做到。
不做任何写库操作，产物落在 scripts/_pano_test/ 供人工查看。

用法：
    ./.venv/Scripts/python.exe scripts/_tmp_pano_edit_test.py            # 只测相机
    ./.venv/Scripts/python.exe scripts/_tmp_pano_edit_test.py --all      # 三件物品全测
"""
import sys
import time
import traceback
from pathlib import Path

import requests

# 允许以 `python scripts/xxx.py` 方式直接运行（把项目根加入 sys.path）
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings  # noqa: E402
from app.services import llm_client

OUT = Path(__file__).resolve().parent / "_pano_test"
OUT.mkdir(parents=True, exist_ok=True)

PROMPT_LEFT = (
    "将图片中的物品向左旋转 90 度，保持物品的外观、颜色、材质、背景完全一致，只改变视角"
)
PROMPT_BACK = (
    "将图片中的物品旋转到背面视角，保持物品的外观、颜色、材质、背景完全一致，只改变视角"
)

# 真实库种子物品在用的 Unsplash 原图（就是 item 55/56/59 的 images[0]）
SAMPLES = [
    ("camera", "复古胶片相机", "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?auto=format&fit=crop&w=800&q=80"),
    ("headphone", "头戴式降噪耳机", "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=800&q=80"),
    ("sofa", "布艺双人沙发", "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=800&q=80"),
]


def line(t="-" * 66):
    print(t, flush=True)


def download(key: str, url: str) -> Path | None:
    dest = OUT / f"source_{key}.jpg"
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  [跳过下载] {dest.name} 已存在 {dest.stat().st_size:,} bytes")
        return dest
    try:
        r = requests.get(url, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code >= 400:
            print(f"  [下载失败] HTTP {r.status_code}")
            return None
        dest.write_bytes(r.content)
        print(f"  [原图] {dest.name}  {len(r.content):,} bytes")
        return dest
    except Exception as exc:  # noqa: BLE001
        print(f"  [下载异常] {type(exc).__name__}: {exc}")
        return None


def edit_once(key: str, src: Path, tag: str, prompt: str) -> dict:
    """直调魔搭分支（不经过降级，确保看到的是魔搭本身的真实结果）。"""
    dest = OUT / f"{key}_{tag}.jpg"
    t0 = time.time()
    try:
        data = llm_client._image_edit_modelscope(src, prompt)
        cost = time.time() - t0
        dest.write_bytes(data)
        print(f"  [成功] {tag:<5} 耗时 {cost:6.1f}s  输出 {len(data):>9,} bytes -> {dest.name}", flush=True)
        return {"ok": True, "cost": cost, "size": len(data), "file": str(dest), "err": ""}
    except Exception as exc:  # noqa: BLE001
        cost = time.time() - t0
        print(f"  [失败] {tag:<5} 耗时 {cost:6.1f}s  {type(exc).__name__}: {str(exc)[:300]}", flush=True)
        return {"ok": False, "cost": cost, "size": 0, "file": "", "err": f"{type(exc).__name__}: {exc}"}


def main():
    run_all = "--all" in sys.argv

    line("=" * 66)
    print("魔搭 Qwen-Image-Edit 视角外推实测")
    line("=" * 66)
    print(f"IMAGE_PROVIDER        = {settings.image_provider}")
    print(f"IMAGE_MODEL           = {settings.image_model}")
    print(f"MODELSCOPE_API_URL    = {settings.modelscope_api_url}")
    print(f"MODELSCOPE_API_KEY    = {'<已配置 %d 字符>' % len(settings.modelscope_api_key) if settings.modelscope_api_key.strip() else '<空>'}")
    print(f"PUBLIC_BASE_URL       = {settings.public_base_url!r}  (百炼降级不可用)")
    print(f"modelscope 可用       = {llm_client._has_modelscope()}")
    print(f"产物目录              = {OUT}")
    line()

    targets = SAMPLES if run_all else SAMPLES[:1]
    results = []

    for key, label, url in targets:
        line("-" * 66)
        print(f"【{label}】({key})")
        src = download(key, url)
        if src is None:
            results.append((label, "下载失败", None))
            continue
        r1 = edit_once(key, src, "left", PROMPT_LEFT)
        results.append((label, "左转 90°", r1))
        if r1["ok"] and run_all:
            edit_once(key, src, "back", PROMPT_BACK)

    line("=" * 66)
    print("汇总")
    line("=" * 66)
    for label, tag, r in results:
        if r is None:
            print(f"  {label:<12} {tag:<10} 跳过")
        elif r["ok"]:
            print(f"  {label:<12} {tag:<10} 成功  {r['cost']:6.1f}s  {r['size']:>9,} bytes")
        else:
            line()
            print(f"  {label:<12} {tag:<10} 失败  {r['cost']:6.1f}s")
            print(f"      原因: {r['err'][:400]}")
    line("=" * 66)
    print(f"产物目录: {OUT}")
    for p in sorted(OUT.glob("*.jpg")):
        print(f"  {p.name:<28} {p.stat().st_size:>10,} bytes")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
