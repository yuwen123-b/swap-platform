"""物品图片 URL 迁移脚本（幂等，可重复运行）。

⚠️⚠️ **已废弃（2026-10-16），禁止再运行！** ⚠️⚠️
本脚本的历史方案「把签名 URL 写进 item.images」已被证实是 **BUG**：签名只有
1 小时有效期（file_url_expire_seconds=3600），落库必然过期，任何物品发布
1 小时后封面就会 403。正确口径是「**DB 只存相对路径，签名在读取时现场补**」，
统一实现在 `app/services/image_utils.py`（`item_covers*` / `to_signed_url`）。

存量的外链 / 签名 URL 规整请改用 `scripts/localize_item_images.py`。
保留本文件仅为历史溯源，请勿执行。

背景：
    图片访问由 StaticFiles 目录直挂改为受控路由后，URL 需要携带签名参数
    （exp + sig）才能访问。本脚本把历史存量数据中不含签名的旧 URL
    批量补签，避免老图片在切换后无法显示。

迁移规则：
    旧：/api/v1/static/items/xxx.jpg
    新：/api/v1/static/items/xxx.jpg?exp=...&sig=...

特点：
    - 幂等：已带 exp/sig 的 URL 会被跳过，重复运行不会重复追加参数；
    - 安全：先以 --dry-run 预览将改动的行数与内容，确认后再实际写入；
    - 安全：仅处理形如 /api/v1/static/items/<文件名> 的合法旧 URL，
      其他格式（如 panorama 视角图或已损坏数据）原样保留不做改动。

用法（在 agent_back 目录下）：
    # 预览（不写库）
    .venv/Scripts/python.exe scripts/migrate_item_image_urls.py --dry-run
    # 实际执行
    .venv/Scripts/python.exe scripts/migrate_item_image_urls.py
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.security import sign_file_path  # noqa: E402
from app.db.pool import connection  # noqa: E402

# 旧 URL 前缀：与本项目 api_prefix（/api/v1）+ /static/items/ 对齐
STATIC_ITEMS_PREFIX = f"{settings.api_prefix}/static/items/"


def migrate_url(url: str) -> str | None:
    """为单个旧 URL 补签；无需迁移或格式不合法时返回 None。"""
    if not isinstance(url, str):
        return None
    if not url.startswith(STATIC_ITEMS_PREFIX):
        return None
    # 已带签名参数则跳过（幂等保证）
    if "exp=" in url and "sig=" in url:
        return None
    # 相对 uploads 的路径，如 items/xxx.jpg（供签名计算使用）
    relative_path = url[len(f"{settings.api_prefix}/static/"):]
    return f"{url}?{sign_file_path(relative_path)}"


def migrate_images_field(raw: str | None) -> tuple[str, int] | None:
    """处理 item.images 字段（JSON 数组字符串），返回 (新值, 改动数)；无改动返回 None。"""
    if not raw:
        return None
    try:
        urls = json.loads(raw)
    except (TypeError, ValueError):
        # 非合法 JSON：不擅自改写，避免破坏数据
        return None
    if not isinstance(urls, list):
        return None

    changed = 0
    migrated: list = []
    for url in urls:
        new_url = migrate_url(url)
        if new_url:
            migrated.append(new_url)
            changed += 1
        else:
            migrated.append(url)

    if changed == 0:
        return None
    return json.dumps(migrated, ensure_ascii=False), changed


def main() -> None:
    parser = argparse.ArgumentParser(description="为存量物品图片 URL 补签名参数")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据库")
    args = parser.parse_args()

    total_rows = 0
    total_urls = 0

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, images FROM item WHERE images IS NOT NULL AND images != ''")
            rows = cursor.fetchall()

            for row in rows:
                result = migrate_images_field(row["images"])
                if not result:
                    continue
                new_value, changed = result
                total_rows += 1
                total_urls += changed
                if args.dry_run:
                    print(f"[dry-run] item id={row['id']} 将更新 {changed} 个图片 URL")
                else:
                    cursor.execute("UPDATE item SET images=%s WHERE id=%s", (new_value, row["id"]))

    mode = "预览" if args.dry_run else "已迁移"
    print(f"[migrate] {mode}：{total_rows} 行，共 {total_urls} 个图片 URL")
    if args.dry_run and total_rows:
        print("[migrate] 确认无误后去掉 --dry-run 参数重新执行以写入数据库")


if __name__ == "__main__":
    main()
