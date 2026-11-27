"""Matching and provisioning of local users from identity-provider claims."""

import itertools
import secrets as secrets_module
import uuid
from typing import Any

import jasil.audit as jasil_audit
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.claim_mapping as claim_mapping
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.event_publishers as idp_event_publishers
import modules.auth.lockout.integration_service as lockout_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

#: The answer to a sign-in whose staged writes can no longer be applied; the client signs in again.
_SIGN_IN_ENDED_MESSAGE = "The sign-in can no longer be completed"


class SsoSignInRefusedError(core_exceptions.PermissionDeniedError):
    """An SSO sign-in refused for a reason the login page names to the user.

    Attributes:
        login_error: The ``error`` code the login page shows a specific message for.
    """

    def __init__(self, detail: str, *, login_error: str) -> None:
        """Initialise the refusal with its message and login-page code.

        Args:
            detail: Why the sign-in was refused.
            login_error: The ``error`` code the login page shows a specific message for.
        """
        super().__init__(detail)
        self.login_error = login_error


class SsoAccountInactiveError(SsoSignInRefusedError):
    """An SSO sign-in refused because the account it signs in to is not active.

    Attributes:
        user_id: The inactive account.
    """

    def __init__(self, detail: str, *, login_error: str, user_id: uuid.UUID) -> None:
        """Initialise the refusal with its message, login-page code and account.

        Args:
            detail: Why the sign-in was refused.
            login_error: The ``error`` code the login page shows a specific message for.
            user_id: The inactive account.
        """
        super().__init__(detail, login_error=login_error)
        self.user_id = user_id


def require_active_user(user: users_schema.UserRead, db: Session) -> None:
    """Refuse an inactive account's SSO sign-in, with the login page's code for what the user can do.

    This is the one place that decides an inactive account's refusal. It only runs for an account the provider
    has proven the user owns (linked by subject, or matched by a verified email), so naming the account's state
    reveals nothing to anyone else. An account awaiting an administrator's approval is told to wait; one an
    administrator deactivated or a deletion request ended, and any other inactive account, cannot sign in.

    Args:
        user: The account the sign-in resolved to.
        db: Database session.

    Raises:
        SsoAccountInactiveError: If the account is not active.
    """
    try:
        users_integration.require_active_user(user)
    except core_exceptions.PermissionDeniedError as err:
        if user.pending_admin_approval and not users_integration.is_deactivated(user.id, db):
            raise SsoAccountInactiveError(
                "The account is awaiting administrator approval", login_error="sso_approval_pending", user_id=user.id
            ) from err
        raise SsoAccountInactiveError(
            "The account is not active", login_error="sso_account_disabled", user_id=user.id
        ) from err


def stage_identity_link(user_id: uuid.UUID, idp_id: uuid.UUID, db: Session) -> None:
    """Stage the audit row of a provider linked to an account, in the transaction that commits the link.

    Args:
        user_id: The account the provider was linked to.
        idp_id: The provider that was linked.
        db: Database session.
    """
    jasil_audit.stage(
        db,
        idp_audit_actions.IDENTITY_LINK_LINK,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=idp_audit_actions.IdentityLinkDetails(idp_id=idp_id),
    )


def record_identity_link_refused(
    user_id: uuid.UUID,
    idp_id: uuid.UUID,
    reason: idp_audit_actions.IdentityLinkRefusal,
    outcome: jasil_audit.Outcome = jasil_audit.Outcome.DENIED,
) -> None:
    """Record a refused link in its own transaction, since the refused request rolls back.

    Args:
        user_id: The account the provider was to be linked to.
        idp_id: The provider that was to be linked.
        reason: Why the link was refused.
        outcome: ``DENIED`` for a refusal by policy, ``FAILURE`` for a link that could not be completed.
    """
    jasil_audit.record_detached(
        idp_audit_actions.IDENTITY_LINK_LINK,
        outcome=outcome,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=idp_audit_actions.IdentityLinkDetails(idp_id=idp_id, reason=reason),
    )


#: Validates a username with the same rule the users module applies to every account.
_USERNAME_ADAPTER = TypeAdapter(users_schema.UserUsername)

#: Longest username a new account may start from; leaves room for ``_`` and the six-digit uniqueness suffix.
MAX_USERNAME_BASE_LENGTH = 250 - len("_") - 6

#: Characters trimmed from both ends of a sanitised username.
_USERNAME_EDGE_CHARS = "._-"

#: Number of subject characters in the fallback username.
_FALLBACK_ID_LENGTH = 8


def _is_valid_username(value: str) -> bool:
    """Return whether ``value`` satisfies the username rule of the users module."""
    try:
        _USERNAME_ADAPTER.validate_python(value)
    except ValidationError:
        return False
    return True


def _sanitise_username(value: str) -> str:
    """Replace each run of disallowed characters with ``_`` and trim ``._-`` from both ends.

    Args:
        value: The raw text to turn into a username.

    Returns:
        The sanitised text, empty when nothing usable is left.
    """
    runs = itertools.groupby(value, key=_is_valid_username)
    cleaned = "".join("".join(run) if valid else "_" for valid, run in runs)
    return cleaned.strip(_USERNAME_EDGE_CHARS)


def derive_sso_username(claimed_username: Any, subject: str) -> str:
    """Choose the base username for an account created through single sign-on.

    No part of an email address becomes a username: usernames are visible to other users. A claim that
    already is a valid username is used as is, a claim containing ``@`` (an email or a UPN) is ignored, and any
    other claim is sanitised. With nothing usable left, the name is ``user_`` plus the first characters of the
    sanitised subject, or of the subject's hash when the subject has too few or is an email.

    Args:
        claimed_username: The username mapped from the identity provider claims, if any.
        subject: The identity provider's subject identifier.

    Returns:
        A valid username short enough to take the uniqueness suffix.
    """
    if isinstance(claimed_username, str) and "@" not in claimed_username:
        if _is_valid_username(claimed_username) and len(claimed_username) <= MAX_USERNAME_BASE_LENGTH:
            return claimed_username
        sanitised = _sanitise_username(claimed_username)[:MAX_USERNAME_BASE_LENGTH].strip(_USERNAME_EDGE_CHARS)
        if sanitised:
            return sanitised

    subject_id = "" if "@" in subject else _sanitise_username(subject)[:_FALLBACK_ID_LENGTH]
    if len(subject_id) < _FALLBACK_ID_LENGTH:
        subject_id = core_hashing.sha256_hex(subject)[:_FALLBACK_ID_LENGTH]
    return f"user_{subject_id}"


def find_or_create_user(
    idp: identity_provider_contracts.IdentityProviderState,
    subject: str,
    userinfo: dict[str, Any],
    db: Session,
) -> tuple[users_schema.UserRead, identity_provider_contracts.StagedSignIn | None]:
    """Find the account a sign-in is for, or create a new one if allowed, and return what its completion applies.

    The steps, in order:
    1. Find the user linked to the identity provider (IdP) with the subject identifier.
    2. Refuse an email the IdP did not verify (``sso_email_unverified``), before any lookup by email. An
       unverified email is never matched to a local account and never creates one, so the browser error, the
       audit reason and the audit action are the same whether or not a local account has that address.
    3. Find a user by the verified email, but only when the IdP has ``link_by_email`` on and the local account's
       email is verified too. A refusal here (``sso_link_by_email_disabled``) names an account only to someone the
       provider proved owns the address.
    4. If still not found and auto-creation is enabled, create a new user from the IdP information.

    Nothing is written to an existing account: it may still need its second factor. Its link (for an account
    matched by email), profile sync and last-login stamp are returned as a :class:`StagedSignIn`, which
    :func:`apply_staged_sign_in` applies when the sign-in completes. A new account has no second factor yet, so it
    is created and linked here and nothing is staged for it. A linked or matched account that is not active is
    refused through :func:`require_active_user`.

    Args:
        idp (identity_provider_contracts.IdentityProviderState): The identity provider instance.
        subject (str): The unique subject identifier from the IdP.
        userinfo (Dict[str, Any]): User information/claims from the IdP.
        db (Session): Database session.

    Returns:
        The found or newly created user, and what the sign-in's completion applies to an existing account (None for
        a new one). A newly created account is inactive while the server's sign-up policy requires email
        verification or admin approval.

    Raises:
        SsoAccountInactiveError: If the existing account is inactive.
        SsoSignInRefusedError: If the IdP's email is not verified, an existing account matches the email and the
            IdP does not link by email, or account creation is disabled and no existing user is found.
        PermissionDeniedError: If the matching account's own email is not verified.
    """
    # Try to find existing user by IdP link
    link = identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id(idp.id, subject, db)

    if link:
        # Fetch the linked user through the CRUD layer so we work with
        # the UserRead schema rather than reaching into the ORM
        # relationship (link.users) and crossing the module boundary.
        user = users_integration.get_user(link.user_id, db)
        if user is None:
            raise core_exceptions.NotFoundError("User not found")
        require_active_user(user, db)
        return user, _staged_sign_in(user, idp, subject, userinfo, create_link=False)

    # Try to find by email (for linking existing accounts).
    #
    # SECURITY (account-takeover prevention): only auto-link an
    # external identity to an EXISTING local account when the IdP
    # asserts that the email is verified (standard OIDC
    # ``email_verified`` claim). Without this gate, an attacker who
    # registers an unverified address matching a victim's email at a
    # permissive IdP would be auto-linked into — and gain control of —
    # the victim's existing account on first SSO login. Subject-based
    # linking above is unaffected; this only guards the email fallback.
    mapped_data = claim_mapping.map_user_claims(idp, userinfo)
    email = mapped_data.get("email")

    if email and not claim_mapping.is_email_verified(idp, userinfo):
        # Refused before any lookup by email, so the answer cannot tell whether a local account has the address.
        logger.warning(
            "SSO sign-in refused: IdP <name> did not assert a verified email",
            extra=core_logger.context(name=idp.name),
        )
        raise SsoSignInRefusedError(
            f"{idp.name} did not verify the email address, so it cannot be used to sign in",
            login_error="sso_email_unverified",
        )

    if email:
        user = users_integration.get_user_by_email(email, db)
        if user:
            if not idp.link_by_email:
                record_identity_link_refused(
                    user.id, idp.id, idp_audit_actions.IdentityLinkRefusal.LINK_BY_EMAIL_DISABLED
                )
                logger.warning(
                    "Refusing to link IdP <name> to account <username_log_id>: the provider does not link by email",
                    extra=core_logger.context(
                        name=idp.name, username_log_id=lockout_integration.username_log_identifier(user.username)
                    ),
                )
                raise SsoSignInRefusedError(
                    "Cannot link this identity provider to an existing account because the provider does not "
                    "link by email. Sign in with your password and link the provider from your settings.",
                    login_error="sso_link_by_email_disabled",
                )

            # An unverified local address can be claimed by anyone who set it on their own account, so
            # the IdP's assertion proves nothing about who owns this account.
            if not user.email_verified:
                record_identity_link_refused(
                    user.id, idp.id, idp_audit_actions.IdentityLinkRefusal.ACCOUNT_EMAIL_UNVERIFIED
                )
                logger.warning(
                    "Refusing to link IdP <name> to account <username_log_id>: the account email is not verified",
                    extra=core_logger.context(
                        name=idp.name, username_log_id=lockout_integration.username_log_identifier(user.username)
                    ),
                )
                raise core_exceptions.PermissionDeniedError(
                    "Cannot link this identity provider to an existing "
                    "account because the account email is not verified. "
                    "Verify the email address and try again."
                )

            require_active_user(user, db)
            return user, _staged_sign_in(user, idp, subject, userinfo, create_link=True)

    # A new account needs the server to allow sign-up through SSO and the provider to allow account creation.
    server_allows = server_settings_integration.get_server_settings(db).signup_sso_enabled
    if not (server_allows and idp.auto_create_users):
        logger.warning(
            "SSO sign-in refused: account creation is disabled for IdP <name>",
            extra=core_logger.context(
                name=idp.name, server_allows=server_allows, provider_allows=idp.auto_create_users
            ),
        )
        raise SsoSignInRefusedError(
            "User account creation through SSO is disabled", login_error="sso_auto_create_disabled"
        )

    return create_user_from_idp(idp, subject, mapped_data, db), None


def _staged_sign_in(
    user: users_schema.UserRead,
    idp: identity_provider_contracts.IdentityProviderState,
    subject: str,
    userinfo: dict[str, Any],
    *,
    create_link: bool,
) -> identity_provider_contracts.StagedSignIn:
    """Return what the completion of a sign-in to an existing account applies to it.

    Args:
        user: The account the sign-in is for.
        idp: The provider the user signed in through.
        subject: The provider's identifier of the user.
        userinfo: The provider's claims.
        create_link: Whether the account was matched by its verified email and so gets the link.

    Returns:
        The staged sign-in.
    """
    return identity_provider_contracts.StagedSignIn(
        user_id=user.id,
        idp_id=idp.id,
        subject=subject,
        create_link=create_link,
        claims=claim_mapping.synced_claims(idp, userinfo),
    )


def create_user_from_idp(
    idp: identity_provider_contracts.IdentityProviderState,
    subject: str,
    mapped_data: dict[str, Any],
    db: Session,
) -> users_schema.UserRead:
    """Creates a new user in the database based on identity provider (IdP) information.

    This method generates a unique username, creates a user with mapped data from the IdP
    using the existing CRUD layer, and links the user to the IdP subject. SSO accounts get
    no local password credential: no row is written to ``users_local_credentials`` and
    ``has_local_password`` reports ``False``. Units and currency are the server's defaults. The caller has
    already refused an email the IdP did not verify, so the account's email is verified.

    Args:
        idp (identity_provider_contracts.IdentityProviderState): The identity provider instance.
        subject (str): The unique subject identifier from the IdP.
        mapped_data (Dict[str, Any]): User data mapped from the IdP (e.g., username, email, name).
        db (Session): The database session.

    Returns:
        users_schema.UserRead: The newly created user instance.

    Raises:
        SsoSignInRefusedError: If the IdP did not share an email address, as every account needs a real one.
        domain error: If user creation fails (e.g., duplicate username/email).
    """
    email = mapped_data.get("email")
    if not email:
        raise SsoSignInRefusedError(
            f"{idp.name} did not share an email address, so no account can be created",
            login_error="sso_email_missing",
        )

    server_settings = server_settings_integration.get_server_settings(db)

    # Ensure username is unique; the base leaves room for the suffix
    base_username = derive_sso_username(mapped_data.get("username"), subject)
    username = base_username
    while users_integration.get_user_by_username(username, db):
        # secrets.randbelow is a CSPRNG; generate a 6-digit suffix
        username = f"{base_username}_{secrets_module.randbelow(900000) + 100000}"

    profile = users_schema.UserBase(
        username=username,
        email=email,
        city=mapped_data.get("city"),
        birthdate=mapped_data.get("birthdate"),
        name=mapped_data.get("name", username),
        height=mapped_data.get("height"),
        max_heart_rate=mapped_data.get("max_heart_rate"),
    )

    created_user = users_integration.create_sso_user(profile, server_settings, db, email_verified=True)

    # Create the IdP link
    identity_provider_links_integration.create_user_identity_provider(created_user.id, idp.id, subject, db)
    stage_identity_link(created_user.id, idp.id, db)

    logger.info(
        "Created new user <username_log_id> from IdP <name>",
        extra=core_logger.context(
            username_log_id=lockout_integration.username_log_identifier(created_user.username), name=idp.name
        ),
    )

    return created_user


def apply_staged_sign_in(
    user: users_schema.UserRead,
    idp_id: uuid.UUID,
    staged: identity_provider_contracts.StagedSignIn | None,
    db: Session,
) -> users_schema.UserRead:
    """Apply what a sign-in's callback staged for the account, in the transaction that completes the sign-in.

    The caller has claimed the session, so this runs once per session, and holds the account's security-generation
    lock. In order: the link of an account matched by email is created, after checking again that the subject is not
    linked to another account and the account has no other link to the provider, with its audit row and
    ``auth.idp_linked`` event; the profile is synced with the staged claims under the provider's current switches;
    and the link's last-login time is stamped. Everything is staged for the caller's commit.

    Without a staged record (none was staged for a new account, or the state store lost it), the sign-in completes
    with nothing applied only when the account is already linked to the provider, so a sign-in that needed its link
    fails closed.

    Args:
        user: The account the session belongs to.
        idp_id: The provider the session signed in through.
        staged: What the callback staged, or None when no record was found.
        db: Database session holding the completion's transaction.

    Returns:
        The account after the sync.

    Raises:
        SessionEndedError: If the record is missing for an account not linked to the provider, names another account
            or provider, the provider is gone or no longer links by email, the subject is no longer linked to the
            account, or the link cannot be created.
    """
    if staged is None:
        if identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(user.id, idp_id, db):
            return user
        logger.warning(
            "SSO sign-in refused: the link its callback staged is gone", extra=core_logger.context(user_id=user.id)
        )
        raise core_exceptions.SessionEndedError(_SIGN_IN_ENDED_MESSAGE)
    if staged.user_id != user.id or staged.idp_id != idp_id:
        logger.warning(
            "SSO sign-in refused: the staged sign-in names another account or provider",
            extra=core_logger.context(user_id=user.id),
        )
        raise core_exceptions.SessionEndedError(_SIGN_IN_ENDED_MESSAGE)
    idp = idp_crud.get_identity_provider(idp_id, db)
    if idp is None:
        raise core_exceptions.SessionEndedError(_SIGN_IN_ENDED_MESSAGE)

    link = identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id(
        idp.id, staged.subject, db
    )
    if link is None and staged.create_link:
        _link_matched_account(user, idp, staged.subject, db)
    elif link is None or link.user_id != user.id:
        if link is not None:
            record_identity_link_refused(
                user.id, idp.id, idp_audit_actions.IdentityLinkRefusal.LINKED_TO_ANOTHER_ACCOUNT
            )
        logger.warning(
            "SSO sign-in refused: the provider identity is no longer linked to the account",
            extra=core_logger.context(user_id=user.id, name=idp.name),
        )
        raise core_exceptions.SessionEndedError(_SIGN_IN_ENDED_MESSAGE)

    user = update_user_from_idp(user, idp, staged.claims, db)
    identity_provider_links_integration.update_user_identity_provider_last_login(user.id, idp.id, db)
    return user


def _link_matched_account(
    user: users_schema.UserRead,
    idp: identity_provider_contracts.IdentityProviderState,
    subject: str,
    db: Session,
) -> None:
    """Stage the link of an account a sign-in matched by its verified email, with its audit row and event.

    Args:
        user: The matched account.
        idp: The provider, as it is configured now.
        subject: The provider's identifier of the user, linked to no account.
        db: Database session holding the completion's transaction.

    Raises:
        SessionEndedError: If the provider no longer links by email, the account has another link to the provider,
            or a concurrent sign-in linked the subject first.
    """
    if not idp.link_by_email:
        record_identity_link_refused(user.id, idp.id, idp_audit_actions.IdentityLinkRefusal.LINK_BY_EMAIL_DISABLED)
        logger.warning(
            "SSO sign-in refused: IdP <name> stopped linking by email before the sign-in completed",
            extra=core_logger.context(user_id=user.id, name=idp.name),
        )
        raise core_exceptions.SessionEndedError(_SIGN_IN_ENDED_MESSAGE)
    if identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(user.id, idp.id, db):
        logger.warning(
            "SSO sign-in refused: the account is already linked to another identity at IdP <name>",
            extra=core_logger.context(user_id=user.id, name=idp.name),
        )
        raise core_exceptions.SessionEndedError(_SIGN_IN_ENDED_MESSAGE)
    try:
        identity_provider_links_integration.create_user_identity_provider(user.id, idp.id, subject, db)
    except core_exceptions.ConflictError as err:
        # A sign-in for another account linked the subject and committed first; the unique key decided.
        record_identity_link_refused(user.id, idp.id, idp_audit_actions.IdentityLinkRefusal.LINKED_TO_ANOTHER_ACCOUNT)
        logger.warning(
            "SSO sign-in refused: a concurrent sign-in linked the identity at IdP <name> first",
            extra=core_logger.context(user_id=user.id, name=idp.name),
        )
        raise core_exceptions.SessionEndedError(_SIGN_IN_ENDED_MESSAGE) from err
    stage_identity_link(user.id, idp.id, db)
    idp_event_publishers.publish_idp_linked(user.id, idp.id, db)
    logger.info(
        "Linked existing user <username_log_id> to IdP <name>",
        extra=core_logger.context(
            username_log_id=lockout_integration.username_log_identifier(user.username), name=idp.name
        ),
    )


def update_user_from_idp(
    user: users_schema.UserRead,
    idp: identity_provider_contracts.IdentityProviderState,
    claims: identity_provider_contracts.SyncedClaims,
    db: Session,
) -> users_schema.UserRead:
    """Stage the user's name and email from the claims an identity provider (IdP) sent.

    ``sync_user_info`` syncs the mapped name; ``sync_email`` syncs the email, and nothing else does. The name is
    written as the identity provider's, which is the source of truth, so it overwrites whatever version is stored.
    An email the IdP did not verify, or one already in use by another user, is never copied. A synced email goes
    through the users module's synced email change: the account's address becomes verified, its unused
    password-reset tokens are voided, the change is audited and the previous address is sent a notice. The caller
    commits.

    Args:
        user (users_schema.UserRead): The user schema instance to update.
        idp (identity_provider_contracts.IdentityProviderState): The identity provider instance with the sync
            switches.
        claims (identity_provider_contracts.SyncedClaims): The mapped claims the provider sent.
        db (Session): The SQLAlchemy database session.

    Returns:
        users_schema.UserRead: The updated user schema instance from database.
    """
    if not (idp.sync_user_info or idp.sync_email):
        return user

    updated_fields: list[str] = []

    if idp.sync_user_info and claims.name is not None and claims.name != user.name:
        logger.debug(
            "Syncing name for user <username_log_id> from IdP <name>",
            extra=core_logger.context(
                username_log_id=lockout_integration.username_log_identifier(user.username), name=idp.name
            ),
        )
        updated_user = user.model_copy(update={"name": claims.name})
        # The identity provider is the source of truth for the name, so it overwrites whatever version is stored.
        user = users_integration.edit_user(user.id, users_schema.UserEdit.from_read(updated_user), db, if_match="*")
        updated_fields.append("name")

    new_email = _synced_email(user, idp, claims, db)
    if new_email is not None:
        users_integration.stage_synced_email_change(user.id, new_email, db)
        user = users_integration.get_user(user.id, db) or user
        updated_fields.append("email")

    if updated_fields:
        logger.info(
            "Applying updates to user <username_log_id>: <updated_fields>",
            extra=core_logger.context(
                username_log_id=lockout_integration.username_log_identifier(user.username),
                updated_fields=sorted(updated_fields),
            ),
        )

    return user


def _synced_email(
    user: users_schema.UserRead,
    idp: identity_provider_contracts.IdentityProviderState,
    claims: identity_provider_contracts.SyncedClaims,
    db: Session,
) -> str | None:
    """Return the email to sync onto a user, or None when the account keeps its own.

    Args:
        user: The user the claims belong to.
        idp: The identity provider.
        claims: The mapped claims, which say whether the provider verified the email.
        db: Database session.

    Returns:
        The email, when ``sync_email`` is on and the provider verified an address the account does not have and
        no other account uses or has reserved.
    """
    # An email the IdP did not verify is never copied onto the account, since it becomes the verified address.
    if not (idp.sync_email and claims.email and claims.email_verified):
        return None
    email = claims.email.strip()
    if email.lower() == user.email.lower():
        return None
    if not users_integration.is_email_available(user.id, email, db):
        logger.warning(
            "Cannot sync email from IdP <name>: it is already in use by another user",
            extra=core_logger.context(name=idp.name),
        )
        return None
    logger.debug(
        "Syncing email for user <username_log_id> from IdP <name>",
        extra=core_logger.context(
            username_log_id=lockout_integration.username_log_identifier(user.username), name=idp.name
        ),
    )
    return email
