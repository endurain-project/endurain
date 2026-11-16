"""Retire the v0.20 data migrations and align the schema with the models

The steps run in this order.

Retire the v0.20 data migrations
--------------------------------

The handlers of data migrations 1-6 and 8-10 are removed, so their rows leave the ``migrations`` table. The upgrade
source is v0.20.x, which revision 1 enforces: it refuses while one of them is pending. Row 7 stays, since it is
executed on every install.

The running cadence normalisation never ran in production, so ``cadence_spm_migration_rows``, the bookkeeping
table of its downgrade, goes too.

The UUID conversion revisions that follow are the one-time exception to the events guide's rule to raise a payload
class's ``SCHEMA_VERSION``: they rewrite the integer ids inside stored event payloads in place and keep every
payload class's version. After the rewrite no integer-shaped payload remains, and every process is stopped during the
upgrade, so no old build can publish one.

The revision is irreversible.

Align the schema with the models
--------------------------------

``activity_sets.start_time`` becomes ``timestamptz``; the naive values are read in the session time zone (UTC, which
the application's engine pins), the way the application wrote them. Four column comments follow the model text.

Revision ID: 3e7a91d4c0b8
Revises: b84e9f3a6c25
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3e7a91d4c0b8"
down_revision: str | None = "b84e9f3a6c25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade_retire_old_data_migrations() -> None:
    """Delete the retired data migration rows and drop the cadence normalisation bookkeeping table."""
    op.execute(sa.text("DELETE FROM migrations WHERE id IN (1, 2, 3, 4, 5, 6, 8, 9, 10)"))
    op.execute(sa.text("DROP TABLE cadence_spm_migration_rows"))


def downgrade_retire_old_data_migrations() -> None:
    """Refuse to downgrade.

    Raises:
        NotImplementedError: Always; the deleted rows and the dropped table cannot be rebuilt.
    """
    raise NotImplementedError(
        "Retiring the data migrations cannot be reversed: restore the database from the backup taken before "
        "the upgrade."
    )


# (table, column, existing type, nullable, old comment, new comment)
_COMMENTS = (
    (
        "activity_ingestion_jobs",
        "id",
        sa.String(length=36),
        False,
        "Upload job identifier (UUIDv4 string)",
        "Ingestion job identifier (UUIDv4 string)",
    ),
    (
        "activity_ingestion_jobs",
        "user_id",
        sa.Integer(),
        False,
        "User that owns the upload",
        "User that owns the ingestion request",
    ),
    (
        "activity_ingestion_jobs",
        "created_at",
        sa.DateTime(timezone=True),
        False,
        "When the upload was accepted",
        "When the request was accepted",
    ),
    (
        "health_record_deletions",
        "record_type",
        sa.String(length=50),
        False,
        "Sync type of the record",
        "Sync type of the deleted record, e.g. health_weight",
    ),
)


def upgrade_align_schema_with_models() -> None:
    """Make ``activity_sets.start_time`` timezone-aware and update the four column comments."""
    op.alter_column(
        "activity_sets",
        "start_time",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        existing_comment="Workout set start date",
    )
    for table, column, existing_type, nullable, old_comment, new_comment in _COMMENTS:
        op.alter_column(
            table,
            column,
            existing_type=existing_type,
            existing_nullable=nullable,
            existing_comment=old_comment,
            comment=new_comment,
        )


def downgrade_align_schema_with_models() -> None:
    """Restore the naive ``activity_sets.start_time`` and the four earlier column comments."""
    for table, column, existing_type, nullable, old_comment, new_comment in _COMMENTS:
        op.alter_column(
            table,
            column,
            existing_type=existing_type,
            existing_nullable=nullable,
            existing_comment=new_comment,
            comment=old_comment,
        )
    op.alter_column(
        "activity_sets",
        "start_time",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        existing_comment="Workout set start date",
    )


def upgrade() -> None:
    """Run every step in order."""
    upgrade_retire_old_data_migrations()
    upgrade_align_schema_with_models()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_align_schema_with_models()
    downgrade_retire_old_data_migrations()
