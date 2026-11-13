"""92: text ids that hold UUID text become native uuid

The ten text columns that hold UUID text become ``uuid``: ``users_sessions.id`` and ``token_family_id``,
``rotated_refresh_tokens.token_family_id``, ``users_api_keys.id``, ``activity_ingestion_jobs.id``,
``oauth_states.session_id``, ``idp_session_tokens.session_id``, ``password_reset_tokens.id`` and
``sign_up_tokens.id`` and ``change_id``.

The password-reset and sign-up token ids are not secrets: every release since v0.14 sets them to ``str(uuid4())``, and
the secret is ``token_hash``. The "this wasn't me" links already mailed keep working: their signature covers the
canonical UUID text, which the cast does not change. ``oauth_states.id`` is a secret (``secrets.token_urlsafe(32)``)
and stays ``varchar(64)``, and so does ``users_sessions.oauth_state_id``, which references it.
``notifications.source_event_id`` stays a string: it holds an event id of the platform.

The revision refuses to run when a converted column holds a value that is not canonical UUID text (lowercase,
hyphenated), before any change, so the upgrade transaction rolls back unchanged.

No stored payload, metadata, notification option, JSON array, tombstone, stored file key or shared-state key is
rewritten. The event payloads that carry these ids (``api_key_id``, ``session_id``, ``except_session_id``, ``job_id``)
already hold canonical UUID text, which the payload classes now parse as ``uuid.UUID``; their ``SCHEMA_VERSION`` stays.
The storage keys built from a job id keep their text. Revision 91 emptied the sessions, rotated tokens, OAuth states
and identity provider session tokens, and data migration 14 clears the shared-state namespace.

Expected cost: one table rewrite and an index rebuild per converted column. The tables are small and the session
tables are empty after revision 91. Only the foreign key from ``rotated_refresh_tokens.token_family_id`` to
``users_sessions.token_family_id`` is dropped and recreated, because its two columns change type together.

The revision runs inside the single upgrade transaction and is irreversible.

Revision ID: 1087a5442836
Revises: 353455bea2a5
Create Date: 2026-11-13 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
from migrations import uuid_conversion
from migrations.uuid_conversion import TextIdColumn

# revision identifiers, used by Alembic.
revision: str = "1087a5442836"
down_revision: str | None = "353455bea2a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The converted columns, in conversion order.
_TEXT_ID_COLUMNS = (
    TextIdColumn("users_sessions", "id", 36, False),
    TextIdColumn("users_sessions", "token_family_id", 36, False, "UUID identifying token family for reuse detection"),
    TextIdColumn("rotated_refresh_tokens", "token_family_id", 36, False, "UUID of the token family"),
    TextIdColumn("users_api_keys", "id", 36, False, "Unique key identifier (UUID4)"),
    TextIdColumn("activity_ingestion_jobs", "id", 36, False, "Ingestion job identifier (UUIDv4)"),
    TextIdColumn("oauth_states", "session_id", 36, True, "Session that started a link or step-up flow"),
    TextIdColumn(
        "idp_session_tokens",
        "session_id",
        36,
        False,
        "Endurain session the sign-in created; no foreign key, so the token outlives the session row",
    ),
    TextIdColumn("password_reset_tokens", "id", 64, False),
    TextIdColumn("sign_up_tokens", "id", 64, False),
    TextIdColumn(
        "sign_up_tokens",
        "change_id",
        64,
        True,
        "Identifier of the email change the token belongs to (email-change tokens only)",
    ),
)


def upgrade() -> None:
    uuid_conversion.refuse_text_ids_that_are_not_uuids("92", _TEXT_ID_COLUMNS)
    op.drop_constraint("rotated_refresh_tokens_token_family_id_fkey", "rotated_refresh_tokens", type_="foreignkey")
    uuid_conversion.cast_text_ids_to_uuid(_TEXT_ID_COLUMNS)
    op.create_foreign_key(
        "rotated_refresh_tokens_token_family_id_fkey",
        "rotated_refresh_tokens",
        "users_sessions",
        ["token_family_id"],
        ["token_family_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Revision 92 cannot be reversed: restore the database from the backup taken before the upgrade."
    )
