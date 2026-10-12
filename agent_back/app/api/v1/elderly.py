"""助老模式接口：语音/文字交互闭环 + 一键呼叫。"""
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.core.response import success
from app.schemas.elderly import CallHelpRequest, ElderlyInteractResponse
from app.services import elderly_service, notify_service

router = APIRouter()

MAX_AUDIO_SIZE = 10 * 1024 * 1024


def _save_audio(audio: UploadFile) -> Path:
    """校验并保存录音文件到 uploads/voice/，返回文件路径。"""
    content_type = audio.content_type or ""
    if not content_type.startswith(("audio/", "video/")):
        raise HTTPException(400, "仅支持音频文件")
    data = audio.file.read(MAX_AUDIO_SIZE + 1)
    if len(data) > MAX_AUDIO_SIZE:
        raise HTTPException(400, "音频大小不能超过 10MB")
    if not data:
        raise HTTPException(400, "音频内容为空")
    suffix = Path(audio.filename or "").suffix.lstrip(".") or "webm"
    voice_dir = Path(settings.upload_dir).resolve() / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    path = voice_dir / f"{uuid.uuid4().hex}.{suffix}"
    path.write_bytes(data)
    return path


@router.post("/interact", response_model=None)
def elderly_interact(
    user_id: int = Form(...),
    audio: UploadFile | None = File(None),
    text: str = Form(""),
):
    """助老交互：audio 与 text 至少给一个；ASR 不可用时返回 503 由前端降级文字输入。"""
    audio_path = _save_audio(audio) if audio is not None and audio.filename else None
    if audio_path is None and not text.strip():
        raise HTTPException(400, "请提供语音或文字")
    try:
        result: dict = elderly_service.interact(audio_path, user_id, text=text)
    except RuntimeError:
        raise HTTPException(503, "语音识别暂不可用，请改用文字输入")
    return success(ElderlyInteractResponse(**result).model_dump())


@router.post("/call-help")
def call_help(body: CallHelpRequest):
    """一键呼叫子女/志愿者：企微推送当前操作状态，未配置 webhook 时 mock 不阻断。"""
    pushed = notify_service.push_help_alert(body.user_id, body.context)
    return success({"pushed": pushed}, "已通知您的紧急联系人。")
