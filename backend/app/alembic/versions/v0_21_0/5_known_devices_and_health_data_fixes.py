"""Known devices and cleaning of stored health data

The steps run in this order.

Add auth_known_devices for new-device sign-in notices
-----------------------------------------------------

Each row is a browser a user signed in from, named by the SHA-256 hex digest of the device id its cookie holds,
never the id itself. A sign-in from a device the user has no row for sends a notice. The table starts empty, so the
first sign-in of each user after the upgrade registers a device without one.

Store the audit trail retention and legal hold in the database
--------------------------------------------------------------

Adds ``audit_retention_days`` and ``audit_legal_hold`` to ``server_settings``, so an
administrator edits them at run time. A retention is 0 (keep everything) or between the
audit trail's database-side floor of 30 days and the substrate's maximum of 36500 days.

Clear stored weight BMIs outside the valid range
------------------------------------------------

A BMI above 100 (for example from a height typed in the wrong unit) made every read of
the user's weight records fail validation. The calculation now leaves such a BMI empty;
this clears the ones already stored.

Delete health records dated before 1900
---------------------------------------

A record dated before 1900 (a mistyped year) cannot be a real measurement and broke the charts
that group records by day. Requests are now refused for such dates; this deletes the records
already stored.

Derive the stored duration of every ended fasting session
---------------------------------------------------------

The duration of a fasting session was written by the client and not recalculated when its times were
edited, so it drifted from the start and end times the statistics are meant to reflect. The server now
derives it; this recomputes the ones already stored for sessions that have an end time.

A session whose end is before its start has no valid duration and is left as it is.

Mark in-progress fasting sessions that have an end time as completed
--------------------------------------------------------------------

A fasting session could be saved as in progress with an end time. Such a session counted as the running
fast, was given a duration and blocked starting a new one. The server now refuses the combination; this
turns the ones already stored into completed sessions, keeping their end time and duration. A duration
that was never stored is derived from the session's times, as the fasting duration derivation does, unless the end is
before the start.

Register the image-metadata strip data migration
------------------------------------------------

Revision ID: f2c6a9d4b871
Revises: 9e4b7a2d6c18
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from datetime import UTC, date, datetime

# revision identifiers, used by Alembic.
revision: str = "f2c6a9d4b871"
down_revision: str | None = "9e4b7a2d6c18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "auth_known_devices"

_PRUNE_INDEX = "ix_auth_known_devices_last_seen_at"


def upgrade_add_auth_known_devices() -> None:
    """Create ``auth_known_devices`` with its per-user unique device and the index the prune filters on."""
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="User who signed in from the device"),
        sa.Column(
            "device_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hex digest of the device id held in the browser's cookie",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="First sign-in from the device"),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Last sign-in from the device; the row is pruned 400 days after it",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "device_hash", name="uq_auth_known_devices_user_id_device_hash"),
    )
    op.create_index(_PRUNE_INDEX, _TABLE, ["last_seen_at"], unique=False)


def downgrade_add_auth_known_devices() -> None:
    """Drop ``auth_known_devices``."""
    op.drop_index(_PRUNE_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)


def upgrade_add_audit_retention_settings() -> None:
    """Add the audit retention and legal hold columns and the retention check constraint."""
    op.add_column(
        "server_settings",
        sa.Column(
            "audit_retention_days",
            sa.Integer(),
            server_default=sa.text("90"),
            nullable=False,
            comment="Days after which audit trail partitions are dropped (0 - never)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "audit_legal_hold",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Suspend all pruning of the audit trail (true - yes, false - no)",
        ),
    )
    op.create_check_constraint(
        "audit_retention_days_check",
        "server_settings",
        "audit_retention_days = 0 OR audit_retention_days BETWEEN 30 AND 36500",
    )


def downgrade_add_audit_retention_settings() -> None:
    """Drop the check constraint and both columns."""
    op.drop_constraint("audit_retention_days_check", "server_settings", type_="check")
    op.drop_column("server_settings", "audit_legal_hold")
    op.drop_column("server_settings", "audit_retention_days")


def upgrade_clear_out_of_range_weight_bmi() -> None:
    """Set the BMI of every weight record outside 0 to 100 to NULL, bumping the version a client's ETag names."""
    op.execute(sa.text("UPDATE health_weight SET bmi = NULL, version = version + 1 WHERE bmi > 100 OR bmi < 0"))


def downgrade_clear_out_of_range_weight_bmi() -> None:
    """Keep the cleared values: the BMI they held was not valid and cannot be recovered."""


_EARLIEST_DATE = date(1900, 1, 1)

_EARLIEST_DATETIME = datetime(1900, 1, 1, tzinfo=UTC)

# table -> (column that dates the record, the column's type, the earliest value it may hold)
_DATED = {
    "health_steps": ("date", sa.Date(), _EARLIEST_DATE),
    "health_water": ("date", sa.Date(), _EARLIEST_DATE),
    "health_weight": ("date", sa.Date(), _EARLIEST_DATE),
    "health_sleep": ("date", sa.Date(), _EARLIEST_DATE),
    "health_poop": ("date_time", sa.DateTime(timezone=True), _EARLIEST_DATETIME),
    "health_fasting": ("fast_start_time", sa.DateTime(timezone=True), _EARLIEST_DATETIME),
}


def upgrade_delete_health_records_before_1900() -> None:
    """Delete every record that is dated before 1900-01-01."""
    for table_name, (column_name, column_type, earliest) in _DATED.items():
        table = sa.table(table_name, sa.column(column_name, column_type))
        op.execute(sa.delete(table).where(table.c[column_name] < earliest))


def downgrade_delete_health_records_before_1900() -> None:
    """Keep the deleted records gone: they were invalid and cannot be restored."""


_derive_fasting_durations_health_fasting = sa.table(
    "health_fasting",
    sa.column("id", sa.Integer),
    sa.column("fast_start_time", sa.DateTime(timezone=True)),
    sa.column("fast_end_time", sa.DateTime(timezone=True)),
    sa.column("actual_duration_seconds", sa.Integer),
    sa.column("version", sa.Integer),
)


def _derive_fasting_durations_utc(moment: datetime) -> datetime:
    """Return a stored time as UTC; a database that keeps no offset holds UTC."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def upgrade_derive_fasting_durations() -> None:
    """Set the duration of each ended session to the seconds between its times, bumping the version when it changes."""
    connection = op.get_bind()
    stale = []
    rows = connection.execute(
        sa.select(
            _derive_fasting_durations_health_fasting.c.id,
            _derive_fasting_durations_health_fasting.c.fast_start_time,
            _derive_fasting_durations_health_fasting.c.fast_end_time,
            _derive_fasting_durations_health_fasting.c.actual_duration_seconds,
        ).where(_derive_fasting_durations_health_fasting.c.fast_end_time.is_not(None))
    )
    for fast_id, start, end, stored in rows:
        duration = int((_derive_fasting_durations_utc(end) - _derive_fasting_durations_utc(start)).total_seconds())
        if duration >= 0 and duration != stored:
            stale.append({"fast_id": fast_id, "duration": duration})
    if stale:
        connection.execute(
            sa.update(_derive_fasting_durations_health_fasting)
            .where(_derive_fasting_durations_health_fasting.c.id == sa.bindparam("fast_id"))
            .values(
                actual_duration_seconds=sa.bindparam("duration"),
                version=_derive_fasting_durations_health_fasting.c.version + 1,
            ),
            stale,
        )


def downgrade_derive_fasting_durations() -> None:
    """Keep the derived durations: the values they replaced were not the sessions' real durations."""


_end_in_progress_fasts_with_an_end_time_health_fasting = sa.table(
    "health_fasting",
    sa.column("id", sa.Integer),
    sa.column("status", sa.String),
    sa.column("fast_start_time", sa.DateTime(timezone=True)),
    sa.column("fast_end_time", sa.DateTime(timezone=True)),
    sa.column("actual_duration_seconds", sa.Integer),
    sa.column("version", sa.Integer),
)


def _end_in_progress_fasts_with_an_end_time_utc(moment: datetime) -> datetime:
    """Return a stored time as UTC; a database that keeps no offset holds UTC."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def upgrade_end_in_progress_fasts_with_an_end_time() -> None:
    """Complete each in-progress session that has an end time, filling a missing duration and bumping the version."""
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            _end_in_progress_fasts_with_an_end_time_health_fasting.c.id,
            _end_in_progress_fasts_with_an_end_time_health_fasting.c.fast_start_time,
            _end_in_progress_fasts_with_an_end_time_health_fasting.c.fast_end_time,
            _end_in_progress_fasts_with_an_end_time_health_fasting.c.actual_duration_seconds,
        ).where(
            _end_in_progress_fasts_with_an_end_time_health_fasting.c.status == "in_progress",
            _end_in_progress_fasts_with_an_end_time_health_fasting.c.fast_end_time.is_not(None),
        )
    ).all()
    for fast_id, start, end, stored in rows:
        values: dict[str, object] = {
            "status": "completed",
            "version": _end_in_progress_fasts_with_an_end_time_health_fasting.c.version + 1,
        }
        if stored is None:
            duration = int(
                (
                    _end_in_progress_fasts_with_an_end_time_utc(end)
                    - _end_in_progress_fasts_with_an_end_time_utc(start)
                ).total_seconds()
            )
            if duration >= 0:
                values["actual_duration_seconds"] = duration
        connection.execute(
            sa.update(_end_in_progress_fasts_with_an_end_time_health_fasting)
            .where(_end_in_progress_fasts_with_an_end_time_health_fasting.c.id == fast_id)
            .values(**values)
        )


def downgrade_end_in_progress_fasts_with_an_end_time() -> None:
    """Keep the sessions completed: which ones were in progress is not recorded."""


def upgrade_register_strip_image_metadata() -> None:
    """Register the image-metadata strip data migration."""
    op.execute(
        """
    INSERT INTO migrations (id, name, description, executed) VALUES
    (12, 'v0.21.0', 'Strip metadata from stored images and cap profile photos at 512 px', false);
    """
    )


def downgrade_register_strip_image_metadata() -> None:
    """Remove the migration registration."""
    op.execute("DELETE FROM migrations WHERE id = 12;")


def upgrade() -> None:
    """Run every step in order."""
    upgrade_add_auth_known_devices()
    upgrade_add_audit_retention_settings()
    upgrade_clear_out_of_range_weight_bmi()
    upgrade_delete_health_records_before_1900()
    upgrade_derive_fasting_durations()
    upgrade_end_in_progress_fasts_with_an_end_time()
    upgrade_register_strip_image_metadata()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_register_strip_image_metadata()
    downgrade_end_in_progress_fasts_with_an_end_time()
    downgrade_derive_fasting_durations()
    downgrade_delete_health_records_before_1900()
    downgrade_clear_out_of_range_weight_bmi()
    downgrade_add_audit_retention_settings()
    downgrade_add_auth_known_devices()
