import json
import time
import uuid
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.schemas.pricing import PricingRequest
from app.services import agent, recognition_service
from app.services.ai_log import log_ai_call

router = APIRouter()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024


@router.post("/pricing")
def pricing(payload: PricingRequest, user_id: int = Depends(get_current_user_id)):
    start = time.perf_counter()
    try:
        condition_rates = {1: Decimal("0.20"), 2: Decimal("0.35"), 3: Decimal("0.50"), 4: Decimal("0.65"), 5: Decimal("0.80")}
        category_adjustments = {"数码家电": Decimal("0.05"), "家具家居": Decimal("-0.03"), "母婴玩具": Decimal("0.00")}
        depreciation_rate = max(Decimal("0.10"), min(Decimal("0.90"), Decimal("1.00") - condition_rates[payload.condition_level] + category_adjustments.get(payload.item_category, Decimal("0"))))
        suggested_price = (payload.original_price * (Decimal("1.00") - depreciation_rate)).quantize(Decimal("0.01"))
        reason = f"根据成色{payload.condition_level}级和{payload.item_category}类别，建议折旧率为{depreciation_rate:.2%}，建议售价{suggested_price}元。"
        result = {"suggested_price": suggested_price, "depreciation_rate": depreciation_rate, "pricing_reason": reason}
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO ai_pricing_log (user_id,item_name,item_category,condition_level,original_price,suggested_price,depreciation_rate,pricing_reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (user_id, payload.item_name, payload.item_category, payload.condition_level, payload.original_price, suggested_price, depreciation_rate, reason))
        log_ai_call("pricing", payload.model_dump(), result, 1, int((time.perf_counter() - start) * 1000))
        return success(result)
    except Exception as exc:
        log_ai_call("pricing", payload.model_dump(), None, 0, int((time.perf_counter() - start) * 1000), str(exc))
        raise


@router.get("/pricing/history")
def pricing_history(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), user_id: int = Depends(get_current_user_id)):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM ai_pricing_log WHERE user_id=%s", (user_id,))
            total = cursor.fetchone()["total"]
            cursor.execute("SELECT * FROM ai_pricing_log WHERE user_id=%s ORDER BY id DESC LIMIT %s OFFSET %s", (user_id, size, (page - 1) * size))
            rows = cursor.fetchall()
    return success({"items": rows, "total": total, "page": page, "size": size})


@router.get("/agent/stream")
def agent_stream(question: str = Query(..., min_length=1, max_length=500), user_id: int = Depends(get_current_user_id)):
    """智能体助手 SSE 流式问答。帧格式：data: {"msg": "..."}，结束帧 msg=[end_stream]。"""
    start = time.perf_counter()
    parts: list[str] = []

    def event_source():
        status, error = 1, None
        try:
            for token in agent.stream_tokens(question, "zh", user_id):
                parts.append(token)
                yield f"data: {json.dumps({'msg': token}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # 流中异常：告知前端并留日志
            status, error = 0, str(exc)
            yield f"data: {json.dumps({'msg': '抱歉，服务暂时不可用，请稍后再试。'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'msg': '[end_stream]'})}\n\n"
        log_ai_call(
            "assistant_stream",
            {"question": question, "user_id": user_id},
            "".join(parts) if status == 1 else None,
            status,
            int((time.perf_counter() - start) * 1000),
            error,
        )

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/recognition")
def recognition(image: UploadFile = File(...), user_id: int = Depends(get_current_user_id)):
    """AI 物体识别：上传图片返回物品名称/建议分类/成色/描述/标签。"""
    start = time.perf_counter()
    ext = ALLOWED_IMAGE_TYPES.get(image.content_type or "")
    if not ext:
        raise HTTPException(400, "仅支持 jpg/png/webp/gif 格式图片")
    data = image.file.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(400, "图片大小不能超过 5MB")
    if not data:
        raise HTTPException(400, "图片内容为空")

    rec_dir = Path(settings.upload_dir).resolve() / "recognition"
    rec_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    (rec_dir / filename).write_bytes(data)
    image_url = f"{settings.api_prefix}/static/recognition/{filename}"

    result = recognition_service.recognize_with_fallback(data, image.content_type or "image/jpeg", "zh")
    log_ai_call(
        "recognition",
        {"user_id": user_id, "filename": image.filename},
        result,
        1,
        int((time.perf_counter() - start) * 1000),
    )
    return success({**result, "image_url": image_url}, "识别完成")
