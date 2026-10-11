from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    order_id: int
    to_user_id: int
    rating: int = Field(ge=1, le=5)
    content: str = Field(min_length=1, max_length=500)
    tags: list[str] = []
