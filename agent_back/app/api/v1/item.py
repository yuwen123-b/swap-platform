import json
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile

from app.core.config import settings
from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.services import translation_service

router = APIRouter()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024


@router.get("")
def list_items(page: int = Query(1, ge=1), size: int = Query(12, ge=1, le=100), category_id: int | None = None, exchange_mode: str | None = None, keyword: str | None = None, sort_by: str | None = None, status: int = 1, accept_language: str = Header(default="zh")):
    conditions = ["i.status=%s"]
    params: list = [status]
    if category_id:
        conditions.append("i.category_id=%s")
        params.append(category_id)
    if exchange_mode:
        conditions.append("i.exchange_mode=%s")
        params.append(exchange_mode)
    if keyword:
        conditions.append("(i.title LIKE %s OR i.description LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    where = " AND ".join(conditions)
    offset = (page - 1) * size

    # 排序白名单：值 -> ORDER BY 片段，避免用户输入直接拼接 SQL
    sort_map = {
        None: "i.id DESC",
        "created_at": "i.created_at DESC, i.id DESC",
        "carbon_value": "i.carbon_value DESC, i.id DESC",
    }
    if sort_by == "distance":
        # 暂无距离数据（需要用户位置/社区地理信息），返回明确提示由前端展示
        raise HTTPException(status_code=400, detail="距离排序功能开发中")
    if sort_by not in sort_map:
        raise HTTPException(status_code=400, detail="不支持的排序方式")
    order_sql = sort_map[sort_by]

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM item i WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT i.*, c.name AS category_name
                    FROM item i
                    LEFT JOIN category c ON i.category_id = c.id
                    WHERE {where}
                    ORDER BY {order_sql}
                    LIMIT %s OFFSET %s""",
                params + [size, offset],
            )
            items = cursor.fetchall()
    # 列表不透出 panorama_views 大 JSON（仅保留 panorama_status 供卡片 360° 角标）
    for it in items:
        it["panorama_views"] = None
    # 英文模式：并发翻译标题与描述（内部带缓存）
    lang = translation_service.normalize_request_lang(accept_language)
    if items and lang == "en":
        titles = translation_service.translate_many([it["title"] or "" for it in items], "en")
        descs = translation_service.translate_many([it["description"] or "" for it in items], "en")
        for it, t, d in zip(items, titles, descs):
            it["title"], it["description"] = t, d
    return success({"items": items, "total": total, "page": page, "size": size})


@router.get("/{item_id}")
def get_item(item_id: int, accept_language: str = Header(default="zh")):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM item WHERE id=%s LIMIT 1", (item_id,))
            item = cursor.fetchone()
    if not item:
        raise HTTPException(404, "物品不存在")
    # 360° 字段整形：仅 ready 时透出视角图 dict，其余状态置 None（坏 JSON 静默降级）
    raw_views = item.get("panorama_views")
    item["panorama_views"] = None
    if item.get("panorama_status") == "ready" and raw_views:
        try:
            views = json.loads(raw_views).get("views")
            if isinstance(views, dict) and views:
                item["panorama_views"] = views
        except (TypeError, ValueError):
            pass
    lang = translation_service.normalize_request_lang(accept_language)
    if lang == "en":
        item["title"] = translation_service.translate_text(item["title"], "en")
        item["description"] = translation_service.translate_text(item["description"], "en")
    return success(item)


@router.post("")
def create_item(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str = Form(...),
    category_id: int = Form(...),
    expected_exchange: str = Form(""),
    contact: str = Form(...),
    image: UploadFile | None = File(None),
    user_id: int = Depends(get_current_user_id),
):
    title = title.strip()
    description = description.strip()
    contact = contact.strip()
    if not title or not description or not contact:
        raise HTTPException(400, "物品名称、描述和联系方式不能为空")
    if len(title) > 64:
        raise HTTPException(400, "物品名称不能超过 64 字")
    if len(contact) > 100:
        raise HTTPException(400, "联系方式不能超过 100 字")

    image_url: str | None = None
    image_path: Path | None = None
    if image is not None and image.filename:
        ext = ALLOWED_IMAGE_TYPES.get(image.content_type or "")
        if not ext:
            raise HTTPException(400, "仅支持 jpg/png/webp/gif 格式图片")
        data = image.file.read(MAX_IMAGE_SIZE + 1)
        if len(data) > MAX_IMAGE_SIZE:
            raise HTTPException(400, "图片大小不能超过 5MB")
        if not data:
            raise HTTPException(400, "图片内容为空")
        items_dir = Path(settings.upload_dir).resolve() / "items"
        items_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.{ext}"
        image_path = items_dir / filename
        image_path.write_bytes(data)
        image_url = f"{settings.api_prefix}/static/items/{filename}"

    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM category WHERE id=%s LIMIT 1", (category_id,))
            if not cursor.fetchone():
                raise HTTPException(400, "所选分类不存在")
            images_json = json.dumps([image_url]) if image_url else None
            cursor.execute(
                """INSERT INTO item
                       (user_id, category_id, title, description, images,
                        expected_item, contact, status, exchange_mode, condition_level)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 4, 1, 0)""",
                (user_id, category_id, title, description, images_json,
                 expected_exchange.strip() or None, contact),
            )
            item_id = cursor.lastrowid

    # 360° 视图生成：BackgroundTasks 后台执行，不阻断发布（惰性 import 避免循环依赖）
    if image_path is not None:
        try:
            from app.services import panorama_service
            background_tasks.add_task(panorama_service.run_generate, item_id, image_path)
        except Exception:  # noqa: BLE001
            pass
    return success({"id": item_id, "status": 4}, "提交成功，等待审核")
