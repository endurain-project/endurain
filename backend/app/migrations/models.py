"""Migration tracking database models."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Migration(Base):
    """Tracks data migration execution state.

    Attributes:
        id: Primary key.
        name: Migration name (max 250 chars).
        description: Migration description (max 2500 chars).
        executed: Whether the migration has been executed.
    """

    __tablename__ = "migrations"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        comment="Migration name",
    )
    description: Mapped[str] = mapped_column(
        String(2500),
        nullable=False,
        comment="Migration description",
    )
    executed: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether the migration was executed",
    )
