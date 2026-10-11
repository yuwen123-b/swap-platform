"""国际化接口：语言偏好设置（i18n_router）、翻译服务（translate_router）。"""
from fastapi import APIRouter, HTTPException

from app.core.response import success
from app.db.pool import connection
from app.schemas.i18n import (SetLanguageRequest, SetLanguageResponse,
                              TranslateRequest, TranslateResponse)
from app.services import translate_service
from app.utils.i18n import SUPPORTED_LANGS

# 挂载于 /api/i18n
i18n_router = APIRouter()
# 挂载于 /api（提供 /translate）
translate_router = APIRouter()


@i18n_router.post("/set-language")
def set_language(body: SetLanguageRequest):
    if body.language not in SUPPORTED_LANGS:
        raise HTTPException(400, f"不支持的语言：{body.language}")
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE user SET preferred_lang=%s WHERE id=%s",
                           (body.language, body.user_id))
            if cursor.rowcount == 0:
                raise HTTPException(404, "用户不存在")
    return success(SetLanguageResponse(success=True, language=body.language).model_dump())


@translate_router.post("/translate")
def translate(body: TranslateRequest):
    try:
        result = translate_service.translate(body.text, body.source_lang, body.target_lang)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return success(TranslateResponse(**result).model_dump())
