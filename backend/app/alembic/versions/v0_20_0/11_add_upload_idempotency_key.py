"""11: add upload idempotency key

Revision ID: 8c3d9f21e64b
Revises: 5b21c7d84a9e
Create Date: 2026-07-28 00:00:00.000000

Adds the ``Idempotency-Key`` an upload may carry, so a client that retries a
request it never saw the response to (a dropped connection, a proxy timeout)
gets the original job back rather than starting a second import of the same
file. That matters more now the route answers ``202``: without the response the
client has no job id to poll, so replaying the upload is its only recovery.

The uniqueness is scoped to the user *and* the job kind: a key is only
meaningful within the client that generated it, and scoping it prevents one
user's key from colliding with — or probing for — another's, or a future
refresh's key from colliding with an upload's. Postgres treats NULLs as
distinct, so the uploads that carry no key are unaffected by the constraint.

``request_fingerprint`` is what makes this idempotency rather than a lookup.
Without it, a client that reused a key for a *different* file would be handed
the first job and told it succeeded, and the second file would never be
imported — silent data loss. Storing the hash of the bytes the key was first
used with lets a mismatch be rejected instead.

This is a different layer from the ``activities.dedup_key`` idempotency already
in place. That one is content-derived and makes a *re-import* a no-op at the
activity level, but only after the file has been stored and parsed; this one is
request-derived and short-circuits before either, and gives the caller the same
job id back to poll.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c3d9f21e64b"
down_revision: str | None = "5b21c7d84a9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=True,
            comment="Client-supplied Idempotency-Key for an upload; unique per user and kind",
        ),
    )
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "request_fingerprint",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 of the bytes the idempotency key was first used with",
        ),
    )
    op.create_unique_constraint(
        "uq_activity_ingestion_jobs_user_kind_idempotency",
        "activity_ingestion_jobs",
        ["user_id", "kind", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_activity_ingestion_jobs_user_kind_idempotency",
        "activity_ingestion_jobs",
        type_="unique",
    )
    op.drop_column("activity_ingestion_jobs", "request_fingerprint")
    op.drop_column("activity_ingestion_jobs", "idempotency_key")
