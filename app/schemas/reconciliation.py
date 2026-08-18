import enum
import uuid

from pydantic import BaseModel


class ReconciliationStatus(str, enum.Enum):
    MATCHED = "matched"
    MISSING = "missing"
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    STATUS_MISMATCH = "status_mismatch"


class ReconciliationItem(BaseModel):
    payment_id: uuid.UUID
    result: ReconciliationStatus

    internal_amount: int | None = None
    external_amount: int

    internal_currency: str | None = None
    external_currency: str

    internal_status: str | None = None
    external_status: str


class ReconciliationReport(BaseModel):
    total: int
    matched: int
    mismatched: int

    items: list[ReconciliationItem]
