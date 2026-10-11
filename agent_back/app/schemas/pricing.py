from decimal import Decimal
from pydantic import BaseModel, Field


class PricingRequest(BaseModel):
    item_name: str = Field(min_length=1, max_length=100)
    item_category: str = Field(min_length=1, max_length=50)
    condition_level: int = Field(ge=1, le=5)
    original_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
