from pydantic import BaseModel


class Advertisement(BaseModel):
    seller_id: int
    is_verified_seller: bool
    item_id: int
    name: str
    description: str
    category: int
    images_qty: int


class AsyncPredictRequest(BaseModel):
    item_id: int


class AsyncPredictResponse(BaseModel):
    task_id: int
    status: str
    message: str


class ModerationResultResponse(BaseModel):
    task_id: int
    status: str
    is_violation: bool | None
    probability: float | None
