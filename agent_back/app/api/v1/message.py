from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.response import success
from app.core.security import get_current_user_id
from app.schemas.message import MessageResponse, MessageSendRequest
from app.services import message_service

router = APIRouter()


@router.post("")
def send_message(payload: MessageSendRequest, user_id: int = Depends(get_current_user_id)):
    if payload.receiver_id == user_id:
        raise HTTPException(status_code=400, detail="不能给自己发送私信")
    message_id = message_service.send_message(
        sender_id=user_id,
        receiver_id=payload.receiver_id,
        content=payload.content,
        item_id=payload.item_id,
    )
    return success({"message_id": message_id}, "发送成功")


@router.get("/chat")
def chat_history(
    other_user_id: int = Query(...),
    item_id: int | None = Query(None),
    user_id: int = Depends(get_current_user_id),
):
    rows = message_service.get_chat_history(user_id, other_user_id, item_id)
    return success([MessageResponse.model_validate(r).model_dump(mode="json") for r in rows])


@router.get("/sessions")
def sessions(user_id: int = Depends(get_current_user_id)):
    return success(message_service.get_sessions(user_id))


@router.put("/read/{message_id}")
def mark_read(message_id: int, user_id: int = Depends(get_current_user_id)):
    updated = message_service.mark_message_read(user_id, message_id)
    return success({"updated": updated})
