import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class WebhookEndpointCreate(BaseModel):
    url: HttpUrl


class WebhookEndpointRead(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    url: str
    secret: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
