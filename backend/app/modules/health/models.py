"""SQLAlchemy ORM model of the deleted health records."""

import uuid

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

import core.sync as core_sync
from core.database import Base


class HealthRecordDeletion(core_sync.TombstoneMixin, Base):
    """A health record that was deleted, kept so incremental sync can tell a client.

    One table serves every health record type; ``record_type`` is the record's sync type.

    Attributes:
        record_id: The id the deleted record had.
        record_type: The sync type of the deleted record, e.g. ``health_weight``.
    """

    __tablename__ = "health_record_deletions"
    __table_args__ = (Index("ix_health_record_deletions_user_deleted_at_id", "user_id", "deleted_at", "id"),)

    record_id: Mapped[uuid.UUID] = mapped_column(nullable=False, comment="The id the deleted record had")
    record_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Sync type of the deleted record, e.g. health_weight"
    )
