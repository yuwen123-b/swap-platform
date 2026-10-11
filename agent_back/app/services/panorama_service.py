"""360° 物品视图生成服务：一张正面照片生成 前/左/后/右 四视角。

策略：
1. 优先 wanx2.1-imageedit 图像外推生成 左/后/右（需 settings.public_base_url 提供公网图片 URL）；
2. 外推不可用或失败时降级：qwen-vl 分析物品外观 → 文生图生成缺失视角；
3. 全部失败时优雅降级为单图（panorama_status=failed），不阻断发布流程。

结果存入 uploads/items/{item_id}/views/{front,left,back,right}.jpg，
4 张图总大小 ≤ 2MB（PIL 自动压缩，无法压到上限内才判定失败）。
"""
import json
import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app.core.config import settings
from app.db.pool import connection
from app.services import llm_client

logger = logging.getLogger(__name__)

VIEW_NAMES = ("front", "left", "back", "right")
MAX_TOTAL_BYTES = 2 * 1024 * 1024

# 各视角的生成提示词
_VIEW_PROMPT = {
    "left": "同一物品的左侧90度视角照片，外观、颜色、材质保持一致，背景简洁",
    "back": "同一物品的背面视角照片，外观、颜色、材质保持一致，背景简洁",
    "right": "同一物品的右侧90度视角照片，外观、颜色、材质保持一致，背景简洁",
}

# 降级方案中 qwen-vl 的外观分析提示词
_VL_DESCRIBE_PROMPT = "描述这张物品照片的外观、颜色、材质、形状和显著特征，80 字以内。"


def _views_dir(item_id: int) -> Path:
    return Path(settings.upload_dir).resolve() / "items" / str(item_id) / "views"


def _view_url(item_id: int, name: str) -> str:
    return f"{settings.api_prefix}/static/items/{item_id}/views/{name}.jpg"


def _update_status(item_id: int, status: str, payload: dict | None = None) -> None:
    with connection() as conn:
        with conn.cursor() as cursor:
            if payload is None:
                cursor.execute("UPDATE item SET panorama_status=%s WHERE id=%s", (status, item_id))
            else:
                cursor.execute(
                    "UPDATE item SET panorama_status=%s, panorama_views=%s WHERE id=%s",
                    (status, json.dumps(payload, ensure_ascii=False), item_id),
                )


def _total_size(files: list[Path]) -> int:
    return sum(p.stat().st_size for p in files)


def _compress_views(views_dir: Path, max_total: int = MAX_TOTAL_BYTES) -> None:
    """PIL 压缩四视角图，确保总大小 ≤ max_total。

    策略：已达标不重压缩（保画质）→ JPEG 质量逐级下降（85→70→55→40）
    → 仍超限等比缩小到 768px。坏图或压缩后仍超限抛 RuntimeError（兜底失败）。
    """
    files = [views_dir / f"{name}.jpg" for name in VIEW_NAMES if (views_dir / f"{name}.jpg").exists()]
    if _total_size(files) <= max_total:
        return

    def _resave(path: Path, quality: int, thumbnail: bool = False) -> None:
        try:
            with Image.open(path) as img:
                img = img.convert("RGB")
                if thumbnail:
                    img.thumbnail((768, 768))
                img.save(path, "JPEG", quality=quality, optimize=True)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"视角图压缩失败 {path.name}: {exc}") from exc

    for quality in (85, 70, 55, 40):
        for path in files:
            _resave(path, quality)
        if _total_size(files) <= max_total:
            return
    # 最终兜底：等比缩小到 768px 内
    for path in files:
        _resave(path, 60, thumbnail=True)
    if _total_size(files) > max_total:
        raise RuntimeError(f"生成图片总大小 {_total_size(files)} 字节，压缩后仍超过 2MB 上限")


def generate(item_id: int, source_image: Path) -> dict:
    """同步生成四视角；任何环节失败抛出 RuntimeError。"""
    views_dir = _views_dir(item_id)
    views_dir.mkdir(parents=True, exist_ok=True)
    front_path = views_dir / "front.jpg"
    if source_image.resolve() != front_path.resolve():
        shutil.copyfile(source_image, front_path)

    views = {"front": _view_url(item_id, "front")}
    fallback = False
    missing = [n for n in VIEW_NAMES if n != "front"]

    if settings.public_base_url:
        source_url = f"{settings.public_base_url}{_view_url(item_id, 'front')}"
        try:
            for name in missing:
                result_url = llm_client.image_edit(source_url, _VIEW_PROMPT[name])
                llm_client.download_file(result_url, views_dir / f"{name}.jpg")
                views[name] = _view_url(item_id, name)
            missing = []
        except RuntimeError as exc:
            logger.warning("图像外推失败，转降级方案：%s", exc)
            fallback = True
    else:
        logger.info("未配置 PUBLIC_BASE_URL，360° 生成直接走降级方案")
        fallback = True

    if missing:
        # 降级：qwen-vl 生成多角度描述 + 文生图补齐缺失视角
        description = llm_client.describe_image(str(front_path), _VL_DESCRIBE_PROMPT)
        for name in missing:
            prompt = f"{description}。{_VIEW_PROMPT[name]}"
            result_url = llm_client.text_to_image(prompt)
            llm_client.download_file(result_url, views_dir / f"{name}.jpg")
            views[name] = _view_url(item_id, name)

    _compress_views(views_dir)
    payload = {
        "views": views,
        "fallback": fallback,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _update_status(item_id, "ready", payload)
    return {"item_id": item_id, "views": views, "status": "ready", "fallback": fallback}


def generate_async(item_id: int, source_image: Path) -> None:
    """后台线程生成：先置 generating，失败置 failed，绝不抛出阻断发布。"""
    def _run() -> None:
        _update_status(item_id, "generating")
        try:
            generate(item_id, source_image)
        except Exception as exc:  # noqa: BLE001 生成失败优雅降级为单图
            logger.warning("物品 %s 360° 生成失败，降级为单图：%s", item_id, exc)
            try:
                _update_status(item_id, "failed")
            except Exception:  # noqa: BLE001 状态回写失败仅记录日志
                logger.exception("物品 %s panorama_status 回写失败", item_id)

    threading.Thread(target=_run, daemon=True).start()


def get_views(item_id: int) -> dict:
    """读取物品 360° 视图信息；未生成时返回 status 与空 views。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT panorama_status, panorama_views FROM item WHERE id=%s LIMIT 1", (item_id,)
            )
            row = cursor.fetchone()
    if not row:
        raise ValueError("物品不存在")
    payload: dict = {}
    if row.get("panorama_views"):
        try:
            payload = json.loads(row["panorama_views"])
        except json.JSONDecodeError:
            payload = {}
    return {
        "item_id": item_id,
        "status": row.get("panorama_status") or "none",
        "views": payload.get("views") or {},
        "generated_at": payload.get("generated_at") or "",
        "fallback": bool(payload.get("fallback", False)),
    }
