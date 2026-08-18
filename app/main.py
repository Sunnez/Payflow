from fastapi import FastAPI

from app.api.routes.merchants import router as merchants_router
from app.api.routes.payments import router as payments_router
from app.api.routes.reconciliation import router as reconciliation_router
from app.api.routes.webhooks import router as webhooks_router

app = FastAPI(
    title="PayFlow",
    description="FinTech payment processing and automation platform",
    version="0.1.0",
)

app.include_router(merchants_router)
app.include_router(payments_router)
app.include_router(webhooks_router)
app.include_router(reconciliation_router)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "payflow",
    }
