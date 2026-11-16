"""Authentication state, identity provider icons and session policy

The steps run in this order.

Keep a rotated refresh-token record until its own token expires
---------------------------------------------------------------

Reuse detection needs a rotated token's record for as long as that token could still be presented.
The purge used the deployment's default refresh-token lifetime, so with a longer lifetime set in the
server settings the record went while the token was still valid and a replay was no longer recognised
as theft. Each record now carries its token's expiry and is purged after it.

A token was issued before it was rotated, so ``rotated_at`` plus the configured lifetime is never
earlier than its real expiry; existing records are filled with that bound, or with the longest allowed
lifetime (365 days) when no settings row exists.

Index the columns the auth purges filter on
-------------------------------------------

The scheduled purges of password-reset tokens, sign-up tokens and sessions delete by expiry (and, for
sessions, by last activity) one bounded batch at a time. Without an index each batch scans the whole
table, so the columns they filter on are indexed.

Bind an identity-provider link to the browser that started it
-------------------------------------------------------------

A link's OAuth state now stores the SHA-256 of a secret the starting browser keeps in a cookie, and the
callback refuses a link that another browser finishes. Without it, the provider URL of a link an
attacker started on their own account would bind any victim who opened it to that account.

States are short-lived, so existing rows are left without a binding: a link begun before the upgrade
must be started again.

Use PKCE between this server and the identity provider
------------------------------------------------------

An SSO login or link now sends the provider an S256 code challenge and proves it at the token exchange with
a verifier kept on the OAuth state, so an authorization code that leaks before it is used cannot be redeemed
by anyone else.

States are short-lived, so existing rows are left without a verifier and finish without PKCE.

Name each OAuth state's flow and carry a step-up's session and action
---------------------------------------------------------------------

The callback read a state's flow from whether it had a user: a link had one, a login did not. A step-up
re-authentication also starts from a signed-in user, so a state now names its flow in ``purpose``, and a
step-up state records the session that started it and the operation it authorises.

Existing rows are short-lived and keep the flow they had: ``link`` when they carry a user, ``login``
otherwise.

Record the address a sign-up token proves and the address an email change replaces
----------------------------------------------------------------------------------

A sign-up token carried only its user, so an email-change link could not name the address it confirmed
and the new address was written to the account before it was verified. A token now records the address
it proves in ``email`` and, on an email-change token, the account's address at the time of the request in
``previous_email``, so a pending change lives on the token until it is confirmed.

Existing rows keep both columns empty: they are short-lived and were issued for the account's own address.

Record when an account was deactivated
--------------------------------------

An inactive account was either deactivated (by an administrator or a deletion request) or a sign-up not yet
verified or approved, and the row did not say which, so an email verification link could reactivate an
account an administrator had deactivated. ``deactivated_at`` marks a deactivation; a sign-up has none.

Existing rows are backfilled where the state proves a deactivation: an inactive account whose email is
verified and that is not awaiting approval. A sign-up (``_stage_signup_user``) is inactive only while its
email is unverified (``stage_email_verification`` verifies and activates it) or while it awaits approval
(``approve_user`` clears the flag and activates it), so such a row can only have been deactivated. The one
exception is an account created by a first identity-provider sign-in with the provider-verified email while
the server requires email verification: it starts inactive, verified and not awaiting approval, and is
marked deactivated too, so a verification link no longer activates it. Every other row stays null.

Widen the identity provider icon column
---------------------------------------

The icon holds a built-in key or a custom icon URL, and the form accepts a URL of up to 500 characters, which
the 100-character column and request schema rejected.

Flag identity providers that have an uploaded icon
--------------------------------------------------

The icon column held a built-in key or a custom icon URL, and a URL on another host is blocked by the page's
Content-Security-Policy. ``icon_uploaded`` marks a provider whose icon is stored in Endurain and served from it;
it is set only by the icon upload and removal routes, so an edited form never resets it. The icon column now holds
only a built-in key, so a custom URL is cleared.

Always apply the absolute session timeout
-----------------------------------------

``session_idle_timeout_enabled`` now turns only the idle timeout on or off; the absolute timeout always applies and
defaults to 720 hours (30 days). An install that never enabled the timeouts never enforced its stored absolute
timeout, so one left at the old 24-hour default moves to 720 hours instead of suddenly ending sessions after a day.
The idle timeout of such an install is at most 24 hours (the absolute timeout cannot be shorter), so 720 keeps the
check constraint.

Add users.weight_units
----------------------

Body weight was always presented in the unit system of ``users.units``, which also drives
distance, pace, elevation and temperature. Users who mix systems — the canonical example being
Canada, where running distances are discussed in kilometres but body weight in pounds — had no
way to split the two. ``weight_units`` overrides the system for body weight only, leaving
distance, pace, elevation and temperature on ``users.units``.

Nullable with no backfill. ``NULL`` means "not set" and displays exactly as before: weight
follows ``users.units``. Nothing changes for existing users.

Describe rotated_refresh_tokens.expires_at as the end of the replay grace window
--------------------------------------------------------------------------------

Only the column comment changes; no data or type is touched.

Password policy follows NIST SP 800-63B-4 (length and blocklist, no composition rules)
--------------------------------------------------------------------------------------

``server_settings.password_type`` chose between a composition policy and a length-only one; the policy is now one
rule set, so the column is dropped. Both minimum lengths default to 15. An install whose lengths still sit at the old
defaults (8 for regular users, 12 for administrators) moves to 15; a length an administrator chose is kept.

Revision ID: 9e4b7a2d6c18
Revises: 7e2c5a9f4b18
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e4b7a2d6c18"
down_revision: str | None = "7e2c5a9f4b18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_rotated_refresh_tokens_refresh_token_exp"


def upgrade_rotated_refresh_token_expiry() -> None:
    """Add, backfill and index the rotated token's expiry."""
    op.add_column(
        "rotated_refresh_tokens",
        sa.Column(
            "refresh_token_exp",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Expiry of the rotated refresh token; the record is purged after it",
        ),
    )
    op.execute(
        "UPDATE rotated_refresh_tokens SET refresh_token_exp = rotated_at + make_interval(days => COALESCE("
        "(SELECT refresh_token_expire_days FROM server_settings WHERE id = 1), 365))"
    )
    op.alter_column(
        "rotated_refresh_tokens", "refresh_token_exp", existing_type=sa.DateTime(timezone=True), nullable=False
    )
    op.create_index(_INDEX, "rotated_refresh_tokens", ["refresh_token_exp"])


def downgrade_rotated_refresh_token_expiry() -> None:
    """Drop the rotated token's expiry."""
    op.drop_index(_INDEX, table_name="rotated_refresh_tokens")
    op.drop_column("rotated_refresh_tokens", "refresh_token_exp")


_INDEXES = (
    ("password_reset_tokens", "expires_at"),
    ("sign_up_tokens", "expires_at"),
    ("users_sessions", "expires_at"),
    ("users_sessions", "last_activity_at"),
)


def upgrade_auth_purge_indexes() -> None:
    """Create the purge indexes."""
    for table, column in _INDEXES:
        op.create_index(op.f(f"ix_{table}_{column}"), table, [column], unique=False)


def downgrade_auth_purge_indexes() -> None:
    """Drop the purge indexes."""
    for table, column in reversed(_INDEXES):
        op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table)


def upgrade_oauth_state_browser_binding() -> None:
    """Add the link's browser-binding digest."""
    op.add_column(
        "oauth_states",
        sa.Column(
            "browser_binding_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 of the link's browser-binding cookie (link mode only)",
        ),
    )


def downgrade_oauth_state_browser_binding() -> None:
    """Drop the link's browser-binding digest."""
    op.drop_column("oauth_states", "browser_binding_hash")


def upgrade_oauth_state_idp_code_verifier() -> None:
    """Add the provider PKCE verifier."""
    op.add_column(
        "oauth_states",
        sa.Column(
            "idp_code_verifier",
            sa.String(length=128),
            nullable=True,
            comment="PKCE verifier sent to the identity provider at the token exchange",
        ),
    )


def downgrade_oauth_state_idp_code_verifier() -> None:
    """Drop the provider PKCE verifier."""
    op.drop_column("oauth_states", "idp_code_verifier")


def upgrade_oauth_state_purpose() -> None:
    """Add the flow, the step-up session and the step-up action."""
    op.add_column(
        "oauth_states",
        sa.Column(
            "purpose",
            sa.String(length=16),
            nullable=True,
            comment="Flow the state belongs to: login, link or step_up",
        ),
    )
    op.execute(sa.text("UPDATE oauth_states SET purpose = CASE WHEN user_id IS NULL THEN 'login' ELSE 'link' END"))
    op.alter_column("oauth_states", "purpose", existing_type=sa.String(length=16), nullable=False)
    op.add_column(
        "oauth_states",
        sa.Column(
            "session_id",
            sa.String(length=36),
            nullable=True,
            comment="Session that started a step-up flow, or a link that ends the user's other sessions",
        ),
    )
    op.add_column(
        "oauth_states",
        sa.Column(
            "action",
            sa.String(length=32),
            nullable=True,
            comment="Sensitive operation a step-up flow authorises (step-up only)",
        ),
    )
    op.alter_column(
        "oauth_states",
        "browser_binding_hash",
        existing_type=sa.String(length=64),
        existing_nullable=True,
        comment="SHA-256 of the browser-binding cookie (link and step-up flows)",
        existing_comment="SHA-256 of the link's browser-binding cookie (link mode only)",
    )


def downgrade_oauth_state_purpose() -> None:
    """Drop the flow, the step-up session and the step-up action."""
    op.alter_column(
        "oauth_states",
        "browser_binding_hash",
        existing_type=sa.String(length=64),
        existing_nullable=True,
        comment="SHA-256 of the link's browser-binding cookie (link mode only)",
        existing_comment="SHA-256 of the browser-binding cookie (link and step-up flows)",
    )
    op.execute(sa.text("DELETE FROM oauth_states WHERE purpose = 'step_up'"))
    op.drop_column("oauth_states", "action")
    op.drop_column("oauth_states", "session_id")
    op.drop_column("oauth_states", "purpose")


def upgrade_sign_up_token_email() -> None:
    """Add the proven address and the replaced address."""
    op.add_column(
        "sign_up_tokens",
        sa.Column(
            "email",
            sa.String(length=250),
            nullable=True,
            comment="Email address the token proves (empty on tokens issued before the column existed)",
        ),
    )
    op.add_column(
        "sign_up_tokens",
        sa.Column(
            "previous_email",
            sa.String(length=250),
            nullable=True,
            comment="Account email address when an email change was requested (email-change tokens only)",
        ),
    )


def downgrade_sign_up_token_email() -> None:
    """Drop the proven address and the replaced address."""
    op.drop_column("sign_up_tokens", "previous_email")
    op.drop_column("sign_up_tokens", "email")


def upgrade_users_deactivated_at() -> None:
    """Add the deactivation time and backfill the accounts that are provably deactivated."""
    op.add_column(
        "users",
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "When the account was deactivated by an administrator or a deletion request; "
                "null for an active account and for a sign-up not yet verified or approved"
            ),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE users SET deactivated_at = now() "
            "WHERE active = false AND pending_admin_approval = false AND email_verified = true"
        )
    )


def downgrade_users_deactivated_at() -> None:
    """Drop the deactivation time."""
    op.drop_column("users", "deactivated_at")


def upgrade_widen_identity_provider_icon() -> None:
    """Widen the icon column to 500 characters."""
    op.alter_column(
        "identity_providers",
        "icon",
        existing_type=sa.String(length=100),
        type_=sa.String(length=500),
        existing_nullable=True,
        existing_comment="Icon name (FontAwesome) or custom URL",
    )


def downgrade_widen_identity_provider_icon() -> None:
    """Narrow the icon column to 100 characters, clearing values that no longer fit (a cut URL is broken)."""
    op.execute("UPDATE identity_providers SET icon = NULL WHERE LENGTH(icon) > 100")
    op.alter_column(
        "identity_providers",
        "icon",
        existing_type=sa.String(length=500),
        type_=sa.String(length=100),
        existing_nullable=True,
        existing_comment="Icon name (FontAwesome) or custom URL",
    )


#: The built-in icon keys, as of this revision.
_BUILTIN_ICONS = ("authelia", "authentik", "casdoor", "keycloak", "pocketid")


def upgrade_add_identity_provider_icon_uploaded() -> None:
    """Add the uploaded-icon flag, false for every existing provider, and clear custom icon URLs."""
    op.add_column(
        "identity_providers",
        sa.Column(
            "icon_uploaded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Whether an uploaded icon is stored and shown instead of icon",
        ),
    )
    providers = sa.table("identity_providers", sa.column("icon", sa.String()))
    op.execute(providers.update().where(providers.c.icon.not_in(_BUILTIN_ICONS)).values(icon=None))


def downgrade_add_identity_provider_icon_uploaded() -> None:
    """Drop the uploaded-icon flag. The cleared custom icon URLs are not restored."""
    op.drop_column("identity_providers", "icon_uploaded")


_SESSION_ABSOLUTE_TIMEOUT_ALWAYS_NEW_COMMENT = (
    "Enforce the session idle timeout (true - yes, false - no); the absolute timeout always applies"
)

_SESSION_ABSOLUTE_TIMEOUT_ALWAYS_OLD_COMMENT = "Enforce session idle and absolute timeouts (true - yes, false - no)"


def upgrade_session_absolute_timeout_always() -> None:
    """Default the absolute timeout to 720 hours and lift the unenforced 24-hour value on installs without timeouts."""
    op.alter_column(
        "server_settings",
        "session_absolute_timeout_hours",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("720"),
    )
    op.alter_column(
        "server_settings",
        "session_idle_timeout_enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default=sa.text("false"),
        comment=_SESSION_ABSOLUTE_TIMEOUT_ALWAYS_NEW_COMMENT,
    )
    op.execute(
        "UPDATE server_settings SET session_absolute_timeout_hours = 720 "
        "WHERE session_idle_timeout_enabled = false AND session_absolute_timeout_hours = 24"
    )


def downgrade_session_absolute_timeout_always() -> None:
    """Restore the 24-hour default and the old comment. The raised absolute timeouts are not restored."""
    op.alter_column(
        "server_settings",
        "session_idle_timeout_enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default=sa.text("false"),
        comment=_SESSION_ABSOLUTE_TIMEOUT_ALWAYS_OLD_COMMENT,
    )
    op.alter_column(
        "server_settings",
        "session_absolute_timeout_hours",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("24"),
    )


def upgrade_add_user_weight_units() -> None:
    """Add the weight units override, unset for every existing user."""
    op.add_column(
        "users",
        sa.Column(
            "weight_units",
            sa.String(length=20),
            nullable=True,
            comment="User weight units override (metric - kg, imperial - lb), null follows units",
        ),
    )


def downgrade_add_user_weight_units() -> None:
    """Drop the weight units override."""
    op.drop_column("users", "weight_units")


_GRACE_NEW_COMMENT = "End of the replay grace window"

_GRACE_OLD_COMMENT = "Cleanup marker (rotated_at + 60 seconds)"


def upgrade_rotated_token_grace_comment() -> None:
    """Describe ``expires_at`` as the end of the replay grace window."""
    op.alter_column(
        "rotated_refresh_tokens",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        comment=_GRACE_NEW_COMMENT,
    )


def downgrade_rotated_token_grace_comment() -> None:
    """Restore the previous ``expires_at`` comment."""
    op.alter_column(
        "rotated_refresh_tokens",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        comment=_GRACE_OLD_COMMENT,
    )


def upgrade_nist_password_policy() -> None:
    """Drop ``password_type`` and move lengths still at the old defaults to 15."""
    op.drop_column("server_settings", "password_type")
    for column in ("password_length_regular_users", "password_length_admin_users"):
        op.alter_column(
            "server_settings",
            column,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=sa.text("15"),
        )
    op.execute("UPDATE server_settings SET password_length_regular_users = 15 WHERE password_length_regular_users = 8")
    op.execute("UPDATE server_settings SET password_length_admin_users = 15 WHERE password_length_admin_users = 12")


def downgrade_nist_password_policy() -> None:
    """Re-add ``password_type`` as 'strict' and drop the length defaults.

    The lengths are not reverted: a 15 could be the new default or a value an administrator chose.
    """
    op.add_column(
        "server_settings",
        sa.Column(
            "password_type",
            sa.String(),
            nullable=False,
            server_default="strict",
            comment="Password type policy (strict, length_only)",
        ),
    )
    op.alter_column("server_settings", "password_type", existing_type=sa.String(), server_default=None)
    for column in ("password_length_regular_users", "password_length_admin_users"):
        op.alter_column(
            "server_settings",
            column,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=None,
        )


def upgrade() -> None:
    """Run every step in order."""
    upgrade_rotated_refresh_token_expiry()
    upgrade_auth_purge_indexes()
    upgrade_oauth_state_browser_binding()
    upgrade_oauth_state_idp_code_verifier()
    upgrade_oauth_state_purpose()
    upgrade_sign_up_token_email()
    upgrade_users_deactivated_at()
    upgrade_widen_identity_provider_icon()
    upgrade_add_identity_provider_icon_uploaded()
    upgrade_session_absolute_timeout_always()
    upgrade_add_user_weight_units()
    upgrade_rotated_token_grace_comment()
    upgrade_nist_password_policy()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_nist_password_policy()
    downgrade_rotated_token_grace_comment()
    downgrade_add_user_weight_units()
    downgrade_session_absolute_timeout_always()
    downgrade_add_identity_provider_icon_uploaded()
    downgrade_widen_identity_provider_icon()
    downgrade_users_deactivated_at()
    downgrade_sign_up_token_email()
    downgrade_oauth_state_purpose()
    downgrade_oauth_state_idp_code_verifier()
    downgrade_oauth_state_browser_binding()
    downgrade_auth_purge_indexes()
    downgrade_rotated_refresh_token_expiry()
