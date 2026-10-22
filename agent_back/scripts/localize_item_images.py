"""把 `item.images` 里残留的「外链 / 签名 URL」一次性规整为相对路径。

修复「发布 1 小时后封面 403」时，读取端已改为「DB 存相对路径 + 读取时签名」，
但库里仍有两类历史值需要规整：

1. **公网外链**（演示种子数据 items 55-61，Unsplash）——国内网络不一定可达，
   且与「DB 只存相对路径」的约定不符。本脚本把图片**下载到本地**
   （`uploads/items/seed_<item_id>.<ext>`，扩展名按魔数判定而非 URL 后缀），
   再把 `item.images` 改成本地相对路径。下载失败的行**保持原值不动**，绝不写坏数据。
2. **已签名的静态 URL**（存量脏数据，如 item.id=77）——签名只有 1 小时有效期，
   落库必然过期。读取端虽已能自动剥掉旧签名重签（无需 SQL 即恢复），
   但库里留着过期签名终究是隐患，这里一并归一为相对路径。

幂等：已是相对路径的行会被跳过，可重复执行。

用法：
    python -m scripts.localize_item_images --dry-run   # 只看会改哪些，不落库
    python -m scripts.localize_item_images             # 实际执行
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.image_check import detect_image_ext  # noqa: E402
from app.db.pool import connection  # noqa: E402
from app.services.image_utils import normalize_image_ref  # noqa: E402

# 外链下载：与 image_utils.MAX_REMOTE_IMAGE_BYTES 同口径（10MB 上限）
MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = 20
UA = {"User-Agent": "Mozilla/5.0 (compatible; community-recycle/1.0)"}


def _parse(values_raw):
    if not values_raw:
        return []
    try:
        parsed = json.loads(values_raw)
    except (TypeError, ValueError):
        return [values_raw] if isinstance(values_raw, str) else []
    return [str(v) for v in parsed] if isinstance(parsed, list) else []


def _download(url: str) -> tuple[bytes | None, str | None, str | None]:
    """返回 (data, ext, error)。"""
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=UA, stream=True)
    except requests.RequestException as exc:  # noqa: PERF203
        return None, None, f"请求失败：{type(exc).__name__}"
    if resp.status_code != 200:
        return None, None, f"HTTP {resp.status_code}"
    chunks, size = [], 0
    for chunk in resp.iter_content(65536):
        size += len(chunk)
        if size > MAX_BYTES:
            return None, None, "超过 10MB 上限"
        chunks.append(chunk)
    data = b"".join(chunks)
    ext = detect_image_ext(data)
    if not ext:
        return None, None, "不是有效图片（魔数校验失败）"
    return data, ext, None


def main() -> int:
    parser = argparse.ArgumentParser(description="把 item.images 的外链/签名 URL 规整为相对路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不落库不下载")
    args = parser.parse_args()

    root = Path(settings.upload_dir).resolve()
    items_dir = root / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, images FROM item "
            "WHERE images IS NOT NULL AND images <> '' ORDER BY id"
        )
        rows = cur.fetchall()

        plan: list[tuple[int, str, str, str]] = []   # (id, kind, before, after)
        payloads: list[tuple[int, bytes, str]] = []  # (id, data, ext)

        for row in rows:
            item_id = int(row["id"])
            values = _parse(row["images"])
            if not values:
                continue
            changed = False
            new_values = []
            for value in values:
                text = str(value).strip()
                if text.startswith(("http://", "https://")):
                    # 外链 → 下载到本地
                    if args.dry_run:
                        new_values.append("<下载到本地>")
                        changed = True
                        continue
                    data, ext, err = _download(text)
                    if err:
                        print(f"  ! item {item_id} 外链下载失败（保留原值）：{err}")
                        new_values.append(text)
                        continue
                    payloads.append((item_id, data, ext))
                    new_values.append(f"items/seed_{item_id}.{ext}")
                    changed = True
                else:
                    ref = normalize_image_ref(text)
                    if ref and ref != text:
                        # 已签名 URL → 归一为相对路径
                        new_values.append(ref)
                        changed = True
                    elif ref:
                        new_values.append(ref)
                    else:
                        new_values.append(text)
            if changed:
                kind = "外链" if any(v.startswith(("http://", "https://")) for v in values) else "签名URL"
                plan.append((item_id, kind, row["images"], json.dumps(new_values, ensure_ascii=False)))

        if not plan:
            print("没有需要规整的行（全部已是相对路径）。")
            return 0

        print(f"{'DRY-RUN ' if args.dry_run else ''}待规整 {len(plan)} 行：")
        for item_id, kind, before, after in plan:
            print(f"  item {item_id:>4} [{kind}]")
            print(f"      - {str(before)[:110]}")
            print(f"      + {str(after)[:110]}")

        if args.dry_run:
            return 0

        # 先落盘图片，再改 DB —— 落盘失败的行不回写
        written: dict[int, str] = {}
        for item_id, data, ext in payloads:
            path = items_dir / f"seed_{item_id}.{ext}"
            path.write_bytes(data)
            written[item_id] = f"items/seed_{item_id}.{ext}"
            print(f"  ✓ 落盘 {path.name}（{len(data) // 1024} KB）")

        updated = 0
        for item_id, kind, before, after in plan:
            new_values = json.loads(after)
            # 外链若下载失败会保留原外链，此时该行不算成功规整
            if any(str(v).startswith(("http://", "https://")) for v in new_values):
                print(f"  - item {item_id} 跳过（仍有外链未落地）")
                continue
            cur.execute("UPDATE item SET images=%s WHERE id=%s", (after, item_id))
            updated += 1

    print(f"\n完成：规整 {updated} 行（共 {len(plan)} 行候选）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
