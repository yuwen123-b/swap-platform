from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    content: str = Field(min_length=1, max_length=500)
