import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.refund import RefundStatus


class RefundRead(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    amount: int
    status: RefundStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
