"""【开发辅助】把 item 55 临时置为 panorama ready，用于手动验证 360° 查看器。

用法（必须先关掉或重启 uvicorn，避免连接池缓存旧快照）：
    cd d:/Project/agent_back
    .venv/Scripts/python.exe scripts/_tmp_panorama_demo.py on     # 造数据（4 张视角图 + DB ready）
    .venv/Scripts/python.exe scripts/_tmp_panorama_demo.py off    # 还原（删图 + DB 回 none）

验证地址：http://localhost:5173/items/55

注意：视角图用 4 个纯色方块（前红/左蓝/后黄/右紫），便于肉眼判断
① 颜色是否偏暗发绿  ② 拖动/键盘/自动旋转是否正常  ③ 原图 ⇄ 360° 是否可自由切换。
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PIL import Image  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.pool import connection  # noqa: E402

ITEM_ID = 55
VIEW_NAMES = ("front", "left", "back", "right")
# 纯色便于肉眼分辨四个视角
COLORS = {
    "front": (200, 60, 60),
    "left": (60, 120, 200),
    "back": (200, 180, 60),
    "right": (140, 90, 200),
}


def views_dir() -> Path:
    return Path(settings.upload_dir).resolve() / "items" / str(ITEM_ID) / "views"


def sql_ready() -> str:
    """返回等价 SQL（供不想跑脚本时直接在 MySQL 里执行）。"""
    prefix = settings.api_prefix
    rels = {n: f"{prefix}/static/items/{ITEM_ID}/views/{n}.jpg" for n in VIEW_NAMES}
    payload = {"views": rels, "generated_at": "2026-10-13T12:00:00", "fallback": False}
    return (
        "UPDATE `item` SET\n"
        "  `panorama_status` = 'ready',\n"
        f"  `panorama_views` = '{json.dumps(payload, ensure_ascii=False)}',\n"
        "  `panorama_generated_at` = NOW()\n"
        f"WHERE `id` = {ITEM_ID};"
    )


def turn_on() -> None:
    d = views_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in VIEW_NAMES:
        Image.new("RGB", (800, 600), COLORS[name]).save(d / f"{name}.jpg", "JPEG", quality=85)

    prefix = settings.api_prefix
    rels = {n: f"{prefix}/static/items/{ITEM_ID}/views/{n}.jpg" for n in VIEW_NAMES}
    payload = {"views": rels, "generated_at": "2026-10-13T12:00:00", "fallback": False}
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE item SET panorama_status=%s, panorama_views=%s, panorama_generated_at=NOW() WHERE id=%s",
                ("ready", json.dumps(payload, ensure_ascii=False), ITEM_ID),
            )
    print(f"[on] item {ITEM_ID} -> ready，4 张视角图已写入 {d}")
    print("     打开 http://localhost:5173/items/55 验证")


def turn_off() -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE item SET panorama_status='none', panorama_views=NULL, panorama_generated_at=NULL WHERE id=%s",
                (ITEM_ID,),
            )
    d = views_dir()
    if d.exists():
        for p in sorted(d.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        d.rmdir()
        parent = d.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    print(f"[off] item {ITEM_ID} -> none，视角图已删除")


if __name__ == "__main__":
    action = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if action == "on":
        turn_on()
    elif action == "off":
        turn_off()
    elif action == "sql":
        print(sql_ready())
    else:
        print("用法: python scripts/_tmp_panorama_demo.py [on|off|sql]")
        sys.exit(1)
