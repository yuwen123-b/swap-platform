"""360° 物品视图接口：触发生成、查询生成结果。"""
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.v1.item import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
from app.core.config import settings
from app.core.response import success
from app.db.pool import connection
from app.services import panorama_service
from app.utils.i18n import get_text

router = APIRouter()


@router.post("/generate")
def generate_panorama(item_id: int = Form(...), source_image: UploadFile = File(...)):
    """上传正面照片并异步生成四视角；立即返回 generating，前端轮询 GET /{item_id}。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM item WHERE id=%s LIMIT 1", (item_id,))
            if not cursor.fetchone():
                raise HTTPException(404, "物品不存在")

    ext = ALLOWED_IMAGE_TYPES.get(source_image.content_type or "")
    if not ext:
        raise HTTPException(400, "仅支持 jpg/png/webp/gif 格式图片")
    data = source_image.file.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(400, "图片大小不能超过 5MB")
    if not data:
        raise HTTPException(400, "图片内容为空")

    views_dir = Path(settings.upload_dir).resolve() / "items" / str(item_id) / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    front_path = views_dir / "front.jpg"
    front_path.write_bytes(data)

    panorama_service.generate_async(item_id, front_path)
    return success({"item_id": item_id, "status": "generating"}, get_text("panorama.generating"))


@router.get("/{item_id}")
def get_panorama(item_id: int):
    try:
        result = panorama_service.get_views(item_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return success(result)
