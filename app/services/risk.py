from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant
from app.models.payment import Payment


async def assess_payment_risk(
    db: AsyncSession,
    merchant: Merchant,
    amount: int,
    currency: str,
) -> tuple[int, str, list[str]]:
    score = 0
    reasons: list[str] = []

    #
    # Rule 1: transaction size
    #
    if amount >= 500_000:
        score += 60
        reasons.append("Very large transaction")

    elif amount >= 100_000:
        score += 30
        reasons.append("Large transaction")

    #
    # Rule 2: new merchant
    #
    now = datetime.now(timezone.utc)

    if merchant.created_at >= (now - timedelta(days=1)):
        score += 15
        reasons.append("Merchant created less than 24 hours ago")

    #
    # Rule 3: payment velocity
    #
    one_hour_ago = now - timedelta(hours=1)

    result = await db.execute(
        select(func.count(Payment.id)).where(
            Payment.merchant_id == merchant.id,
            Payment.created_at >= one_hour_ago,
        )
    )

    recent_payment_count = result.scalar_one()

    if recent_payment_count >= 10:
        score += 25
        reasons.append("High payment velocity")

    #
    # Rule 4: unusual currency
    #
    if currency not in {
        "EUR",
        "USD",
    }:
        score += 20
        reasons.append("Unusual currency")

    score = min(
        score,
        100,
    )

    if score >= 60:
        level = "high"

    elif score >= 30:
        level = "medium"

    else:
        level = "low"

    return (
        score,
        level,
        reasons,
    )
