import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LedgerAccountType(str, enum.Enum):
    PROCESSOR_CLEARING = "processor_clearing"
    MERCHANT_PAYABLE = "merchant_payable"


class LedgerEntryDirection(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class LedgerTransactionType(str, enum.Enum):
    CAPTURE = "capture"
    REFUND = "refund"


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"

    __table_args__ = (
        UniqueConstraint(
            "merchant_id",
            name="uq_ledger_accounts_merchant",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    code: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    account_type: Mapped[LedgerAccountType] = mapped_column(
        Enum(
            LedgerAccountType,
            name="ledger_account_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    merchant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("merchants.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "transaction_type",
            name="uq_ledger_transaction_payment_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id"),
        nullable=False,
        index=True,
    )

    transaction_type: Mapped[LedgerTransactionType] = mapped_column(
        Enum(
            LedgerTransactionType,
            name="ledger_transaction_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_ledger_entries_positive_amount",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ledger_transactions.id"),
        nullable=False,
        index=True,
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ledger_accounts.id"),
        nullable=False,
        index=True,
    )

    direction: Mapped[LedgerEntryDirection] = mapped_column(
        Enum(
            LedgerEntryDirection,
            name="ledger_entry_direction",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
