"""Credentials, identity provider and session schema, and running cadence

The steps run in this order.

Mark a password an administrator wrote as one its owner must replace
--------------------------------------------------------------------

``password_change_required`` belongs to the local credential. An administrator knows the password they set or
created an account with, so the owner is asked to choose a new one at the next sign-in. Existing rows start false:
no password already stored is known to have been written by an administrator.

Keep the ID token each identity-provider sign-in was issued
-----------------------------------------------------------

RP-initiated logout (OpenID Connect RP-Initiated Logout 1.0) names the session to end with the ID token the
provider issued at sign-in, so the sign-in keeps it, encrypted like the refresh token. Existing sign-ins hold none:
signing out of such a session ends only the Endurain session.

Settle the identity-provider type and add the link-by-email and email-sync switches
-----------------------------------------------------------------------------------

``provider_type`` is ``oidc`` or ``oauth2``. There is no SAML code, so a ``saml`` row has always behaved exactly
like an ``oauth2`` one; it becomes ``oauth2``, which changes nothing at runtime.

``link_by_email`` says whether a sign-in with no link joins the local account with the same verified email, and
``sync_email`` whether the verified email is copied onto the account at sign-in. New providers start with both
off. Existing providers keep what they did before: they all linked by email, and they synced the email exactly
when they synced the other fields (``sync_user_info``).

Record the client type of each session and end the sessions open before it
--------------------------------------------------------------------------

A session now records the kind of client it was created for (``web`` or ``mobile``); its tokens name it in the
``client_id`` claim and a refresh must declare it. Refresh tokens are now signed with a key of their own and carry
the refresh endpoint as their audience, so no refresh token issued before this revision verifies any more. The open
sessions are deleted instead of being given a guessed client type: every user signs in once more. Deleting a session
deletes its rotated refresh tokens (foreign key with ``ON DELETE CASCADE``); the identity-provider tokens of those
sessions, which have no foreign key, are revoked at the provider by the scheduled sweep of ended sessions.

The downgrade drops the column; the sessions ended by the upgrade do not come back.

Date a user account
-------------------

``users.created_at`` lets a job tell how long an account has existed, which the verification link's lifetime
alone cannot: the sign-up tokens are purged once they expire. Accounts that exist already take the migration time,
so none is mistaken for an old unverified sign-up the moment the column appears.

Keep the provider session id of each identity-provider sign-in
--------------------------------------------------------------

OpenID Connect Back-Channel Logout 1.0 names the provider session to end with the ``sid`` the provider put in the
ID token at sign-in, so the sign-in keeps it, indexed for the lookup by provider and ``sid``. Existing sign-ins hold
none: a logout token that names only their ``sid`` matches nothing, and one that names the user's ``sub`` still
ends them.

Let only one identity provider use an issuer
--------------------------------------------

A user's link to an identity provider is only as trustworthy as the issuer that names the provider, so two providers
must not share one. The check in the service can race, so a unique index on the issuer without its trailing slashes
decides. Providers with no issuer URL are not compared. An install that already has two providers with the same issuer
cannot pick one silently: the upgrade stops and names them, and the administrator changes or deletes all but one
before upgrading again.

Bind each rotated refresh token to the client that rotated it
-------------------------------------------------------------

A rotated refresh token presented again inside the grace window used to be answered with the live replacement
refresh token whoever presented it. The rotated record now stores a fingerprint of the rotating client, its network
and its ``User-Agent``, and only a retry from the same client is answered. The existing records carry no fingerprint
and are deleted: the sessions they belong to were ended by the session client type step, so no rotated token of
them can be presented again.

The downgrade drops the column.

Store the OAuth state's nonce and PKCE verifier encrypted
---------------------------------------------------------

The OIDC nonce and the PKCE verifier of an identity-provider sign-in sat in ``oauth_states`` in plain text, so a copy of
the table was enough to forge the ID token or the code exchange of a sign-in in flight. Both are now stored Fernet
encrypted, which no longer fits their column lengths, so the columns become ``Text``. The existing rows hold plain text
and are deleted: a state lives ten minutes at most, so the sign-ins in flight are started again, a session waiting for
its mobile token exchange loses its state (the foreign key sets the reference to null) and answers not found, and the
user signs in again.

The downgrade deletes the rows, which hold ciphertext the old code cannot use, and narrows the columns.

Opt-in breached-password check
------------------------------

Adds ``server_settings.password_breach_check_enabled``. It is off, so no install starts sending password hash
prefixes to a third party without an administrator turning the check on.

Session idle timeout on (72 hours) for new installs
---------------------------------------------------

The idle timeout shipped off at 1 hour. This sets it to on at 72 hours on the single ``server_settings`` row, but
only when the ``users`` table is empty and both idle columns still hold the shipped values (false and 1). A fresh
install runs its migrations before its first account exists, so only new installs change; an existing install has
accounts and keeps its setting. The one harmless edge: an install upgraded before any account was ever created is
treated as new. Column server defaults and model defaults stay false and 1, because the row already exists and the
defaults only apply to rows inserted later. The deprecated ``SESSION_IDLE_TIMEOUT_*`` environment variables are
imported at startup, after migrations, and still win when set.

Normalize stored running cadence to steps per minute (spm)
----------------------------------------------------------

Running cadence was stored as the source reported it: FIT, Strava, TCX and GPX
running cadence is a single-leg rate (rpm, around 85) while some treadmill and
footpod sources store full spm (around 160). The importers store spm for running
activities, so existing rows are brought to the same unit.

Only the stored numbers are available here, so the per-activity decision is a
best-effort heuristic, not an exact split: a running activity whose
representative cadence is below 100 is taken as rpm and doubled, one at or above
100 is taken as spm and left untouched. Per-leg running cadence is about 70 to
110 and real spm is almost never below 120, so a slow run above 100 rpm stays in
rpm and a walk logged as a run below 100 spm is doubled.

The representative cadence is a non-zero ``activities.average_cad``, else the
mean of the non-zero cadence stream samples (``stream_type = 3``), else the mean
of the non-zero per-lap cadence with its fraction, else a non-zero ``max_cad``
(a maximum below 100 implies an average below 100); a zero cadence counts as
missing. The decision is taken once per activity, recorded in
``cadence_spm_migration_rows`` together with the original scalars, and applied
to the stream, the laps and the scalars alike. A missing ``average_cad`` takes
the mean it was decided from, if any; a missing ``max_cad`` comes from the
stream, else the laps.

Only plausible activities are touched: cadence is a uint8 in FIT, so an activity
with ``max_cad``, a lap value (with its fraction) or a numeric stream sample
above 255 is left entirely as stored rather than overflowing ``int4``. A
recorded activity has every lap value and numeric stream sample doubled;
non-numeric stream samples are kept as they are. A lap whose fraction is folded
into ``avg_cadence``/``max_cadence`` has its ``*_fractional_cadence`` cleared.

``downgrade()`` restores the recorded activities' original scalars and halves
their lap values and numeric stream samples with integer division: a folded
fraction of 0.75 or more comes back one higher, cleared fractions stay empty,
and a fractional stream sample comes back as an integer.

Revision ID: c91ac2dad0f0
Revises: f1b6d3a8c254
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from collections import defaultdict

# revision identifiers, used by Alembic.
revision: str = "c91ac2dad0f0"
down_revision: str | None = "f1b6d3a8c254"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade_credentials_password_change_required() -> None:
    """Add the flag, false for every existing credential."""
    op.add_column(
        "users_local_credentials",
        sa.Column(
            "password_change_required",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Whether the owner must choose a new password at the next sign-in (an administrator wrote it)",
        ),
    )


def downgrade_credentials_password_change_required() -> None:
    """Drop the flag."""
    op.drop_column("users_local_credentials", "password_change_required")


def upgrade_idp_session_token_id_token() -> None:
    """Add the column, empty for every existing sign-in."""
    op.add_column(
        "idp_session_tokens",
        sa.Column("id_token", sa.Text(), nullable=True, comment="Encrypted ID token the provider issued at sign-in"),
    )


def downgrade_idp_session_token_id_token() -> None:
    """Drop the column."""
    op.drop_column("idp_session_tokens", "id_token")


def upgrade_idp_provider_type_link_and_sync_flags() -> None:
    """Turn ``saml`` rows into ``oauth2`` and add the two switches, keeping what existing providers did."""
    op.alter_column(
        "identity_providers",
        "provider_type",
        existing_type=sa.String(length=50),
        existing_nullable=False,
        comment="Type: oidc, oauth2",
        existing_comment="Type: oidc, oauth2, saml",
    )
    op.alter_column(
        "identity_providers",
        "sync_user_info",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        comment="Sync the mapped profile fields, except the email, on each login",
        existing_comment="Sync user info on each login",
    )
    op.add_column(
        "identity_providers",
        sa.Column(
            "link_by_email",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Link a sign-in with no link to the local account that has the same verified email",
        ),
    )
    op.add_column(
        "identity_providers",
        sa.Column(
            "sync_email",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Sync the verified email on each login",
        ),
    )
    op.execute("UPDATE identity_providers SET provider_type = 'oauth2' WHERE provider_type = 'saml'")
    op.execute("UPDATE identity_providers SET link_by_email = true, sync_email = sync_user_info")


def downgrade_idp_provider_type_link_and_sync_flags() -> None:
    """Drop the two switches. A ``saml`` row that became ``oauth2`` stays ``oauth2``: the two behave alike."""
    op.drop_column("identity_providers", "sync_email")
    op.drop_column("identity_providers", "link_by_email")
    op.alter_column(
        "identity_providers",
        "sync_user_info",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        comment="Sync user info on each login",
        existing_comment="Sync the mapped profile fields, except the email, on each login",
    )
    op.alter_column(
        "identity_providers",
        "provider_type",
        existing_type=sa.String(length=50),
        existing_nullable=False,
        comment="Type: oidc, oauth2, saml",
        existing_comment="Type: oidc, oauth2",
    )


_SESSION_CLIENT_TYPE_TABLE = "users_sessions"

_CHECK = "ck_users_sessions_client_type"


def upgrade_session_client_type() -> None:
    """End every session, then add the non-null client type limited to ``web`` and ``mobile``."""
    op.execute("DELETE FROM users_sessions")
    op.add_column(
        _SESSION_CLIENT_TYPE_TABLE,
        sa.Column(
            "client_type",
            sa.String(length=10),
            nullable=False,
            comment="Client type the session was created for: web or mobile",
        ),
    )
    op.create_check_constraint(_CHECK, _SESSION_CLIENT_TYPE_TABLE, "client_type IN ('web', 'mobile')")


def downgrade_session_client_type() -> None:
    """Drop the client type; the sessions the upgrade ended stay ended."""
    op.drop_constraint(_CHECK, _SESSION_CLIENT_TYPE_TABLE, type_="check")
    op.drop_column(_SESSION_CLIENT_TYPE_TABLE, "client_type")


def upgrade_users_created_at() -> None:
    """Add the creation time, now for every existing account."""
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the account was created; accounts that predate the column carry the migration time",
        ),
    )


def downgrade_users_created_at() -> None:
    """Drop the creation time."""
    op.drop_column("users", "created_at")


_SID_TABLE = "idp_session_tokens"

_SID_INDEX = "ix_idp_session_tokens_idp_id_idp_sid"


def upgrade_idp_session_token_sid() -> None:
    """Add the column, empty for every existing sign-in, and its index."""
    op.add_column(
        _SID_TABLE,
        sa.Column(
            "idp_sid",
            sa.String(length=255),
            nullable=True,
            comment="Provider session id (sid) of the verified ID token, named by back-channel logout",
        ),
    )
    op.create_index(_SID_INDEX, _SID_TABLE, ["idp_id", "idp_sid"], unique=False)


def downgrade_idp_session_token_sid() -> None:
    """Drop the index and the column."""
    op.drop_index(_SID_INDEX, table_name=_SID_TABLE)
    op.drop_column(_SID_TABLE, "idp_sid")


_IDENTITY_PROVIDER_ISSUER_UNIQUE_TABLE = "identity_providers"

_ISSUER_INDEX = "uq_identity_providers_issuer_url_normalized"


def upgrade_identity_provider_issuer_unique() -> None:
    """Refuse to continue while two providers share an issuer, then create the unique index.

    Raises:
        RuntimeError: When two or more providers have the same issuer once trailing slashes are ignored.
    """
    rows = op.get_bind().execute(
        sa.text(
            "SELECT rtrim(issuer_url, '/') AS issuer, slug FROM identity_providers "
            "WHERE issuer_url IS NOT NULL ORDER BY slug"
        )
    )
    slugs_by_issuer: dict[str, list[str]] = defaultdict(list)
    for issuer, slug in rows:
        slugs_by_issuer[issuer].append(slug)
    shared = {issuer: slugs for issuer, slugs in slugs_by_issuer.items() if len(slugs) > 1}
    if shared:
        lines = "; ".join(f"{issuer} is used by {', '.join(slugs)}" for issuer, slugs in sorted(shared.items()))
        raise RuntimeError(
            "Cannot upgrade: identity providers must have different issuer URLs (a trailing slash is ignored). "
            f"{lines}. Change the issuer URL of, or delete, all but one of the providers that share an issuer, "
            "then upgrade again."
        )
    op.create_index(
        _ISSUER_INDEX, _IDENTITY_PROVIDER_ISSUER_UNIQUE_TABLE, [sa.text("rtrim(issuer_url, '/')")], unique=True
    )


def downgrade_identity_provider_issuer_unique() -> None:
    """Drop the unique index."""
    op.drop_index(_ISSUER_INDEX, table_name=_IDENTITY_PROVIDER_ISSUER_UNIQUE_TABLE)


_FINGERPRINT_TABLE = "rotated_refresh_tokens"


def upgrade_rotated_refresh_token_client_fingerprint() -> None:
    """Delete the rotated records, which have no fingerprint, then add the non-null client fingerprint."""
    op.execute("DELETE FROM rotated_refresh_tokens")
    op.add_column(
        _FINGERPRINT_TABLE,
        sa.Column(
            "client_fingerprint",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hex of the rotating client's network and User-Agent, joined by a newline",
        ),
    )


def downgrade_rotated_refresh_token_client_fingerprint() -> None:
    """Drop the client fingerprint."""
    op.drop_column(_FINGERPRINT_TABLE, "client_fingerprint")


_OAUTH_STATE_ENCRYPTED_SECRETS_TABLE = "oauth_states"


def upgrade_oauth_state_encrypted_secrets() -> None:
    """Delete the plain-text states, then widen the nonce and verifier columns to hold Fernet tokens."""
    op.execute("DELETE FROM oauth_states")
    op.alter_column(
        _OAUTH_STATE_ENCRYPTED_SECRETS_TABLE,
        "nonce",
        existing_type=sa.String(length=64),
        type_=sa.Text(),
        existing_nullable=False,
        existing_comment="OIDC nonce for ID token validation",
        comment="Fernet-encrypted OIDC nonce for ID token validation",
    )
    op.alter_column(
        _OAUTH_STATE_ENCRYPTED_SECRETS_TABLE,
        "idp_code_verifier",
        existing_type=sa.String(length=128),
        type_=sa.Text(),
        existing_nullable=True,
        existing_comment="PKCE verifier sent to the identity provider at the token exchange",
        comment="Fernet-encrypted PKCE verifier sent to the identity provider at the token exchange",
    )


def downgrade_oauth_state_encrypted_secrets() -> None:
    """Delete the encrypted states, then narrow the nonce and verifier columns back."""
    op.execute("DELETE FROM oauth_states")
    op.alter_column(
        _OAUTH_STATE_ENCRYPTED_SECRETS_TABLE,
        "idp_code_verifier",
        existing_type=sa.Text(),
        type_=sa.String(length=128),
        existing_nullable=True,
        existing_comment="Fernet-encrypted PKCE verifier sent to the identity provider at the token exchange",
        comment="PKCE verifier sent to the identity provider at the token exchange",
    )
    op.alter_column(
        _OAUTH_STATE_ENCRYPTED_SECRETS_TABLE,
        "nonce",
        existing_type=sa.Text(),
        type_=sa.String(length=64),
        existing_nullable=False,
        existing_comment="Fernet-encrypted OIDC nonce for ID token validation",
        comment="OIDC nonce for ID token validation",
    )


def upgrade_password_breach_check() -> None:
    """Add the switch, off for every existing install."""
    op.add_column(
        "server_settings",
        sa.Column(
            "password_breach_check_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Refuse new passwords found in a known data breach (true - yes, false - no)",
        ),
    )


def downgrade_password_breach_check() -> None:
    """Drop the switch."""
    op.drop_column("server_settings", "password_breach_check_enabled")


def upgrade_session_idle_timeout_default() -> None:
    """Turn the idle timeout on at 72 hours when no account exists and the shipped values are untouched."""
    op.execute(
        sa.text(
            "UPDATE server_settings SET session_idle_timeout_enabled = :enabled, session_idle_timeout_hours = 72 "
            "WHERE id = 1 AND session_idle_timeout_enabled = :disabled AND session_idle_timeout_hours = 1 "
            "AND NOT EXISTS (SELECT 1 FROM users)"
        ).bindparams(
            sa.bindparam("enabled", True, type_=sa.Boolean()), sa.bindparam("disabled", False, type_=sa.Boolean())
        )
    )


def downgrade_session_idle_timeout_default() -> None:
    """Restore the shipped values when the row still holds exactly what the upgrade set.

    Whether the install was new is not knowable later, so a row at true and 72 is reverted; an administrator who
    chose exactly those values loses nothing functional beyond returning to the previous release's default.
    """
    op.execute(
        sa.text(
            "UPDATE server_settings SET session_idle_timeout_enabled = :disabled, session_idle_timeout_hours = 1 "
            "WHERE id = 1 AND session_idle_timeout_enabled = :enabled AND session_idle_timeout_hours = 72"
        ).bindparams(
            sa.bindparam("enabled", True, type_=sa.Boolean()), sa.bindparam("disabled", False, type_=sa.Boolean())
        )
    )


# The running activity types (1, 2, 3, 34, 40), the rpm/spm cutoff (100) and the
# plausible cadence ceiling (255) are inlined as a snapshot; a migration must not
# follow later edits to app code. A stream ``cad`` is cast to numeric only when
# it matches ``^[0-9]+([.][0-9]+)?$``, so a non-numeric sample cannot abort it.


def upgrade_normalize_running_cadence_to_spm() -> None:
    """Double running cadence still stored as a single-leg rate."""
    op.execute(
        """
        CREATE TABLE cadence_spm_migration_rows (
            activity_id integer PRIMARY KEY,
            average_cad integer,
            max_cad integer,
            per_leg_avg numeric,
            per_leg_max numeric
        )
        """
    )

    op.execute(
        """
        INSERT INTO cadence_spm_migration_rows (activity_id, average_cad, max_cad, per_leg_avg, per_leg_max)
        WITH stream_samples AS (
            SELECT s.activity_id, v.cad
            FROM activities_streams s
            JOIN activities a ON a.id = s.activity_id AND a.activity_type IN (1, 2, 3, 34, 40)
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE WHEN json_typeof(s.stream_waypoints) = 'array' THEN s.stream_waypoints::jsonb ELSE '[]'::jsonb END
            ) AS t(elem)
            CROSS JOIN LATERAL (
                SELECT CASE WHEN (t.elem ->> 'cad') ~ '^[0-9]+([.][0-9]+)?$' THEN (t.elem ->> 'cad')::numeric END AS cad
            ) AS v
            WHERE s.stream_type = 3
              AND v.cad IS NOT NULL
        ),
        stream_cad AS (
            SELECT activity_id, avg(cad) AS avg_cad, max(cad) AS max_cad
            FROM stream_samples
            WHERE cad > 0
            GROUP BY activity_id
        ),
        lap_cad AS (
            SELECT l.activity_id,
                   avg(COALESCE(
                       NULLIF(l.avg_cadence, 0) + COALESCE(l.avg_fractional_cadence, 0),
                       NULLIF(l.max_cadence, 0) + COALESCE(l.max_fractional_cadence, 0)
                   )) AS avg_cad,
                   max(COALESCE(
                       NULLIF(l.max_cadence, 0) + COALESCE(l.max_fractional_cadence, 0),
                       NULLIF(l.avg_cadence, 0) + COALESCE(l.avg_fractional_cadence, 0)
                   )) AS max_cad
            FROM activity_laps l
            JOIN activities a ON a.id = l.activity_id AND a.activity_type IN (1, 2, 3, 34, 40)
            WHERE COALESCE(NULLIF(l.avg_cadence, 0), NULLIF(l.max_cadence, 0)) IS NOT NULL
            GROUP BY l.activity_id
        ),
        out_of_range AS (
            SELECT activity_id FROM stream_samples WHERE cad > 255
            UNION
            SELECT activity_id
            FROM activity_laps
            WHERE avg_cadence + COALESCE(avg_fractional_cadence, 0) > 255
               OR max_cadence + COALESCE(max_fractional_cadence, 0) > 255
        ),
        decided AS (
            SELECT a.id,
                   a.average_cad,
                   a.max_cad,
                   COALESCE(NULLIF(a.average_cad, 0), sc.avg_cad, lc.avg_cad) AS per_leg_avg,
                   COALESCE(NULLIF(a.max_cad, 0), sc.max_cad, lc.max_cad, a.max_cad) AS per_leg_max
            FROM activities a
            LEFT JOIN stream_cad sc ON sc.activity_id = a.id
            LEFT JOIN lap_cad lc ON lc.activity_id = a.id
            WHERE a.activity_type IN (1, 2, 3, 34, 40)
              AND COALESCE(a.max_cad, 0) <= 255
              AND NOT EXISTS (SELECT 1 FROM out_of_range o WHERE o.activity_id = a.id)
        )
        SELECT id, average_cad, max_cad, per_leg_avg, per_leg_max
        FROM decided
        WHERE COALESCE(per_leg_avg, NULLIF(max_cad, 0)) < 100
        """
    )

    op.execute(
        """
        UPDATE activities_streams s
        SET stream_waypoints = (
            SELECT jsonb_agg(
                CASE
                    WHEN (elem ->> 'cad') IS NULL OR (elem ->> 'cad') !~ '^[0-9]+([.][0-9]+)?$' THEN elem
                    ELSE jsonb_set(elem, '{cad}', to_jsonb(round((elem ->> 'cad')::numeric * 2)::int))
                END
                ORDER BY ord
            )::json
            FROM jsonb_array_elements(s.stream_waypoints::jsonb) WITH ORDINALITY AS t(elem, ord)
        )
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = s.activity_id
          AND s.stream_type = 3
          AND CASE WHEN json_typeof(s.stream_waypoints) = 'array' THEN json_array_length(s.stream_waypoints) > 0 END
        """
    )

    op.execute(
        """
        UPDATE activity_laps l
        SET avg_cadence = round((l.avg_cadence + COALESCE(l.avg_fractional_cadence, 0)) * 2),
            max_cadence = round((l.max_cadence + COALESCE(l.max_fractional_cadence, 0)) * 2),
            avg_fractional_cadence = CASE WHEN l.avg_cadence IS NULL THEN l.avg_fractional_cadence END,
            max_fractional_cadence = CASE WHEN l.max_cadence IS NULL THEN l.max_fractional_cadence END
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = l.activity_id
          AND (l.avg_cadence IS NOT NULL OR l.max_cadence IS NOT NULL)
        """
    )

    op.execute(
        """
        UPDATE activities a
        SET average_cad = round(r.per_leg_avg * 2)::int,
            max_cad = round(r.per_leg_max * 2)::int
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = a.id
        """
    )


def downgrade_normalize_running_cadence_to_spm() -> None:
    """Return the recorded activities' cadence to single-leg rpm.

    The module docstring lists where the inverse is not exact.
    """
    op.execute(
        """
        UPDATE activities_streams s
        SET stream_waypoints = (
            SELECT jsonb_agg(
                CASE
                    WHEN (elem ->> 'cad') IS NULL OR (elem ->> 'cad') !~ '^[0-9]+([.][0-9]+)?$' THEN elem
                    ELSE jsonb_set(elem, '{cad}', to_jsonb(floor((elem ->> 'cad')::numeric / 2)::int))
                END
                ORDER BY ord
            )::json
            FROM jsonb_array_elements(s.stream_waypoints::jsonb) WITH ORDINALITY AS t(elem, ord)
        )
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = s.activity_id
          AND s.stream_type = 3
          AND CASE WHEN json_typeof(s.stream_waypoints) = 'array' THEN json_array_length(s.stream_waypoints) > 0 END
        """
    )

    op.execute(
        """
        UPDATE activity_laps l
        SET avg_cadence = l.avg_cadence / 2,
            max_cadence = l.max_cadence / 2
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = l.activity_id
        """
    )

    op.execute(
        """
        UPDATE activities a
        SET average_cad = r.average_cad,
            max_cad = r.max_cad
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = a.id
        """
    )

    op.execute("DROP TABLE cadence_spm_migration_rows")


def upgrade() -> None:
    """Run every step in order."""
    upgrade_credentials_password_change_required()
    upgrade_idp_session_token_id_token()
    upgrade_idp_provider_type_link_and_sync_flags()
    upgrade_session_client_type()
    upgrade_users_created_at()
    upgrade_idp_session_token_sid()
    upgrade_identity_provider_issuer_unique()
    upgrade_rotated_refresh_token_client_fingerprint()
    upgrade_oauth_state_encrypted_secrets()
    upgrade_password_breach_check()
    upgrade_session_idle_timeout_default()
    upgrade_normalize_running_cadence_to_spm()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_normalize_running_cadence_to_spm()
    downgrade_session_idle_timeout_default()
    downgrade_password_breach_check()
    downgrade_oauth_state_encrypted_secrets()
    downgrade_rotated_refresh_token_client_fingerprint()
    downgrade_identity_provider_issuer_unique()
    downgrade_idp_session_token_sid()
    downgrade_users_created_at()
    downgrade_session_client_type()
    downgrade_idp_provider_type_link_and_sync_flags()
    downgrade_idp_session_token_id_token()
    downgrade_credentials_password_change_required()
