"""【一次性验证】百炼 qwen-image-edit 直接吃 base64（免公网隧道）是否可行。

现有代码走的是 wanx2.1-imageedit（需 PUBLIC_BASE_URL 公网图），本地开发不可用。
百炼另有 qwen-image-edit 多模态生成端点，据文档支持 base64 data URL。
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
ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
PROMPT = "将图片中的物品向左旋转 90 度，保持物品的外观、颜色、材质、背景完全一致，只改变视角"


def main():
    print("=== 百炼 qwen-image-edit（base64 输入）===", flush=True)
    print(f"key 已配置: {bool(settings.dashscope_api_key.strip())}")
    if not SRC.exists():
        print("缺少原图")
        return
    b64 = "data:image/jpeg;base64," + base64.b64encode(SRC.read_bytes()).decode()
    print(f"base64 长度: {len(b64):,}")

    for model in ("qwen-image-edit", "qwen-image-edit-2509"):
        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"image": b64}, {"text": PROMPT}],
                    }
                ]
            },
            "parameters": {"watermark": False, "negative_prompt": ""},
        }
        t0 = time.time()
        try:
            r = requests.post(
                ENDPOINT,
                headers={
                    "Authorization": f"Bearer {settings.dashscope_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=240,
            )
            cost = time.time() - t0
            print(f"\n[{model}] HTTP {r.status_code}  耗时 {cost:.1f}s", flush=True)
            body = r.json()
            print(json.dumps(body, ensure_ascii=False)[:700], flush=True)
            if r.status_code == 200:
                try:
                    img_url = body["output"]["choices"][0]["message"]["content"][0]["image"]
                    img = requests.get(img_url, timeout=120)
                    dest = OUT / f"dashscope_{model.replace('/', '_')}_left.jpg"
                    dest.write_bytes(img.content)
                    print(f"  [成功] 已保存 -> {dest.name}  {len(img.content):,} bytes", flush=True)
                except (KeyError, IndexError, TypeError) as exc:
                    print(f"  [解析失败] {type(exc).__name__}: {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"\n[{model}] 异常 {time.time()-t0:.1f}s: {type(exc).__name__}: {str(exc)[:300]}", flush=True)


if __name__ == "__main__":
    main()
