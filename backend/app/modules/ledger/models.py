from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseEntity


class LedgerEntry(BaseEntity):
    """Append-only hash-chain entry. Each row links to the previous via SHA256.

    Tampering with any entry invalidates the chain on `verify()`. For external
    anchoring, periodically post `tip_hash` to a public blockchain.
    """

    __tablename__ = "ledger_entries"

    seq: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), index=True)
    resource_id: Mapped[int | None] = mapped_column(Integer, index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    this_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    actor_id: Mapped[int | None] = mapped_column(Integer)
