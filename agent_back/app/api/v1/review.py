import json
from fastapi import APIRouter, Depends, Header, Query
from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.schemas.review import ReviewCreate
from app.services import translation_service

router = APIRouter()


@router.get("")
def list_reviews(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), to_user_id: int | None = None, order_id: int | None = None, accept_language: str = Header(default="zh"), _: int = Depends(get_current_user_id)):
    conditions = ["1=1"]
    params: list = []
    if to_user_id:
        conditions.append("r.to_user_id=%s")
        params.append(to_user_id)
    if order_id:
        conditions.append("r.order_id=%s")
        params.append(order_id)
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM review r WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(f"SELECT r.* FROM review r WHERE {where} ORDER BY r.id DESC LIMIT %s OFFSET %s", params + [size, (page - 1) * size])
            rows = cursor.fetchall()
    # 英文模式：并发翻译评价内容（内部带缓存）
    if rows and translation_service.normalize_request_lang(accept_language) == "en":
        contents = translation_service.translate_many([r["content"] or "" for r in rows], "en")
        for r, c in zip(rows, contents):
            r["content"] = c
    return success({"items": rows, "total": total, "page": page, "size": size})


@router.get("/summary")
def review_summary(to_user_id: int | None = None, _: int = Depends(get_current_user_id)):
    condition = "WHERE to_user_id=%s" if to_user_id else ""
    params = [to_user_id] if to_user_id else []
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COALESCE(AVG(rating),0) AS average_rating, COUNT(*) AS total FROM review {condition}", params)
            result = cursor.fetchone()
    return success(result)


@router.post("")
def create_review(payload: ReviewCreate, user_id: int = Depends(get_current_user_id)):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO review (order_id,from_user_id,to_user_id,rating,content,tags) VALUES (%s,%s,%s,%s,%s,%s)", (payload.order_id, user_id, payload.to_user_id, payload.rating, payload.content, json.dumps(payload.tags, ensure_ascii=False)))
            review_id = cursor.lastrowid
    return success({"review_id": review_id}, "评价提交成功")
