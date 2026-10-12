"""360° 物品视图接口：触发生成、查询生成结果。

POST /generate  接受 JSON { item_id }，使用物品已有图片触发后台生成
GET  /{id}     查询生成状态与视角图
"""
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.services import panorama_service

router = APIRouter()


class PanoramaRequest(BaseModel):
    item_id: int


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
                "SELECT user_id, images FROM item WHERE id=%s LIMIT 1", (item_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(404, "物品不存在")
            if row["user_id"] != user_id:
                raise HTTPException(403, "无权操作该物品")

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

    # URL → 本地文件路径：/api/v1/static/items/xxx.jpg → uploads/items/xxx.jpg
    image_url = images[0]
    prefix = f"{settings.api_prefix}/static/"
    if not image_url.startswith(prefix):
        raise HTTPException(400, "物品图片 URL 格式不支持")
    source_image = Path(settings.upload_dir).resolve() / image_url[len(prefix):]
    if not source_image.exists():
        raise HTTPException(400, "物品图片文件不存在")

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
