import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.merchant import Merchant
from app.models.webhook import WebhookEndpoint
from app.schemas.webhook import (
    WebhookEndpointCreate,
    WebhookEndpointRead,
)

router = APIRouter(
    prefix="/merchants",
    tags=["webhooks"],
)


@router.post(
    "/{merchant_id}/webhooks",
    response_model=WebhookEndpointRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook_endpoint(
    merchant_id: uuid.UUID,
    data: WebhookEndpointCreate,
    db: AsyncSession = Depends(get_db),
):
    async with db.begin():
        merchant = await db.get(
            Merchant,
            merchant_id,
        )

        if merchant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant not found",
            )

        endpoint = WebhookEndpoint(
            merchant_id=merchant_id,
            url=str(data.url),
            secret=secrets.token_hex(32),
        )

        db.add(endpoint)

    await db.refresh(endpoint)

    return endpoint
