"""无障碍模式接口：模式设置、行动能力、交接方式评估、语音标签。"""
from fastapi import APIRouter, HTTPException

from app.core.response import success
from app.schemas.accessibility import (HandoverOptions, SetMobilityRequest,
                                       SetModeRequest, SetModeResponse,
                                       VoiceLabelResponse)
from app.services import accessibility_service, match_service
from app.utils.i18n import get_text, normalize_lang

router = APIRouter()


@router.post("/set-mode")
def set_mode(body: SetModeRequest):
    try:
        result = accessibility_service.set_mode(body.user_id, body.mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return success(SetModeResponse(**result).model_dump())


@router.post("/set-mobility")
def set_mobility(body: SetMobilityRequest):
    try:
        result = accessibility_service.set_mobility(body.user_id, body.mobility_level)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return success(result)


@router.get("/handover-options/{user_id}")
def handover_options(user_id: int):
    """交接方式评估：limited/assisted 自动排除自取并给出推荐项。"""
    return success(HandoverOptions(**match_service.evaluate_handover(user_id)).model_dump())


@router.get("/voice-label/{item_id}")
def voice_label(item_id: int, lang: str = "zh_CN"):
    """视障模式物品语音标签：物品名+成色+颜色+特征。"""
    lang = normalize_lang(lang)
    try:
        label = accessibility_service.generate_voice_label(item_id, language=lang)
    except ValueError:
        raise HTTPException(404, get_text("error.user_not_found", lang).replace("用户", "物品"))
    return success(VoiceLabelResponse(item_id=item_id, label=label).model_dump())
