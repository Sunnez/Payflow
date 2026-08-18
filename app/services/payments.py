import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger import (
    LedgerAccount,
    LedgerAccountType,
    LedgerEntry,
    LedgerEntryDirection,
    LedgerTransaction,
    LedgerTransactionType,
)
from app.models.payment import Payment, PaymentStatus
from app.services.webhooks import enqueue_webhook_event


async def change_payment_status(
    payment_id: uuid.UUID,
    expected_status: PaymentStatus,
    new_status: PaymentStatus,
    db: AsyncSession,
) -> Payment:
    async with db.begin():
        query = select(Payment).where(Payment.id == payment_id).with_for_update()

        result = await db.execute(query)
        payment = result.scalar_one_or_none()

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )

        if payment.status != expected_status:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Payment cannot transition from "
                    f"{payment.status.value} to {new_status.value}"
                ),
            )
        if new_status == PaymentStatus.AUTHORIZED and payment.risk_level == "high":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("High-risk payment requires manual review"),
            )

        payment.status = new_status
        event_names = {
            PaymentStatus.AUTHORIZED: "payment.authorized",
            PaymentStatus.FAILED: "payment.failed",
        }

        event_type = event_names.get(new_status)

        if event_type is not None:
            await enqueue_webhook_event(
                db=db,
                merchant_id=payment.merchant_id,
                event_type=event_type,
                payload={
                    "payment_id": str(payment.id),
                    "merchant_id": str(payment.merchant_id),
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "status": new_status.value,
                },
            )

    return payment


async def capture_payment_with_ledger(
    payment_id: uuid.UUID,
    db: AsyncSession,
) -> Payment:
    async with db.begin():
        # Lock payment
        query = select(Payment).where(Payment.id == payment_id).with_for_update()

        result = await db.execute(query)
        payment = result.scalar_one_or_none()

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )

        if payment.status != PaymentStatus.AUTHORIZED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Payment cannot transition from {payment.status.value} to captured"
                ),
            )

        # Find processor clearing account
        result = await db.execute(
            select(LedgerAccount).where(
                LedgerAccount.account_type == LedgerAccountType.PROCESSOR_CLEARING
            )
        )

        processor_account = result.scalar_one_or_none()

        if processor_account is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Processor ledger account not configured",
            )

        # Find merchant payable account
        result = await db.execute(
            select(LedgerAccount).where(
                LedgerAccount.merchant_id == payment.merchant_id
            )
        )

        merchant_account = result.scalar_one_or_none()

        if merchant_account is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Merchant ledger account not configured",
            )

        # Create ledger transaction
        ledger_transaction = LedgerTransaction(
            payment_id=payment.id,
            transaction_type=LedgerTransactionType.CAPTURE,
            description=f"Capture payment {payment.id}",
        )

        db.add(ledger_transaction)

        await db.flush()

        # DEBIT processor clearing
        debit_entry = LedgerEntry(
            transaction_id=ledger_transaction.id,
            account_id=processor_account.id,
            direction=LedgerEntryDirection.DEBIT,
            amount=payment.amount,
        )

        # CREDIT merchant payable
        credit_entry = LedgerEntry(
            transaction_id=ledger_transaction.id,
            account_id=merchant_account.id,
            direction=LedgerEntryDirection.CREDIT,
            amount=payment.amount,
        )

        db.add_all(
            [
                debit_entry,
                credit_entry,
            ]
        )

        payment.status = PaymentStatus.CAPTURED

        await enqueue_webhook_event(
            db=db,
            merchant_id=payment.merchant_id,
            event_type="payment.captured",
            payload={
                "payment_id": str(payment.id),
                "merchant_id": str(payment.merchant_id),
                "amount": payment.amount,
                "currency": payment.currency,
                "status": PaymentStatus.CAPTURED.value,
            },
        )

    await db.refresh(payment)

    return payment
