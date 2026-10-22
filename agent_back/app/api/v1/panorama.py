"""360° 物品视图接口：触发生成、查询生成结果。

POST /generate  接受 JSON { item_id }，使用物品已有图片触发后台生成
GET  /{id}     查询生成状态与视角图
"""
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.services import panorama_service
from app.services.image_utils import ImageSourceError, ensure_local_jpeg

router = APIRouter()


class PanoramaRequest(BaseModel):
    item_id: int


def _resolve_source_image(image_url: str, item_id: int) -> Path:
    """把物品 images[0] 解析为本地 JPEG 文件（逻辑统一收敛到 image_utils）。

    此前这里自己实现了一份「签名 URL 去 query / 外链下载」，与 3D 服务会各写一份；
    现在两处共用 `ensure_local_jpeg`：签名 URL 直接映射到 uploads 原件，
    外链下载到 views/front.jpg，**WEBP/PNG 顺带转成真 JPEG**
    （历史问题：unspash/上传的 WEBP 字节被原样复制成 front.jpg，扩展名与内容不符）。
    公共模块抛 ImageSourceError，这里统一转成 400 + 中文提示。
    """
    front_path = panorama_service._views_dir(item_id) / "front.jpg"
    try:
        return ensure_local_jpeg(image_url, dest=front_path)
    except ImageSourceError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/generate")
def generate_panorama(
    req: PanoramaRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
):
    """触发 360° 视图生成；立即返回 generating，前端轮询 GET /{item_id}。"""
    item_id = req.item_id
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, images, panorama_status FROM item WHERE id=%s LIMIT 1", (item_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(404, "物品不存在")
            if row["user_id"] != user_id:
                raise HTTPException(403, "无权操作该物品")
            # 重复触发保护：正在生成时拒绝再次触发，避免并发烧模型额度
            if (row.get("panorama_status") or "none") == "generating":
                raise HTTPException(400, "360° 视图正在生成中，请稍候刷新查看，请勿重复触发")

    # 从物品已有图片中取第一张作为原图
    raw_images = row.get("images")
    if not raw_images:
        raise HTTPException(400, "该物品没有图片，无法生成 360° 视图")
    try:
        images = json.loads(raw_images) if isinstance(raw_images, str) else raw_images
    except (TypeError, ValueError):
        raise HTTPException(400, "物品图片数据格式错误")
    if not isinstance(images, list) or not images:
        raise HTTPException(400, "该物品没有图片，无法生成 360° 视图")

    # URL → 本地文件：兼容签名 URL（去 query）与公网外链（下载）两种形态
    source_image = _resolve_source_image(images[0], item_id)

    # BackgroundTasks 异步执行：请求立即返回，失败由 run_generate 内部落库为 failed
    background_tasks.add_task(panorama_service.run_generate, item_id, source_image)
    return success(
        {"item_id": item_id, "status": "generating"},
        "360° 视图生成中，请稍候查看。",
    )


@router.get("/{item_id}")
def get_panorama(item_id: int):
    try:
        result = panorama_service.get_views(item_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return success(result)
