import hashlib
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.merchant import Merchant
from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate, PaymentRead
from app.schemas.refund import RefundRead
from app.services.payments import (
    capture_payment_with_ledger,
    change_payment_status,
)
from app.services.refunds import refund_payment
from app.services.risk import assess_payment_risk

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
)


def build_request_hash(data: PaymentCreate) -> str:
    payload = json.dumps(
        data.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@router.post(
    "",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    data: PaymentCreate,
    idempotency_key: Annotated[
        str,
        Header(
            min_length=8,
            max_length=255,
        ),
    ],
    db: AsyncSession = Depends(get_db),
):
    merchant = await db.get(
        Merchant,
        data.merchant_id,
    )

    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found",
        )

    request_hash = build_request_hash(data)

    query = select(Payment).where(
        Payment.merchant_id == data.merchant_id,
        Payment.idempotency_key == idempotency_key,
    )

    result = await db.execute(query)
    existing_payment = result.scalar_one_or_none()

    if existing_payment is not None:
        if existing_payment.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Idempotency key has already been used with different payment data"
                ),
            )

        return existing_payment

    risk_score, risk_level, risk_reasons = await assess_payment_risk(
        db=db,
        merchant=merchant,
        amount=data.amount,
        currency=data.currency,
    )

    payment = Payment(
        merchant_id=data.merchant_id,
        amount=data.amount,
        currency=data.currency,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        risk_score=risk_score,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
    )

    db.add(payment)

    try:
        await db.commit()

    except IntegrityError:
        await db.rollback()

        result = await db.execute(query)
        existing_payment = result.scalar_one_or_none()

        if existing_payment is None:
            raise

        if existing_payment.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Idempotency key has already been used with different payment data"
                ),
            )

        return existing_payment

    await db.refresh(payment)

    return payment


@router.post(
    "/{payment_id}/authorize",
    response_model=PaymentRead,
)
async def authorize_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await change_payment_status(
        payment_id=payment_id,
        expected_status=PaymentStatus.PENDING,
        new_status=PaymentStatus.AUTHORIZED,
        db=db,
    )


@router.post(
    "/{payment_id}/capture",
    response_model=PaymentRead,
)
async def capture_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await capture_payment_with_ledger(
        payment_id=payment_id,
        db=db,
    )


@router.post(
    "/{payment_id}/fail",
    response_model=PaymentRead,
)
async def fail_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await change_payment_status(
        payment_id=payment_id,
        expected_status=PaymentStatus.PENDING,
        new_status=PaymentStatus.FAILED,
        db=db,
    )


@router.post(
    "/{payment_id}/refund",
    response_model=RefundRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_refund(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await refund_payment(
        payment_id=payment_id,
        db=db,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentRead,
)
async def get_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    payment = await db.get(
        Payment,
        payment_id,
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return payment
