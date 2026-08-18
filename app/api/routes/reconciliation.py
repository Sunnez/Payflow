from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.reconciliation import (
    ReconciliationReport,
)
from app.services.reconciliation import (
    reconcile_csv,
)

router = APIRouter(
    prefix="/reconciliation",
    tags=["reconciliation"],
)


@router.post(
    "",
    response_model=ReconciliationReport,
)
async def reconcile_payments(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()

    return await reconcile_csv(
        content=content,
        db=db,
    )
