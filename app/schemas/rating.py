from pydantic import BaseModel, Field


class RatingCreate(BaseModel):
    value: int = Field(ge=1, le=5)


class RatingSummary(BaseModel):
    average: float
    total: int
    my_rating: int | None = None
