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
from app.models.refund import Refund
from app.services.webhooks import enqueue_webhook_event


async def refund_payment(
    payment_id: uuid.UUID,
    db: AsyncSession,
) -> Refund:
    async with db.begin():
        # Lock payment so concurrent refunds cannot both succeed.
        result = await db.execute(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )

        payment = result.scalar_one_or_none()

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )

        if payment.status != PaymentStatus.CAPTURED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Payment cannot be refunded from {payment.status.value} status"
                ),
            )

        # Processor clearing account
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

        # Merchant account
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

        # Create refund
        refund = Refund(
            payment_id=payment.id,
            amount=payment.amount,
        )

        db.add(refund)

        # Create refund ledger transaction
        ledger_transaction = LedgerTransaction(
            payment_id=payment.id,
            transaction_type=LedgerTransactionType.REFUND,
            description=f"Refund payment {payment.id}",
        )

        db.add(ledger_transaction)

        await db.flush()

        # Reverse the capture entries.
        #
        # Capture:
        # processor DEBIT
        # merchant  CREDIT
        #
        # Refund:
        # merchant  DEBIT
        # processor CREDIT

        merchant_debit = LedgerEntry(
            transaction_id=ledger_transaction.id,
            account_id=merchant_account.id,
            direction=LedgerEntryDirection.DEBIT,
            amount=payment.amount,
        )

        processor_credit = LedgerEntry(
            transaction_id=ledger_transaction.id,
            account_id=processor_account.id,
            direction=LedgerEntryDirection.CREDIT,
            amount=payment.amount,
        )

        db.add_all(
            [
                merchant_debit,
                processor_credit,
            ]
        )

        payment.status = PaymentStatus.REFUNDED

        await db.flush()

        await enqueue_webhook_event(
            db=db,
            merchant_id=payment.merchant_id,
            event_type="payment.refunded",
            payload={
                "payment_id": str(payment.id),
                "merchant_id": str(payment.merchant_id),
                "refund_id": str(refund.id),
                "amount": refund.amount,
                "currency": payment.currency,
                "status": PaymentStatus.REFUNDED.value,
            },
        )

    await db.refresh(refund)

    return refund
