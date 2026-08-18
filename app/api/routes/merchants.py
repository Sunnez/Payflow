from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.ledger import LedgerAccount, LedgerAccountType
from app.models.merchant import Merchant
from app.schemas.merchant import MerchantCreate, MerchantRead

router = APIRouter(
    prefix="/merchants",
    tags=["merchants"],
)


@router.post(
    "",
    response_model=MerchantRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_merchant(
    data: MerchantCreate,
    db: AsyncSession = Depends(get_db),
):
    async with db.begin():
        merchant = Merchant(
            name=data.name,
        )

        db.add(merchant)

        await db.flush()

        ledger_account = LedgerAccount(
            code=f"merchant:{merchant.id}",
            account_type=LedgerAccountType.MERCHANT_PAYABLE,
            merchant_id=merchant.id,
        )

        db.add(ledger_account)

    await db.refresh(merchant)

    return merchant


@router.get(
    "",
    response_model=list[MerchantRead],
)
async def get_merchants(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Merchant))

    merchants = result.scalars().all()

    return merchants
