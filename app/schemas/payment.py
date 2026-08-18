import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.payment import PaymentStatus


class Currency(str, Enum):
    EUR = "EUR"
    USD = "USD"


class PaymentCreate(BaseModel):
    merchant_id: uuid.UUID

    amount: int = Field(
        gt=0,
        description="Amount in minor currency units",
    )

    currency: Currency

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value):
        if isinstance(value, str):
            return value.upper()

        return value


class PaymentRead(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    amount: int
    currency: str
    status: PaymentStatus

    risk_score: int
    risk_level: str
    risk_reasons: list[str]

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
