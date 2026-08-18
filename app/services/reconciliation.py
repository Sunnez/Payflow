import csv
import io
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.schemas.reconciliation import (
    ReconciliationItem,
    ReconciliationReport,
    ReconciliationStatus,
)


async def reconcile_csv(
    content: bytes,
    db: AsyncSession,
) -> ReconciliationReport:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must be UTF-8 encoded",
        )

    reader = csv.DictReader(io.StringIO(text))

    required_columns = {
        "payment_id",
        "amount",
        "currency",
        "status",
    }

    if reader.fieldnames is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV is empty",
        )

    if not required_columns.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("CSV must contain payment_id, amount, currency and status"),
        )

    items: list[ReconciliationItem] = []

    for row_number, row in enumerate(
        reader,
        start=2,
    ):
        try:
            payment_id = uuid.UUID(row["payment_id"])

            external_amount = int(row["amount"])

            external_currency = row["currency"].strip().upper()

            external_status = row["status"].strip().lower()

        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(f"Invalid data at CSV row {row_number}"),
            )

        payment = await db.get(
            Payment,
            payment_id,
        )

        if payment is None:
            items.append(
                ReconciliationItem(
                    payment_id=payment_id,
                    result=ReconciliationStatus.MISSING,
                    external_amount=external_amount,
                    external_currency=external_currency,
                    external_status=external_status,
                )
            )

            continue

        if payment.amount != external_amount:
            result = ReconciliationStatus.AMOUNT_MISMATCH

        elif payment.currency != external_currency:
            result = ReconciliationStatus.CURRENCY_MISMATCH

        elif payment.status.value != external_status:
            result = ReconciliationStatus.STATUS_MISMATCH

        else:
            result = ReconciliationStatus.MATCHED

        items.append(
            ReconciliationItem(
                payment_id=payment.id,
                result=result,
                internal_amount=payment.amount,
                external_amount=external_amount,
                internal_currency=payment.currency,
                external_currency=external_currency,
                internal_status=payment.status.value,
                external_status=external_status,
            )
        )

    matched = sum(1 for item in items if item.result == ReconciliationStatus.MATCHED)

    return ReconciliationReport(
        total=len(items),
        matched=matched,
        mismatched=len(items) - matched,
        items=items,
    )
