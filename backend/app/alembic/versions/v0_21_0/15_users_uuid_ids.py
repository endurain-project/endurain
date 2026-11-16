"""91: users get UUID ids

``users.id`` and the 38 columns that reference it become random ``uuid`` values: the ``user_id`` columns of the
activity, gear, health, authentication, integration and notification tables, the two columns of ``followers``,
``follower_blocks`` and ``follow_request_declines``, and the ``user_id`` primary keys of ``users_local_credentials``
and ``account_security_generations``. Their foreign keys (``ON DELETE CASCADE``) are recreated under the PostgreSQL
default names the models produce, ``{table}_{column}_fkey``, which renames ``followers_following_id_fkey`` to
``followers_followee_id_fkey`` and matches a fresh install. Their indexes, unique constraints, partial unique indexes,
check constraints and comments keep their names.

The ids stored in event payloads and metadata and in notification options are rewritten as UUID strings, the shape
``model_dump(mode="json")`` writes: every user id field of the payload classes in ``PAYLOAD_ID_REWRITES`` in the
event outbox, the processing jobs (every status, dead letters included) and the event log; the ``user_id`` of the
event metadata; and the ``user_id`` of the notification options. A null or a string is kept. The ``SCHEMA_VERSION`` of
the payload classes stays: this revision is the same one-time exception as revisions 85 and 88 describe for every
conversion revision. An id that names no user becomes a fresh random UUID: still a valid id, matching nothing.

Decision C: the sessions, the rotated refresh tokens, the OAuth states and the identity provider session tokens are
deleted, so everyone signs in again. API keys keep working. The identity provider tokens are not revoked at the
provider.

The password-reset and sign-up tokens are kept, pending email changes included: their links carry no user id, so they
still resolve to the same user. The tombstone tables (``activity_deletions``, ``gear_deletions``,
``gear_component_deletions`` and ``health_record_deletions``) keep their rows with the mapped ``user_id``. The audit
rows are not rewritten.

``users.photo_path`` keeps the integer layout: the stored photos are named by the integer ids, and data migration 13,
which this revision registers as not executed again, renames the files and rewrites the column. Every user's old and
new id is recorded in ``uuid_migration_ids`` for it, and migration 13 drops the table afterwards. The ``created_at`` of
``followers``, ``follower_blocks`` and ``users_goals`` is untouched: revision 87 already keeps their order.

Data migration 14, which this revision registers, clears the ``endurain:`` state namespace once (its keys embed
integer user ids; every account lockout is lifted). It is a migration of its own so that a retry of migration 13 never
clears the state written after the upgrade.

Expected cost, on a large install: ``users`` is rewritten once (the ``new_id`` fill) and indexed. Each of the 38
referencing tables is rewritten once by the ``new_<column>`` fill (``activities`` and the health tables are the big
ones), then scanned for ``NOT NULL``, indexed, and its foreign key is validated against ``users_pkey``. The four
emptied tables cost nothing. Every stored id (event payloads and metadata, notification options) is looked up through
``users_pkey``, one index probe per rewritten row, so that part costs O(rewritten rows x log users). Each of the 33
payload field rewrites is its own ``UPDATE`` of an event table, and ``jasil_processing_jobs`` and
``jasil_event_outbox`` have no ``event_type`` index, so every one of them scans both tables in full: about 33 full
scans of each, and a row with two user fields is written twice. Dropped columns
are metadata-only. The dead tuples of the rewrites roughly double the heap until ``VACUUM``: run ``VACUUM (ANALYZE)``
afterwards.

The revision runs inside the single upgrade transaction and is irreversible.

Revision ID: 353455bea2a5
Revises: 3ab6649cdd08
Create Date: 2026-11-12 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from migrations import uuid_conversion
from migrations.uuid_conversion import IdIndex, IdReference

# revision identifiers, used by Alembic.
revision: str = "353455bea2a5"
down_revision: str | None = "3ab6649cdd08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARENT = "users"

#: (payload class, field, event types it is stored under, parent table); every entry is rewritten.
PAYLOAD_ID_REWRITES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "modules.activities.activity.events.ActivityCreatedPayload",
        "user_id",
        ("activity.created",),
        _PARENT,
    ),
    (
        "modules.activities.activity.events.ActivityUpdatedPayload",
        "user_id",
        ("activity.updated",),
        _PARENT,
    ),
    (
        "modules.activities.activity.events.VisibilityEditRequestedPayload",
        "user_id",
        ("activities.visibility_edit_requested",),
        _PARENT,
    ),
    (
        "modules.auth.account_security.events.AccountSecurityChangedPayload",
        "user_id",
        ("auth.account_security_changed",),
        _PARENT,
    ),
    (
        "modules.auth.account_security.events.StepUpSessionEndedPayload",
        "user_id",
        ("auth.step_up_session_ended",),
        _PARENT,
    ),
    (
        "modules.auth.account_security.events.StepUpLockedPayload",
        "user_id",
        ("auth.step_up_locked",),
        _PARENT,
    ),
    ("modules.auth.authentication.events.AccountLockedPayload", "user_id", ("auth.account_locked",), _PARENT),
    ("modules.auth.authentication.events.MfaLockedPayload", "user_id", ("auth.mfa_locked",), _PARENT),
    (
        "modules.auth.authentication.events.RefreshReuseDetectedPayload",
        "user_id",
        ("auth.refresh_reuse_detected",),
        _PARENT,
    ),
    ("modules.auth.identity_providers.events.IdpLinkedPayload", "user_id", ("auth.idp_linked",), _PARENT),
    (
        "modules.auth.identity_providers.events.IdpTokenRefreshPayload",
        "user_id",
        ("auth.idp_token_refresh_requested",),
        _PARENT,
    ),
    ("modules.auth.known_devices.events.NewDeviceSignInPayload", "user_id", ("auth.new_device_sign_in",), _PARENT),
    ("modules.auth.mfa_backup_codes.events.BackupCodeUsedPayload", "user_id", ("auth.backup_code_used",), _PARENT),
    (
        "modules.auth.password_reset_tokens.events.PasswordResetRequestedPayload",
        "user_id",
        ("auth.password_reset_requested",),
        _PARENT,
    ),
    (
        "modules.auth.password_reset_tokens.events.PasswordResetCompletedPayload",
        "user_id",
        ("auth.password_reset_completed",),
        _PARENT,
    ),
    ("modules.auth.sessions.events.SessionsRevokedPayload", "user_id", ("auth.sessions_revoked",), _PARENT),
    (
        "modules.auth.sign_up_tokens.events.SignUpUserPayload",
        "user_id",
        (
            "auth.sign_up_verification_requested",
            "auth.admin_invitation_requested",
            "auth.email_change_verification_requested",
            "auth.sign_up_approved",
            "auth.sign_up_existing_account",
            "auth.email_change_requested",
            "auth.email_change_address_taken",
        ),
        _PARENT,
    ),
    ("modules.auth.sign_up_tokens.events.EmailChangedPayload", "user_id", ("auth.email_changed",), _PARENT),
    (
        "modules.auth.sign_up_tokens.events.SignUpApprovalRequestedPayload",
        "user_id",
        ("auth.sign_up_approval_requested",),
        _PARENT,
    ),
    (
        "modules.auth.sign_up_tokens.events.SignUpApprovalRequestedPayload",
        "admin_user_id",
        ("auth.sign_up_approval_requested",),
        _PARENT,
    ),
    ("modules.followers.events.FollowerRequestedPayload", "requester_user_id", ("follower.requested",), _PARENT),
    ("modules.followers.events.FollowerRequestedPayload", "target_user_id", ("follower.requested",), _PARENT),
    ("modules.followers.events.FollowerAcceptedPayload", "accepter_user_id", ("follower.accepted",), _PARENT),
    ("modules.followers.events.FollowerAcceptedPayload", "requester_user_id", ("follower.accepted",), _PARENT),
    (
        "modules.followers.events.FollowerRequestRemovedPayload",
        "requester_user_id",
        ("follower.request_removed",),
        _PARENT,
    ),
    (
        "modules.followers.events.FollowerRequestRemovedPayload",
        "target_user_id",
        ("follower.request_removed",),
        _PARENT,
    ),
    ("modules.garmin.events.SyncRequestedPayload", "user_id", ("garmin.sync_requested",), _PARENT),
    ("modules.strava.events.SyncRequestedPayload", "user_id", ("strava.sync_requested",), _PARENT),
    ("modules.users.users.events.DeletionRequestedPayload", "user_id", ("users.deletion_requested",), _PARENT),
    ("modules.users.users.events.AdminPromotedPayload", "user_id", ("users.admin_promoted",), _PARENT),
    ("modules.users.users.events.AdminPromotedPayload", "admin_user_id", ("users.admin_promoted",), _PARENT),
    (
        "modules.users.users_profile.events.ProfileImportRequestedPayload",
        "user_id",
        ("users.profile_import_requested",),
        _PARENT,
    ),
    (
        "modules.users.users_profile.events.ProfileExportRequestedPayload",
        "user_id",
        ("users.profile_export_requested",),
        _PARENT,
    ),
)

#: The tables decision C empties, in foreign-key-safe order: each is emptied before the table it references, and
#: nothing outside the four references them.
_EMPTIED_TABLES = ("rotated_refresh_tokens", "idp_session_tokens", "users_sessions", "oauth_states")

_REFERENCES: tuple[IdReference, ...] = (
    IdReference(
        "account_security_generations",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User the generation belongs to",
    ),
    IdReference(
        "activities",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the activity belongs",
        indexes=(
            IdIndex("ix_activities_user_id", ("user_id",)),
            IdIndex("ix_activities_user_id_updated_at_id", ("user_id", "updated_at", "id")),
        ),
    ),
    IdReference(
        "activity_deletions",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Owner of the deleted record",
        indexes=(IdIndex("ix_activity_deletions_user_id_deleted_at_id", ("user_id", "deleted_at", "id")),),
    ),
    IdReference(
        "activity_ingestion_jobs",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User that owns the ingestion request",
        indexes=(
            IdIndex("idx_activity_ingestion_jobs_user_created", ("user_id", "created_at")),
            IdIndex("ix_activity_ingestion_jobs_user_id", ("user_id",)),
        ),
        unique_constraints=(
            IdIndex("uq_activity_ingestion_jobs_user_kind_idempotency", ("user_id", "kind", "idempotency_key")),
        ),
    ),
    IdReference(
        "auth_known_devices",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User who signed in from the device",
        unique_constraints=(IdIndex("uq_auth_known_devices_user_id_device_hash", ("user_id", "device_hash")),),
    ),
    IdReference(
        "follow_request_declines",
        "follower_id",
        nullable=False,
        ondelete="CASCADE",
        comment="ID of the requester whose request was declined",
        indexes=(IdIndex("ix_follow_request_declines_follower_id", ("follower_id",)),),
    ),
    IdReference(
        "follow_request_declines",
        "followee_id",
        nullable=False,
        ondelete="CASCADE",
        comment="ID of the user who declined the request",
        indexes=(IdIndex("ix_follow_request_declines_followee_id", ("followee_id",)),),
        unique_constraints=(IdIndex("uq_follow_request_declines_follower_followee", ("follower_id", "followee_id")),),
    ),
    IdReference(
        "follower_blocks",
        "blocker_id",
        nullable=False,
        ondelete="CASCADE",
        comment="ID of the user who blocked",
        indexes=(IdIndex("ix_follower_blocks_blocker_id", ("blocker_id",)),),
    ),
    IdReference(
        "follower_blocks",
        "blocked_id",
        nullable=False,
        ondelete="CASCADE",
        comment="ID of the user who is blocked",
        indexes=(IdIndex("ix_follower_blocks_blocked_id", ("blocked_id",)),),
        unique_constraints=(IdIndex("uq_follower_blocks_blocker_blocked", ("blocker_id", "blocked_id")),),
    ),
    IdReference(
        "followers",
        "follower_id",
        nullable=False,
        ondelete="CASCADE",
        comment="ID of the follower user (the requester)",
        indexes=(IdIndex("ix_followers_follower_id", ("follower_id",)),),
    ),
    IdReference(
        "followers",
        "followee_id",
        nullable=False,
        ondelete="CASCADE",
        comment="ID of the followee user (the target being followed)",
        indexes=(IdIndex("ix_followers_followee_id", ("followee_id",)),),
        unique_constraints=(IdIndex("uq_followers_follower_followee", ("follower_id", "followee_id")),),
    ),
    IdReference(
        "gear",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the gear belongs to",
        indexes=(IdIndex("ix_gear_user_id_updated_at_id", ("user_id", "updated_at", "id")),),
        unique_constraints=(
            IdIndex("uq_gear_user_strava_gear_id", ("user_id", "strava_gear_id")),
            IdIndex("uq_gear_user_garminconnect_gear_id", ("user_id", "garminconnect_gear_id")),
        ),
    ),
    IdReference(
        "gear_component_deletions",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Owner of the deleted record",
        indexes=(IdIndex("ix_gear_component_deletions_user_id_deleted_at_id", ("user_id", "deleted_at", "id")),),
    ),
    IdReference(
        "gear_components",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the gear component belongs to",
        indexes=(IdIndex("ix_gear_components_user_id_updated_at_id", ("user_id", "updated_at", "id")),),
    ),
    IdReference(
        "gear_deletions",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Owner of the deleted record",
        indexes=(IdIndex("ix_gear_deletions_user_id_deleted_at_id", ("user_id", "deleted_at", "id")),),
    ),
    IdReference(
        "health_fasting",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the health_fasting belongs",
        indexes=(
            IdIndex("ix_health_fasting_user_updated_at_id", ("user_id", "updated_at", "id")),
            IdIndex("ix_health_fasting_user_id", ("user_id",)),
        ),
    ),
    IdReference(
        "health_poop",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the health_poop belongs",
        indexes=(
            IdIndex("ix_health_poop_user_updated_at_id", ("user_id", "updated_at", "id")),
            IdIndex("ix_health_poop_user_id", ("user_id",)),
        ),
    ),
    IdReference(
        "health_record_deletions",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Owner of the deleted record",
        indexes=(IdIndex("ix_health_record_deletions_user_deleted_at_id", ("user_id", "deleted_at", "id")),),
    ),
    IdReference(
        "health_sleep",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the health_sleep belongs",
        indexes=(
            IdIndex("ix_health_sleep_user_id", ("user_id",)),
            IdIndex("ix_health_sleep_user_updated_at_id", ("user_id", "updated_at", "id")),
        ),
        unique_constraints=(IdIndex("uq_health_sleep_user_date", ("user_id", "date")),),
    ),
    IdReference(
        "health_steps",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the health_steps belongs",
        indexes=(
            IdIndex("ix_health_steps_user_updated_at_id", ("user_id", "updated_at", "id")),
            IdIndex("ix_health_steps_user_id", ("user_id",)),
        ),
        unique_constraints=(IdIndex("uq_health_steps_user_date", ("user_id", "date")),),
    ),
    IdReference(
        "health_targets",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the health_target belongs",
        indexes=(IdIndex("ix_health_targets_user_updated_at_id", ("user_id", "updated_at", "id")),),
    ),
    IdReference(
        "health_water",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the health_water belongs",
        indexes=(
            IdIndex("ix_health_water_user_updated_at_id", ("user_id", "updated_at", "id")),
            IdIndex("ix_health_water_user_id", ("user_id",)),
        ),
        unique_constraints=(IdIndex("uq_health_water_user_date", ("user_id", "date")),),
    ),
    IdReference(
        "health_weight",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the health_weight belongs",
        indexes=(
            IdIndex("ix_health_weight_user_updated_at_id", ("user_id", "updated_at", "id")),
            IdIndex("ix_health_weight_user_id", ("user_id",)),
        ),
        unique_constraints=(IdIndex("uq_health_weight_user_date", ("user_id", "date")),),
    ),
    IdReference(
        "idp_session_tokens",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID",
        indexes=(IdIndex("ix_idp_session_tokens_user_id", ("user_id",)),),
    ),
    IdReference(
        "mfa_backup_codes",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User who owns this backup code",
        indexes=(
            IdIndex("idx_user_unused_codes", ("user_id", "used")),
            IdIndex("ix_mfa_backup_codes_user_id", ("user_id",)),
        ),
    ),
    IdReference(
        "mfa_factors",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="FK to users",
        indexes=(IdIndex("ix_mfa_factors_user_id", ("user_id",)),),
    ),
    IdReference(
        "notifications",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the notification belongs to",
        indexes=(IdIndex("ix_notifications_user_id_created_at", ("user_id", "created_at")),),
        unique_constraints=(
            IdIndex("uq_notifications_source_event_user_type", ("source_event_id", "user_id", "type")),
        ),
    ),
    IdReference(
        "oauth_states",
        "user_id",
        nullable=True,
        ondelete="CASCADE",
        comment="User ID (for link mode)",
        indexes=(IdIndex("ix_oauth_states_user_id", ("user_id",)),),
    ),
    IdReference(
        "password_reset_tokens",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the password reset token belongs to",
        indexes=(IdIndex("ix_password_reset_tokens_user_id", ("user_id",)),),
    ),
    IdReference(
        "sign_up_tokens",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the sign up token belongs to",
        indexes=(IdIndex("ix_sign_up_tokens_user_id", ("user_id",)),),
    ),
    IdReference(
        "users_api_keys",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the API key belongs to",
        indexes=(IdIndex("ix_users_api_keys_user_id", ("user_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the default gear belongs",
        indexes=(IdIndex("ix_users_default_gear_user_id", ("user_id",)),),
        unique_constraints=(IdIndex("uq_users_default_gear_user_id", ("user_id",)),),
    ),
    IdReference(
        "users_goals",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the goals belongs",
        indexes=(IdIndex("ix_users_goals_user_id", ("user_id",)),),
        unique_constraints=(
            IdIndex("uq_users_goals_user_scope", ("user_id", "interval", "activity_type", "goal_type")),
        ),
    ),
    IdReference(
        "users_identity_providers",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID",
        indexes=(IdIndex("ix_users_identity_providers_user_id", ("user_id",)),),
        unique_constraints=(IdIndex("uq_identity_links_user_idp", ("user_id", "idp_id")),),
    ),
    IdReference(
        "users_integrations",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the integration belongs",
    ),
    IdReference(
        "users_local_credentials",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User the credentials belong to",
    ),
    IdReference(
        "users_privacy_settings",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the privacy settings belongs",
    ),
    IdReference(
        "users_sessions",
        "user_id",
        nullable=False,
        ondelete="CASCADE",
        comment="User ID that the session belongs",
        indexes=(IdIndex("ix_users_sessions_user_id", ("user_id",)),),
    ),
)

_ACTIVE_BULK_IMPORT = "kind = 'bulk_import' AND completed_at IS NULL"
_FASTING_IN_PROGRESS = "status = 'in_progress'"
_TOTP_ONLY = "type = 'totp'"


def upgrade() -> None:
    """Empty the session tables, rewrite the stored ids and swap the user ids for UUIDs."""
    for table in _EMPTIED_TABLES:
        op.execute(sa.delete(sa.table(table)))
    uuid_conversion.add_uuid_ids_with_references(_PARENT, _REFERENCES)
    for _payload_class, field, event_types, parent in PAYLOAD_ID_REWRITES:
        uuid_conversion.rewrite_payload_ids(event_types, field, parent, by_primary_key=True)
    uuid_conversion.rewrite_metadata_ids("user_id", _PARENT, by_primary_key=True)
    uuid_conversion.rewrite_notification_option_ids("user_id", _PARENT, by_primary_key=True)
    uuid_conversion.record_old_ids(_PARENT)
    uuid_conversion.schedule_stored_key_renames()
    _schedule_state_clear()
    uuid_conversion.swap_in_uuid_ids(_PARENT, (), _REFERENCES)
    _recreate_what_the_swap_does_not()


def _schedule_state_clear() -> None:
    """Register data migration 14, which clears the ``endurain:`` state namespace once, as not executed."""
    op.execute(
        sa.text(
            "INSERT INTO migrations (id, name, description, executed) VALUES "
            "(14, 'v0.21.0', 'Clear the shared state keyed by integer user ids', false) "
            "ON CONFLICT (id) DO UPDATE SET executed = false"
        )
    )


def _recreate_what_the_swap_does_not() -> None:
    """Recreate the primary keys, unique and partial indexes and check constraints that contained a dropped column."""
    op.create_primary_key("users_local_credentials_pkey", "users_local_credentials", ["user_id"])
    op.create_primary_key("account_security_generations_pkey", "account_security_generations", ["user_id"])
    for name, table in (
        ("ix_health_targets_user_id", "health_targets"),
        ("ix_users_integrations_user_id", "users_integrations"),
        ("ix_users_privacy_settings_user_id", "users_privacy_settings"),
    ):
        op.create_index(name, table, ["user_id"], unique=True)
    op.execute("CREATE UNIQUE INDEX uq_gear_user_nickname ON gear (user_id, lower(nickname))")
    op.create_index("uq_activities_user_dedup_key", "activities", ["user_id", "dedup_key"], unique=True)
    for name, table, predicate in (
        ("uq_activity_ingestion_jobs_user_active_bulk_import", "activity_ingestion_jobs", _ACTIVE_BULK_IMPORT),
        ("uq_health_fasting_one_in_progress_per_user", "health_fasting", _FASTING_IN_PROGRESS),
        ("uq_mfa_factors_user_totp", "mfa_factors", _TOTP_ONLY),
    ):
        op.create_index(name, table, ["user_id"], unique=True, postgresql_where=sa.text(predicate))
    op.create_check_constraint("ck_followers_not_self", "followers", "follower_id <> followee_id")
    op.create_check_constraint("ck_follower_blocks_not_self", "follower_blocks", "blocker_id <> blocked_id")


def downgrade() -> None:
    """Refuse: the integer ids are gone.

    Raises:
        NotImplementedError: Always.
    """
    raise NotImplementedError(
        "Revision 91 cannot be reversed: restore the database from the backup taken before the upgrade."
    )
