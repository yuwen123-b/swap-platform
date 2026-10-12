"""360° 物品视图生成服务：一张正面照片生成 前/左/后/右 四视角。

策略：
1. 优先 wanx2.1-imageedit 图像外推生成 左/后/右（需 settings.public_base_url 提供公网图片 URL）；
2. 外推不可用或失败时降级：qwen-vl 分析物品外观 → 文生图生成缺失视角；
3. 全部失败时优雅降级为单图（panorama_status=failed），不阻断发布流程。

结果存入 uploads/items/{item_id}/views/{front,left,back,right}.jpg，
每张图压缩至 ≤ 500KB（PIL 质量阶梯），4 张总量因此 ≤ 2MB。
异步由路由层 BackgroundTasks 调度 run_generate（不引入 Celery）。
"""
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app.core.config import settings
from app.db.pool import connection
from app.services import llm_client

logger = logging.getLogger(__name__)

VIEW_NAMES = ("front", "left", "back", "right")
MAX_FILE_BYTES = 500 * 1024  # 单张视角图大小上限

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
                # ready 时同步回写生成完成时间（独立列，供接口直接读取）
                cursor.execute(
                    "UPDATE item SET panorama_status=%s, panorama_views=%s, "
                    "panorama_generated_at=NOW() WHERE id=%s",
                    (status, json.dumps(payload, ensure_ascii=False), item_id),
                )


def _compress_views(views_dir: Path, max_file: int = MAX_FILE_BYTES) -> None:
    """PIL 压缩每张视角图至 ≤ max_file（500KB）。

    策略：已达标不重压缩（保画质）→ JPEG 质量逐级下降（85→70→55→40）
    → 仍超限等比缩小到 768px。坏图抛 RuntimeError（兜底失败）。
    """
    def _resave(path: Path, quality: int, thumbnail: bool = False) -> None:
        try:
            with Image.open(path) as img:
                img = img.convert("RGB")
                if thumbnail:
                    img.thumbnail((768, 768))
                img.save(path, "JPEG", quality=quality, optimize=True)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"视角图压缩失败 {path.name}: {exc}") from exc

    for name in VIEW_NAMES:
        path = views_dir / f"{name}.jpg"
        if not path.exists() or path.stat().st_size <= max_file:
            continue
        for quality in (85, 70, 55, 40):
            _resave(path, quality)
            if path.stat().st_size <= max_file:
                break
        else:
            _resave(path, 60, thumbnail=True)  # 最终兜底：等比缩小到 768px 内
            if path.stat().st_size > max_file:
                raise RuntimeError(f"视角图 {path.name} 压缩后仍超过 500KB 上限")


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

    source_url = ""
    if settings.public_base_url:
        source_url = f"{settings.public_base_url}{_view_url(item_id, 'front')}"
    try:
        for name in missing:
            image_bytes = llm_client.image_edit(
                image_path=front_path, image_url=source_url, prompt=_VIEW_PROMPT[name],
            )
            (views_dir / f"{name}.jpg").write_bytes(image_bytes)
            views[name] = _view_url(item_id, name)
        missing = []
    except RuntimeError as exc:
        logger.warning("图像外推失败，转降级方案：%s", exc)
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


def run_generate(item_id: int, source_image: Path) -> None:
    """BackgroundTasks 入口：先置 generating，失败置 failed，绝不抛出阻断调用方。"""
    _update_status(item_id, "generating")
    try:
        generate(item_id, source_image)
    except Exception as exc:  # noqa: BLE001 生成失败优雅降级为单图
        logger.warning("物品 %s 360° 生成失败，降级为单图：%s", item_id, exc)
        try:
            _update_status(item_id, "failed")
        except Exception:  # noqa: BLE001 状态回写失败仅记录日志
            logger.exception("物品 %s panorama_status 回写失败", item_id)


def get_views(item_id: int) -> dict:
    """查询 panorama 状态，供前端轮询；panorama_views 仅 ready 时有值。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT panorama_status, panorama_views, panorama_generated_at "
                "FROM item WHERE id=%s LIMIT 1",
                (item_id,),
            )
            row = cursor.fetchone()
    if not row:
        raise ValueError("物品不存在")
    status = row.get("panorama_status") or "none"
    payload: dict = {}
    if row.get("panorama_views"):
        try:
            payload = json.loads(row["panorama_views"])
        except json.JSONDecodeError:
            payload = {}
    generated_at = row.get("panorama_generated_at")
    if hasattr(generated_at, "isoformat"):
        generated_at = generated_at.isoformat()
    views = payload.get("views") if status == "ready" else None
    return {
        "item_id": item_id,
        "panorama_status": status,
        "panorama_views": views if (views and views.get("front")) else None,
        "generated_at": generated_at or (payload.get("generated_at") or ""),
        "fallback": bool(payload.get("fallback", False)),
    }
