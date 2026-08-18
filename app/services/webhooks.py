import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import (
    WebhookDelivery,
    WebhookEndpoint,
)


async def enqueue_webhook_event(
    db: AsyncSession,
    merchant_id: uuid.UUID,
    event_type: str,
    payload: dict,
) -> None:
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.merchant_id == merchant_id,
            WebhookEndpoint.is_active.is_(True),
        )
    )

    endpoints = result.scalars().all()

    for endpoint in endpoints:
        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            event_type=event_type,
            payload=payload,
        )

        db.add(delivery)
