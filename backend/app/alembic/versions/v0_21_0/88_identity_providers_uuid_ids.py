"""88: identity providers get UUID ids

``identity_providers.id`` becomes a random ``uuid``, and so do the three columns that hold it:
``users_identity_providers.idp_id``, ``idp_session_tokens.idp_id`` and ``oauth_states.idp_id``. Their foreign keys,
indexes and unique constraints are recreated under the same names.

jasil does not serialise ``uuid.UUID`` payload values: it publishes ``payload.model_dump()`` in python mode, and the
JSON columns and the Redis bus use plain ``json.dumps``, which raises ``TypeError`` on a UUID. Every publisher therefore
calls ``model_dump(mode="json")`` (``VersionedPayload`` parses the string back to ``uuid.UUID``), enforced by
``tests/architecture/test_event_publishers_dump_json.py``.

The ids stored in event payloads and notification options are rewritten as UUID strings, the shape
``model_dump(mode="json")`` writes: the ``idp_id`` of ``auth.idp_linked`` and ``auth.account_security_changed``
in the event outbox, the processing jobs (every status, dead letters included) and the event log, and the ``idp_id``
of the notification options. A null or a string is kept. The ``SCHEMA_VERSION`` of the payload classes stays: this
revision is the same one-time exception as revision 85 describes for every conversion revision. An id that names no
provider (a provider deleted before) becomes a fresh random UUID: still a valid id, matching nothing.

The audit details that carry an ``idp_id`` (``AUDIT_DETAIL_ID_CHANGES``) change type without being rewritten: audit
rows are not stored in any production database yet, and the rows that are signed by a checkpoint must not change.

The revision records every provider's old and new id in ``uuid_migration_ids`` and registers data migration 13, which
renames the stored icons from the integer to the UUID and then drops the table.

The revision runs inside the single upgrade transaction and is irreversible.

Revision ID: dc5f0450aaf0
Revises: e05703e64861
Create Date: 2026-11-12 11:00:00.000000

"""

from collections.abc import Sequence

from migrations import uuid_conversion
from migrations.uuid_conversion import IdIndex, IdReference

# revision identifiers, used by Alembic.
revision: str = "dc5f0450aaf0"
down_revision: str | None = "e05703e64861"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARENT = "identity_providers"

#: (payload class, field, event types it is stored under, parent table); every entry is rewritten.
PAYLOAD_ID_REWRITES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "modules.auth.account_security.events.AccountSecurityChangedPayload",
        "idp_id",
        ("auth.account_security_changed",),
        _PARENT,
    ),
    ("modules.auth.identity_providers.events.IdpLinkedPayload", "idp_id", ("auth.idp_linked",), _PARENT),
)

#: (details class, field, audit actions it is stored under, parent table); declared, not rewritten.
AUDIT_DETAIL_ID_CHANGES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "modules.auth.account_security.audit_actions.IdentityLinkDetails",
        "idp_id",
        ("auth.identity_link.unlink",),
        _PARENT,
    ),
    (
        "modules.auth.identity_providers.audit_actions.IdentityLinkDetails",
        "idp_id",
        ("auth.identity_link.link",),
        _PARENT,
    ),
    (
        "modules.auth.identity_providers.audit_actions.BackchannelLogoutRefusalDetails",
        "idp_id",
        ("auth.backchannel_logout.refuse",),
        _PARENT,
    ),
)

_REFERENCES: tuple[IdReference, ...] = (
    IdReference(
        "users_identity_providers",
        "idp_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Identity Provider ID",
        indexes=(IdIndex("ix_users_identity_providers_idp_id", ("idp_id",)),),
        unique_constraints=(
            IdIndex("uq_identity_links_user_idp", ("user_id", "idp_id")),
            IdIndex("uq_identity_links_idp_subject", ("idp_id", "idp_subject")),
        ),
    ),
    IdReference(
        "idp_session_tokens",
        "idp_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Identity Provider ID",
        indexes=(
            IdIndex("ix_idp_session_tokens_idp_id", ("idp_id",)),
            IdIndex("ix_idp_session_tokens_idp_id_idp_sid", ("idp_id", "idp_sid")),
        ),
    ),
    IdReference(
        "oauth_states",
        "idp_id",
        nullable=True,
        ondelete="CASCADE",
        comment="Identity provider ID (may be null if mobile logic)",
        indexes=(IdIndex("ix_oauth_states_idp_id", ("idp_id",)),),
    ),
)

_PARENT_INDEXES = (IdIndex("ix_identity_providers_id", ("id",)),)


def upgrade() -> None:
    """Map every reference, rewrite the stored ids, record the old ids and swap the columns for UUIDs."""
    uuid_conversion.add_uuid_ids_with_references(_PARENT, _REFERENCES)
    for _payload_class, field, event_types, parent in PAYLOAD_ID_REWRITES:
        uuid_conversion.rewrite_payload_ids(event_types, field, parent)
    uuid_conversion.rewrite_notification_option_ids("idp_id", _PARENT)
    uuid_conversion.record_old_ids(_PARENT)
    uuid_conversion.schedule_stored_key_renames()
    uuid_conversion.swap_in_uuid_ids(_PARENT, _PARENT_INDEXES, _REFERENCES)


def downgrade() -> None:
    """Refuse: the integer ids are gone.

    Raises:
        NotImplementedError: Always.
    """
    raise NotImplementedError(
        "Revision 88 cannot be reversed: restore the database from the backup taken before the upgrade."
    )
