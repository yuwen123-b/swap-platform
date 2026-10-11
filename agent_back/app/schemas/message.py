from datetime import datetime

from pydantic import BaseModel, Field


class MessageSendRequest(BaseModel):
    receiver_id: int
    item_id: int | None = None
    content: str = Field(min_length=1, max_length=500)


class MessageResponse(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    item_id: int | None = None
    content: str
    is_read: int
    created_at: datetime
    sender_nickname: str | None = None
    sender_avatar: str | None = None
