"""Account security generations, MFA factors and token hardening

The steps run in this order.

Add account_security_generations and the generation an OAuth state was started under
------------------------------------------------------------------------------------

Each row holds an account's security generation, a counter advanced by every security change. A proof that is
pending when the change commits records the generation it was created under and stops being redeemable. There is no
backfill: an account without a row is at generation 0, and its row is created by the first security change or the
first redeem that checks it. ``oauth_states.security_generation`` records the generation of a link, step-up or
pending-exchange flow; existing states keep null and are refused when redeemed, which only ends flows that were
pending at the upgrade. ``oauth_states.ends_other_sessions`` records whether a link's callback ends the user's other
sessions, so ``session_id`` can always name the session that started the flow; existing states keep false.

Add the switch that allows sign-up through single sign-on
---------------------------------------------------------

Adds ``signup_sso_enabled`` to ``server_settings``. It is off for every existing install, so an upgrade stops
identity providers from creating accounts until an administrator turns it on; linking and signing in to existing
accounts is unaffected.

Record the account security generation an email-change token was issued under
-----------------------------------------------------------------------------

A pending email change is a proof: a security change after the request, such as a password reset, ends it. The column
holds the generation of the account when the change was requested, and the confirmation is refused when it no longer
matches. There is no backfill: a change that is pending at the upgrade keeps null and is refused when confirmed,
which only ends changes that were requested in the last 24 hours. Sign-up tokens keep null and are never checked.

Record when and how each session's owner signed in
--------------------------------------------------

A session now records ``auth_time`` (when the owner signed in) and ``amr`` (how they proved themselves, as RFC 8176
values). The sessions open before this revision take their creation time and ``["pwd"]``: the methods they used were
not recorded, and a session whose sign-in used a second factor or an identity provider is not told apart.

The downgrade drops both columns.

Move each user's TOTP secret from users_mfa to mfa_factors
----------------------------------------------------------

``mfa_factors`` holds one row per enrolled second factor, so a factor type that is not a TOTP secret can be added
without another table. Every enabled ``users_mfa`` row becomes a ``totp`` factor with the same ciphertext, so no
secret is re-encrypted, and ``users_mfa`` is dropped.

The downgrade recreates ``users_mfa`` with a row for every user, enabled where the user has a TOTP factor, and drops
``mfa_factors``.

Keep an email change's "this wasn't me" link working for seven days
-------------------------------------------------------------------

The link mailed to the previous address names the stored email change instead of the account's security generation,
so confirming the change no longer ends it. ``change_id`` identifies the change across the rows that re-issue its
confirmation link, ``revert_until`` ends its revert window and the row is kept until then, ``confirmed_at`` records
when a token was confirmed and ``reverted_at`` when the link was used.

Existing email-change rows become their own change with a window seven days after they were created. Rows that were
already used keep a null ``confirmed_at``, because a confirmed change cannot be told from a replaced one, so only a
change that is still pending at the upgrade can be cancelled with the link.

Stamp each known device with the security generation and describe it
--------------------------------------------------------------------

A known device counts only while its stamp equals the account's current security generation, so a security change
makes every device unknown at once. Existing rows are stamped with their user's current generation, so the upgrade
forgets no device and sends no new-device email for a device the user already signed in from; a user without a
generation row is at generation 0, the column's backfill default. ``browser``, ``operating_system`` and
``device_type`` let the user recognise a device in the list; existing rows keep them null until the device signs
in again.

Index the rotated tokens whose replacement is still stored
----------------------------------------------------------

The purge job clears the replacement refresh token of records whose grace window has ended, one bounded batch at
a time. A partial index on the end of the grace window, limited to records that still hold a replacement, lets
each batch find them without scanning the table; once cleared a record leaves the index.

The index is built ``CONCURRENTLY`` outside the migration transaction, so rotations are not blocked while it builds.

Record the native app an SSO session was handed to
--------------------------------------------------

A native app signs in through SSO with a redirect address that must be on the allowed list, and the session it
receives was not tied to that address. The session now records it, so the user and an administrator can tell the
sessions held by different apps apart. It is null for web sessions, for sessions that existed before this revision
and for sign-ins that carry no redirect.

Index the one-time token hashes and make them unique
----------------------------------------------------

Every unauthenticated password-reset and sign-up validation or confirmation looks a token up by its hash, which
scanned the whole table, and nothing enforced that a hash identifies one row, which the redelivery of a mail event
relies on. The hash columns now carry a unique index. A hash stored twice by older code (two concurrent deliveries
of one event) names one link, so the earliest row (by creation time, then id) is kept and the others are deleted.

The "Require MFA" server setting
--------------------------------

Adds ``server_settings.require_mfa``: ``off``, ``administrators`` or ``everyone``. It is ``off``, so no install
makes its users enrol a second factor until an administrator turns the requirement on.

Revision ID: a77c4e8f1b26
Revises: c91ac2dad0f0
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a77c4e8f1b26"
down_revision: str | None = "c91ac2dad0f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCOUNT_SECURITY_GENERATIONS_TABLE = "account_security_generations"

_STATES = "oauth_states"

_STATE_COLUMN = "security_generation"

_ENDS_OTHERS_COLUMN = "ends_other_sessions"

_SESSION_COLUMN = "session_id"


def upgrade_account_security_generations() -> None:
    """Create ``account_security_generations`` and add the OAuth-state columns."""
    op.create_table(
        _ACCOUNT_SECURITY_GENERATIONS_TABLE,
        sa.Column("user_id", sa.Integer(), nullable=False, comment="User the generation belongs to"),
        sa.Column(
            "generation",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Counter advanced by every security change; a pending proof records the value it was created under",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the generation last changed",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.add_column(
        _STATES,
        sa.Column(
            _STATE_COLUMN,
            sa.Integer(),
            nullable=True,
            comment="Account security generation the flow was started under; it is redeemed only while still current",
        ),
    )
    op.add_column(
        _STATES,
        sa.Column(
            _ENDS_OTHERS_COLUMN,
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Whether the callback of a link ends the user's other sessions",
        ),
    )
    op.alter_column(
        _STATES,
        _SESSION_COLUMN,
        existing_type=sa.String(length=36),
        existing_nullable=True,
        comment="Session that started a link or step-up flow",
        existing_comment="Session that started a step-up flow, or a link that ends the user's other sessions",
    )


def downgrade_account_security_generations() -> None:
    """Drop the OAuth-state columns and ``account_security_generations``."""
    op.alter_column(
        _STATES,
        _SESSION_COLUMN,
        existing_type=sa.String(length=36),
        existing_nullable=True,
        comment="Session that started a step-up flow, or a link that ends the user's other sessions",
        existing_comment="Session that started a link or step-up flow",
    )
    op.drop_column(_STATES, _ENDS_OTHERS_COLUMN)
    op.drop_column(_STATES, _STATE_COLUMN)
    op.drop_table(_ACCOUNT_SECURITY_GENERATIONS_TABLE)


def upgrade_signup_sso_enabled() -> None:
    """Add the SSO sign-up switch, off."""
    op.add_column(
        "server_settings",
        sa.Column(
            "signup_sso_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Allow identity providers to create accounts at first sign-in (true - yes, false - no)",
        ),
    )


def downgrade_signup_sso_enabled() -> None:
    """Drop the SSO sign-up switch."""
    op.drop_column("server_settings", "signup_sso_enabled")


def upgrade_sign_up_token_security_generation() -> None:
    """Add the nullable generation column."""
    op.add_column(
        "sign_up_tokens",
        sa.Column(
            "security_generation",
            sa.Integer(),
            nullable=True,
            comment="Account security generation an email-change token was issued under (email-change tokens only)",
        ),
    )


def downgrade_sign_up_token_security_generation() -> None:
    """Drop the generation column."""
    op.drop_column("sign_up_tokens", "security_generation")


_SESSION_AUTH_TIME_AMR_TABLE = "users_sessions"


def upgrade_session_auth_time_amr() -> None:
    """Add the sign-in time and methods, backfilled for the sessions that exist."""
    op.add_column(
        _SESSION_AUTH_TIME_AMR_TABLE,
        sa.Column(
            "auth_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the user signed in; refresh and step-up do not change it",
        ),
    )
    op.add_column(
        _SESSION_AUTH_TIME_AMR_TABLE,
        sa.Column(
            "amr",
            sa.JSON(),
            nullable=True,
            comment="Authentication methods of the sign-in (RFC 8176 values): pwd, fed, otp, mfa",
        ),
    )
    op.execute(sa.text("UPDATE users_sessions SET auth_time = created_at, amr = CAST('[\"pwd\"]' AS JSON)"))
    op.alter_column(_SESSION_AUTH_TIME_AMR_TABLE, "auth_time", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column(_SESSION_AUTH_TIME_AMR_TABLE, "amr", existing_type=sa.JSON(), nullable=False)


def downgrade_session_auth_time_amr() -> None:
    """Drop the sign-in time and methods."""
    op.drop_column(_SESSION_AUTH_TIME_AMR_TABLE, "amr")
    op.drop_column(_SESSION_AUTH_TIME_AMR_TABLE, "auth_time")


_MFA_FACTORS_TABLE = "mfa_factors"


def upgrade_mfa_factors() -> None:
    """Create ``mfa_factors`` and copy the enabled TOTP secrets into it."""
    op.create_table(
        _MFA_FACTORS_TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="FK to users"),
        sa.Column("type", sa.String(length=16), nullable=False, comment="Factor type: totp"),
        sa.Column("credential", sa.String(length=512), nullable=False, comment="Fernet-encrypted factor secret"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="When the factor was enrolled"),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the factor last verified a sign-in or step-up",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("type IN ('totp')", name="ck_mfa_factors_type"),
    )
    op.create_index("ix_mfa_factors_user_id", _MFA_FACTORS_TABLE, ["user_id"])
    op.create_index(
        "uq_mfa_factors_user_totp",
        _MFA_FACTORS_TABLE,
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("type = 'totp'"),
    )
    op.execute(
        sa.text(
            "INSERT INTO mfa_factors (user_id, type, credential, created_at) "
            "SELECT user_id, 'totp', mfa_secret, CURRENT_TIMESTAMP FROM users_mfa "
            "WHERE mfa_enabled AND mfa_secret IS NOT NULL"
        )
    )
    op.drop_table("users_mfa")


def downgrade_mfa_factors() -> None:
    """Recreate ``users_mfa`` from the factors and drop ``mfa_factors``."""
    op.create_table(
        "users_mfa",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="FK to users — one row per user"),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, comment="Whether TOTP MFA is active for this user"),
        sa.Column("mfa_secret", sa.String(length=512), nullable=True, comment="Fernet-encrypted TOTP secret"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_users_mfa_user_id"),
    )
    op.create_index("ix_users_mfa_user_id", "users_mfa", ["user_id"])
    op.execute(
        sa.text(
            "INSERT INTO users_mfa (user_id, mfa_enabled, mfa_secret) "
            "SELECT u.id, f.credential IS NOT NULL, f.credential FROM users u "
            "LEFT JOIN mfa_factors f ON f.user_id = u.id AND f.type = 'totp'"
        )
    )
    op.drop_index("uq_mfa_factors_user_totp", table_name=_MFA_FACTORS_TABLE)
    op.drop_index("ix_mfa_factors_user_id", table_name=_MFA_FACTORS_TABLE)
    op.drop_table(_MFA_FACTORS_TABLE)


_EMAIL_CHANGE_REVERT_TABLE = "sign_up_tokens"

_CHANGE_INDEX = "ix_sign_up_tokens_change_id"


def upgrade_email_change_revert() -> None:
    """Add the change, window, confirmation and revert columns and backfill the existing email-change rows."""
    op.add_column(
        _EMAIL_CHANGE_REVERT_TABLE,
        sa.Column(
            "change_id",
            sa.String(length=64),
            nullable=True,
            comment="Identifier of the email change the token belongs to (email-change tokens only)",
        ),
    )
    op.add_column(
        _EMAIL_CHANGE_REVERT_TABLE,
        sa.Column(
            "revert_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="End of the email change's revert window (email-change tokens only)",
        ),
    )
    op.add_column(
        _EMAIL_CHANGE_REVERT_TABLE,
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the token was confirmed, or the email change it records was applied",
        ),
    )
    op.add_column(
        _EMAIL_CHANGE_REVERT_TABLE,
        sa.Column(
            "reverted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the email change's revert link was used (email-change tokens only)",
        ),
    )
    op.create_index(_CHANGE_INDEX, _EMAIL_CHANGE_REVERT_TABLE, ["change_id"])
    op.execute(
        "UPDATE sign_up_tokens SET change_id = id, revert_until = created_at + INTERVAL '7 days' "
        "WHERE previous_email IS NOT NULL"
    )


def downgrade_email_change_revert() -> None:
    """Drop the columns."""
    op.drop_index(_CHANGE_INDEX, table_name=_EMAIL_CHANGE_REVERT_TABLE)
    op.drop_column(_EMAIL_CHANGE_REVERT_TABLE, "reverted_at")
    op.drop_column(_EMAIL_CHANGE_REVERT_TABLE, "confirmed_at")
    op.drop_column(_EMAIL_CHANGE_REVERT_TABLE, "revert_until")
    op.drop_column(_EMAIL_CHANGE_REVERT_TABLE, "change_id")


_KNOWN_DEVICE_SECURITY_GENERATION_TABLE = "auth_known_devices"


def upgrade_known_device_security_generation() -> None:
    """Add the generation stamp, backfilled from the account's generation, and the description columns."""
    op.add_column(
        _KNOWN_DEVICE_SECURITY_GENERATION_TABLE,
        sa.Column(
            "security_generation",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Account security generation the device was registered under; stale once a security change follows",
        ),
    )
    op.execute(
        "UPDATE auth_known_devices SET security_generation = account_security_generations.generation "
        "FROM account_security_generations WHERE account_security_generations.user_id = auth_known_devices.user_id"
    )
    op.alter_column(_KNOWN_DEVICE_SECURITY_GENERATION_TABLE, "security_generation", server_default=None)
    op.add_column(
        _KNOWN_DEVICE_SECURITY_GENERATION_TABLE,
        sa.Column(
            "browser", sa.String(length=45), nullable=True, comment="Browser of the last sign-in from the device"
        ),
    )
    op.add_column(
        _KNOWN_DEVICE_SECURITY_GENERATION_TABLE,
        sa.Column(
            "operating_system",
            sa.String(length=45),
            nullable=True,
            comment="Operating system of the last sign-in from the device",
        ),
    )
    op.add_column(
        _KNOWN_DEVICE_SECURITY_GENERATION_TABLE,
        sa.Column(
            "device_type",
            sa.String(length=45),
            nullable=True,
            comment="Device type of the last sign-in from the device",
        ),
    )


def downgrade_known_device_security_generation() -> None:
    """Drop the columns."""
    op.drop_column(_KNOWN_DEVICE_SECURITY_GENERATION_TABLE, "device_type")
    op.drop_column(_KNOWN_DEVICE_SECURITY_GENERATION_TABLE, "operating_system")
    op.drop_column(_KNOWN_DEVICE_SECURITY_GENERATION_TABLE, "browser")
    op.drop_column(_KNOWN_DEVICE_SECURITY_GENERATION_TABLE, "security_generation")


_INDEX = "ix_rotated_refresh_tokens_expires_at_with_replacement"


def upgrade_rotated_tokens_replacement_index() -> None:
    """Create the partial index on the end of the grace window."""
    with op.get_context().autocommit_block():
        op.create_index(
            _INDEX,
            "rotated_refresh_tokens",
            ["expires_at"],
            postgresql_where=sa.text("replacement_refresh_token IS NOT NULL"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade_rotated_tokens_replacement_index() -> None:
    """Drop the partial index."""
    with op.get_context().autocommit_block():
        op.drop_index(_INDEX, table_name="rotated_refresh_tokens", postgresql_concurrently=True, if_exists=True)


def upgrade_session_app_redirect_uri() -> None:
    """Add the nullable app redirect address to the sessions."""
    op.add_column(
        "users_sessions",
        sa.Column(
            "app_redirect_uri",
            sa.String(length=500),
            nullable=True,
            comment="Native-app redirect address an SSO sign-in handed the session to",
        ),
    )


def downgrade_session_app_redirect_uri() -> None:
    """Drop the app redirect address."""
    op.drop_column("users_sessions", "app_redirect_uri")


_TABLES = ("password_reset_tokens", "sign_up_tokens")


def upgrade_token_hash_unique() -> None:
    """Delete the later rows of any repeated hash, then create the unique indexes."""
    for name in _TABLES:
        tokens = sa.table(name, sa.column("id"), sa.column("token_hash"), sa.column("created_at"))
        earlier = tokens.alias("earlier")
        has_earlier_twin = (
            sa.select(sa.literal(1))
            .where(
                earlier.c.token_hash == tokens.c.token_hash,
                sa.or_(
                    earlier.c.created_at < tokens.c.created_at,
                    sa.and_(earlier.c.created_at == tokens.c.created_at, earlier.c.id < tokens.c.id),
                ),
            )
            .exists()
        )
        op.execute(tokens.delete().where(has_earlier_twin))
        op.create_index(op.f(f"ix_{name}_token_hash"), name, ["token_hash"], unique=True)


def downgrade_token_hash_unique() -> None:
    """Drop the unique indexes."""
    for table in reversed(_TABLES):
        op.drop_index(op.f(f"ix_{table}_token_hash"), table_name=table)


def upgrade_require_mfa() -> None:
    """Add the setting, off for every existing install, and the constraint that limits it to its three values."""
    op.add_column(
        "server_settings",
        sa.Column(
            "require_mfa",
            sa.String(length=20),
            server_default="off",
            nullable=False,
            comment="Require MFA of accounts without it (off, administrators, everyone)",
        ),
    )
    op.create_check_constraint(
        "require_mfa_check", "server_settings", "require_mfa IN ('off', 'administrators', 'everyone')"
    )


def downgrade_require_mfa() -> None:
    """Drop the constraint and the setting."""
    op.drop_constraint("require_mfa_check", "server_settings", type_="check")
    op.drop_column("server_settings", "require_mfa")


def upgrade() -> None:
    """Run every step in order."""
    upgrade_account_security_generations()
    upgrade_signup_sso_enabled()
    upgrade_sign_up_token_security_generation()
    upgrade_session_auth_time_amr()
    upgrade_mfa_factors()
    upgrade_email_change_revert()
    upgrade_known_device_security_generation()
    upgrade_rotated_tokens_replacement_index()
    upgrade_session_app_redirect_uri()
    upgrade_token_hash_unique()
    upgrade_require_mfa()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_require_mfa()
    downgrade_token_hash_unique()
    downgrade_session_app_redirect_uri()
    downgrade_rotated_tokens_replacement_index()
    downgrade_known_device_security_generation()
    downgrade_email_change_revert()
    downgrade_mfa_factors()
    downgrade_session_auth_time_amr()
    downgrade_sign_up_token_security_generation()
    downgrade_signup_sso_enabled()
    downgrade_account_security_generations()
