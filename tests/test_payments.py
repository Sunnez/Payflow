import uuid

from sqlalchemy import delete, select

from app.models.ledger import (
    LedgerAccount,
    LedgerAccountType,
    LedgerEntry,
    LedgerEntryDirection,
    LedgerTransaction,
)
from tests.conftest import TestSessionLocal


async def create_merchant(
    client,
    name: str = "Test Merchant",
):
    response = await client.post(
        "/merchants",
        json={
            "name": name,
        },
    )

    assert response.status_code == 201

    return response.json()


async def create_payment(
    client,
    merchant_id: str,
    amount: int = 2500,
    idempotency_key: str = "order-test-001",
):
    response = await client.post(
        "/payments",
        headers={
            "Idempotency-Key": idempotency_key,
        },
        json={
            "merchant_id": merchant_id,
            "amount": amount,
            "currency": "EUR",
        },
    )

    assert response.status_code == 201

    return response.json()


async def authorize_payment(
    client,
    payment_id: str,
):
    return await client.post(f"/payments/{payment_id}/authorize")


async def capture_payment(
    client,
    payment_id: str,
):
    return await client.post(f"/payments/{payment_id}/capture")


async def refund_payment(
    client,
    payment_id: str,
):
    return await client.post(f"/payments/{payment_id}/refund")


async def get_ledger_entries(
    payment_id: str,
):
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(LedgerEntry)
            .join(
                LedgerTransaction,
                LedgerEntry.transaction_id == LedgerTransaction.id,
            )
            .where(LedgerTransaction.payment_id == uuid.UUID(payment_id))
        )

        return list(result.scalars().all())


async def test_create_payment(client):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
    )

    assert payment["merchant_id"] == merchant["id"]
    assert payment["amount"] == 2500
    assert payment["currency"] == "EUR"
    assert payment["status"] == "pending"


async def test_payment_idempotency(client):
    merchant = await create_merchant(client)

    first = await create_payment(
        client,
        merchant["id"],
        idempotency_key="same-order-001",
    )

    second = await create_payment(
        client,
        merchant["id"],
        idempotency_key="same-order-001",
    )

    assert first["id"] == second["id"]


async def test_idempotency_conflict(client):
    merchant = await create_merchant(client)

    await create_payment(
        client,
        merchant["id"],
        amount=2500,
        idempotency_key="conflict-order",
    )

    response = await client.post(
        "/payments",
        headers={
            "Idempotency-Key": "conflict-order",
        },
        json={
            "merchant_id": merchant["id"],
            "amount": 9999,
            "currency": "EUR",
        },
    )

    assert response.status_code == 409


async def test_payment_lifecycle(client):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
    )

    response = await authorize_payment(
        client,
        payment["id"],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "authorized"

    response = await capture_payment(
        client,
        payment["id"],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "captured"


async def test_cannot_capture_pending_payment(client):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
    )

    response = await capture_payment(
        client,
        payment["id"],
    )

    assert response.status_code == 409


async def test_capture_creates_balanced_ledger(client):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
        amount=5000,
    )

    await authorize_payment(
        client,
        payment["id"],
    )

    response = await capture_payment(
        client,
        payment["id"],
    )

    assert response.status_code == 200

    entries = await get_ledger_entries(payment["id"])

    assert len(entries) == 2

    total_debit = sum(
        entry.amount
        for entry in entries
        if entry.direction == LedgerEntryDirection.DEBIT
    )

    total_credit = sum(
        entry.amount
        for entry in entries
        if entry.direction == LedgerEntryDirection.CREDIT
    )

    assert total_debit == 5000
    assert total_credit == 5000

    assert total_debit == total_credit


async def test_payment_cannot_be_captured_twice(client):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
    )

    await authorize_payment(
        client,
        payment["id"],
    )

    first_capture = await capture_payment(
        client,
        payment["id"],
    )

    assert first_capture.status_code == 200

    second_capture = await capture_payment(
        client,
        payment["id"],
    )

    assert second_capture.status_code == 409

    entries = await get_ledger_entries(payment["id"])

    assert len(entries) == 2


async def test_refund_creates_reverse_ledger_entries(client):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
        amount=7500,
    )

    await authorize_payment(
        client,
        payment["id"],
    )

    await capture_payment(
        client,
        payment["id"],
    )

    refund_response = await refund_payment(
        client,
        payment["id"],
    )

    assert refund_response.status_code == 201

    refund = refund_response.json()

    assert refund["amount"] == 7500
    assert refund["status"] == "completed"

    payment_response = await client.get(f"/payments/{payment['id']}")

    assert payment_response.json()["status"] == "refunded"

    entries = await get_ledger_entries(payment["id"])

    assert len(entries) == 4

    total_debit = sum(
        entry.amount
        for entry in entries
        if entry.direction == LedgerEntryDirection.DEBIT
    )

    total_credit = sum(
        entry.amount
        for entry in entries
        if entry.direction == LedgerEntryDirection.CREDIT
    )

    assert total_debit == 15000
    assert total_credit == 15000

    assert total_debit == total_credit


async def test_payment_cannot_be_refunded_twice(client):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
    )

    await authorize_payment(
        client,
        payment["id"],
    )

    await capture_payment(
        client,
        payment["id"],
    )

    first_refund = await refund_payment(
        client,
        payment["id"],
    )

    assert first_refund.status_code == 201

    second_refund = await refund_payment(
        client,
        payment["id"],
    )

    assert second_refund.status_code == 409

    entries = await get_ledger_entries(payment["id"])

    assert len(entries) == 4


async def test_capture_rolls_back_on_ledger_failure(client):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
    )

    await authorize_payment(
        client,
        payment["id"],
    )

    async with TestSessionLocal() as session:
        await session.execute(
            delete(LedgerAccount).where(
                LedgerAccount.account_type == LedgerAccountType.PROCESSOR_CLEARING
            )
        )

        await session.commit()

    response = await capture_payment(
        client,
        payment["id"],
    )

    assert response.status_code == 500

    payment_response = await client.get(f"/payments/{payment['id']}")

    assert payment_response.status_code == 200

    assert payment_response.json()["status"] == "authorized"

    entries = await get_ledger_entries(payment["id"])

    assert len(entries) == 0


async def test_reconciliation_detects_matches_and_mismatches(
    client,
):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
        amount=5000,
    )

    await authorize_payment(
        client,
        payment["id"],
    )

    await capture_payment(
        client,
        payment["id"],
    )

    csv_content = (
        "payment_id,amount,currency,status\n"
        f"{payment['id']},5000,EUR,captured\n"
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,"
        "1000,EUR,captured\n"
    )

    response = await client.post(
        "/reconciliation",
        files={
            "file": (
                "transactions.csv",
                csv_content,
                "text/csv",
            )
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 2
    assert data["matched"] == 1
    assert data["mismatched"] == 1

    assert data["items"][0]["result"] == "matched"

    assert data["items"][1]["result"] == "missing"


async def test_high_risk_payment_cannot_be_authorized(
    client,
):
    merchant = await create_merchant(client)

    payment = await create_payment(
        client,
        merchant["id"],
        amount=500_000,
        idempotency_key="high-risk-order",
    )

    assert payment["risk_level"] == "high"

    assert payment["risk_score"] >= 60

    response = await authorize_payment(
        client,
        payment["id"],
    )

    assert response.status_code == 409

    assert response.json()["detail"] == ("High-risk payment requires manual review")
