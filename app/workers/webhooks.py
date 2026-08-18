import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import or_, select

from app.core.webhook_signature import (
    generate_webhook_signature,
)
from app.db.session import SessionLocal
from app.models.webhook import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEndpoint,
)

MAX_ATTEMPTS = 3

RETRY_DELAYS = {
    1: 10,
    2: 60,
    3: 300,
}


async def send_delivery(
    delivery_id: uuid.UUID,
) -> None:
    #
    # First read everything we need from DB.
    #
    async with SessionLocal() as db:
        delivery = await db.get(
            WebhookDelivery,
            delivery_id,
        )

        if delivery is None:
            return

        endpoint = await db.get(
            WebhookEndpoint,
            delivery.endpoint_id,
        )

        if endpoint is None:
            return

        endpoint_url = endpoint.url
        endpoint_secret = endpoint.secret
        event_type = delivery.event_type
        payload = delivery.payload

    body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    signature = generate_webhook_signature(
        endpoint_secret,
        body,
    )

    status_code = None
    error = None
    success = False

    try:
        async with httpx.AsyncClient(
            timeout=5.0,
        ) as client:
            response = await client.post(
                endpoint_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-PayFlow-Event": event_type,
                    "X-PayFlow-Signature": signature,
                    "X-PayFlow-Delivery": str(delivery_id),
                },
            )

        status_code = response.status_code

        success = 200 <= response.status_code < 300

        if not success:
            error = f"Webhook returned HTTP {response.status_code}"

    except httpx.HTTPError as exc:
        error = str(exc)

    #
    # Update DB only after the network request is finished.
    #
    async with SessionLocal() as db:
        async with db.begin():
            delivery = await db.get(
                WebhookDelivery,
                delivery_id,
            )

            if delivery is None:
                return

            delivery.attempts += 1
            delivery.last_status_code = status_code
            delivery.last_error = error

            if success:
                delivery.status = WebhookDeliveryStatus.DELIVERED

                delivery.delivered_at = datetime.now(timezone.utc)

                delivery.next_attempt_at = None

                return

            if delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = WebhookDeliveryStatus.FAILED

                delivery.next_attempt_at = None

                return

            delivery.status = WebhookDeliveryStatus.RETRY

            delay = RETRY_DELAYS[delivery.attempts]

            delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                seconds=delay
            )


async def get_due_deliveries() -> list[uuid.UUID]:
    now = datetime.now(timezone.utc)

    async with SessionLocal() as db:
        result = await db.execute(
            select(WebhookDelivery.id)
            .where(
                WebhookDelivery.status.in_(
                    [
                        WebhookDeliveryStatus.PENDING,
                        WebhookDeliveryStatus.RETRY,
                    ]
                ),
                or_(
                    WebhookDelivery.next_attempt_at.is_(None),
                    WebhookDelivery.next_attempt_at <= now,
                ),
            )
            .limit(20)
        )

        return list(result.scalars().all())


async def run_worker() -> None:
    print("PayFlow webhook worker started")

    while True:
        deliveries = await get_due_deliveries()

        for delivery_id in deliveries:
            await send_delivery(delivery_id)

        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(
        run_worker(),
        loop_factory=asyncio.SelectorEventLoop,
    )
