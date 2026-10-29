"""Matching and provisioning of local users from identity-provider claims."""

import secrets as secrets_module
from typing import Any

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.claim_mapping as claim_mapping
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.lockout.integration_service as lockout_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.schema as server_settings_schema
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


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


def find_or_create_user(
    idp: identity_provider_contracts.IdentityProviderState,
    subject: str,
    userinfo: dict[str, Any],
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
) -> users_schema.UsersRead:
    """Finds an existing user linked to the given identity provider and subject, or creates a new user if allowed.

    This method attempts to:
    1. Find a user by their identity provider (IdP) link using the subject identifier.
    2. If not found, find a user by email and link their account to the IdP,
       but only when the IdP asserts the email is verified (account-takeover
       prevention via the OIDC ``email_verified`` claim) and the local account's
       email is verified too.
    3. If still not found and auto-creation is enabled, create a new user from the IdP information.

    Args:
        idp (identity_provider_contracts.IdentityProviderState): The identity provider instance.
        subject (str): The unique subject identifier from the IdP.
        userinfo (Dict[str, Any]): User information/claims from the IdP.
        password_hasher (credentials_integration.PasswordHasher): The password hasher instance.
        db (Session): Database session.

    Returns:
        users_schema.UsersRead: The found or newly created user instance.

    Raises:
        domain error: If an existing account matches the email but the IdP
            did not assert a verified email or the account's email is not verified (403), or if user creation is
            disabled for the identity provider and no existing user is found.
    """
    # Try to find existing user by IdP link
    link = identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id(idp.id, subject, db)

    if link:
        # Fetch the linked user through the CRUD layer so we work with
        # the UsersRead schema rather than reaching into the ORM
        # relationship (link.users) and crossing the module boundary.
        user = users_integration.get_user(link.user_id, db)
        if user is None:
            raise core_exceptions.NotFoundError("User not found")
        # Update last login timestamp
        identity_provider_links_integration.update_user_identity_provider_last_login(link.user_id, idp.id, db)

        # Update user info if sync is enabled
        if idp.sync_user_info:
            user = update_user_from_idp(user, idp, userinfo, db)
        return user

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

    if email:
        user = users_integration.get_user_by_email(email, db)
        if user:
            if not claim_mapping.is_email_verified(userinfo):
                logger.warning(
                    "Refusing to link IdP <name> to existing account <username_log_id>: "
                    "provider did not assert a verified email",
                    extra=core_logger.context(
                        name=idp.name, username_log_id=lockout_integration.username_log_identifier(user.username)
                    ),
                )
                raise core_exceptions.PermissionDeniedError(
                    "Cannot link this identity provider to an existing "
                    "account because the provider did not verify the "
                    "email address."
                )

            # An unverified local address can be claimed by anyone who set it on their own account, so
            # the IdP's assertion proves nothing about who owns this account.
            if not user.email_verified:
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

            # Link existing account to IdP
            identity_provider_links_integration.create_user_identity_provider(user.id, idp.id, subject, db)

            logger.info(
                "Linked existing user <username_log_id> to IdP <name>",
                extra=core_logger.context(
                    username_log_id=lockout_integration.username_log_identifier(user.username), name=idp.name
                ),
            )

            # Update user info if sync is enabled
            if idp.sync_user_info:
                user = update_user_from_idp(user, idp, userinfo, db)
            return user

    # Create new user if auto-creation is enabled
    if not idp.auto_create_users:
        logger.warning(
            "SSO sign-in refused: account creation is disabled for IdP <name>", extra=core_logger.context(name=idp.name)
        )
        raise core_exceptions.PermissionDeniedError("User account creation is disabled for this identity provider")

    user = create_user_from_idp(
        idp, subject, mapped_data, password_hasher, db, email_verified=claim_mapping.is_email_verified(userinfo)
    )

    return user


def create_user_from_idp(
    idp: identity_provider_contracts.IdentityProviderState,
    subject: str,
    mapped_data: dict[str, Any],
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
    *,
    email_verified: bool,
) -> users_schema.UsersRead:
    """Creates a new user in the database based on identity provider (IdP) information.

    This method generates a unique username, creates a user with mapped data from the IdP
    using the existing CRUD layer, and links the user to the IdP subject. SSO accounts get
    no local password credential — ``create_signup_user`` is called with
    ``persist_credential=False`` so no row is written to ``users_local_credentials`` and
    ``has_local_password`` correctly reports ``False``. The user's email is verified only when the
    IdP asserted it as verified.

    Args:
        idp (identity_provider_contracts.IdentityProviderState): The identity provider instance.
        subject (str): The unique subject identifier from the IdP.
        mapped_data (Dict[str, Any]): User data mapped from the IdP (e.g., username, email, name).
        password_hasher (credentials_integration.PasswordHasher): The password hasher instance.
        db (Session): The database session.
        email_verified (bool): Whether the IdP asserted the email as verified.

    Returns:
        users_schema.UsersRead: The newly created user instance.

    Raises:
        SsoSignInRefusedError: If the IdP did not share an email address; every account needs a real one.
        domain error: If user creation fails (e.g., duplicate username/email).
    """
    email = mapped_data.get("email")
    if not email:
        raise SsoSignInRefusedError(
            f"{idp.name} did not share an email address, so no account can be created",
            login_error="sso_email_missing",
        )

    # Generate a random password solely to satisfy the required
    # UsersSignup.password field. It is never validated, hashed, or
    # stored because the user is created with persist_credential=False
    # (SSO accounts have no local credential row).
    random_password = password_hasher.generate_password(length=16)

    # Ensure username is unique
    base_username = mapped_data.get("username", f"user_{subject[:8]}")
    username = base_username
    while users_integration.get_user_by_username(username, db):
        # secrets.randbelow is a CSPRNG; generate a 6-digit suffix
        username = f"{base_username}_{secrets_module.randbelow(900000) + 100000}"

    # Create user signup schema
    user_signup = users_schema.UsersSignup(
        username=username,
        email=email,
        city=mapped_data.get("city"),
        birthdate=mapped_data.get("birthdate"),
        name=mapped_data.get("name", username),
        password=random_password,
        preferred_language=users_schema.Language.ENGLISH,
        gender=users_schema.Gender.UNSPECIFIED,
        units=server_settings_schema.Units.METRIC,
        height=mapped_data.get("height"),
        max_heart_rate=mapped_data.get("max_heart_rate"),
        first_day_of_week=users_schema.WeekDay.MONDAY,
        currency=server_settings_schema.Currency.EURO,
    )

    server_settings = server_settings_integration.get_server_settings(db)

    created_user = users_integration.create_sso_user(user_signup, server_settings, db, email_verified=email_verified)

    # Create the IdP link
    identity_provider_links_integration.create_user_identity_provider(created_user.id, idp.id, subject, db)

    logger.info(
        "Created new user <username_log_id> from IdP <name>",
        extra=core_logger.context(
            username_log_id=lockout_integration.username_log_identifier(created_user.username), name=idp.name
        ),
    )

    return created_user


def update_user_from_idp(
    user: users_schema.UsersRead,
    idp: identity_provider_contracts.IdentityProviderState,
    userinfo: dict[str, Any],
    db: Session,
) -> users_schema.UsersRead:
    """Updates the user's information based on claims received from an identity provider (IdP).

    This method syncs user profile information from the IdP to the local user account when
    IdP sync is enabled. It performs the following steps:
    1. Maps claims from IdP userinfo to standard user fields (email, name)
    2. Validates email changes - skips an email the IdP did not verify, and one already in use by another user
    3. Logs the conflict when the new email is already in use
    4. Builds an updated copy of the user schema with the changed fields
    5. Delegates persistence to the CRUD layer (edit_user)

    Args:
        user (users_schema.UsersRead): The user schema instance to update.
        idp (identity_provider_contracts.IdentityProviderState): The identity provider instance with user_mapping
            config.
        userinfo (Dict[str, Any]): The user information claims received from the IdP.
        db (Session): The SQLAlchemy database session.

    Returns:
        users_schema.UsersRead: The updated user schema instance from database.
    """
    mapped_data = claim_mapping.map_user_claims(idp, userinfo)

    # Build updates
    updates = {}

    # Check email - verify not already in use. An email the IdP did not verify is never copied onto
    # the account, since it carries the account's own verified flag with it.
    if "email" in mapped_data and mapped_data["email"] != user.email and claim_mapping.is_email_verified(userinfo):
        existing_user = users_integration.get_user_by_email(mapped_data["email"], db)
        if existing_user and existing_user.id != user.id:
            logger.warning(
                "Cannot sync email from IdP <name>: it is already in use by another user",
                extra=core_logger.context(name=idp.name),
            )
        else:
            logger.debug(
                "Syncing email for user <username_log_id> from IdP <name>",
                extra=core_logger.context(
                    username_log_id=lockout_integration.username_log_identifier(user.username), name=idp.name
                ),
            )
            updates["email"] = mapped_data["email"].strip()

    # Check name
    if "name" in mapped_data and mapped_data["name"] != user.name:
        logger.debug(
            "Syncing name for user <username_log_id> from IdP <name>: <name_2> -> <value_4>",
            extra=core_logger.context(
                username_log_id=lockout_integration.username_log_identifier(user.username),
                name=idp.name,
                name_2=user.name,
                value_4=mapped_data["name"],
            ),
        )
        updates["name"] = mapped_data["name"].strip()

    # Only call CRUD if there are updates
    if updates:
        logger.info(
            "Applying updates to user <username_log_id>: <updated_fields>",
            extra=core_logger.context(
                username_log_id=lockout_integration.username_log_identifier(user.username),
                updated_fields=sorted(updates),
            ),
        )
        updated_user = user.model_copy(update=updates)
        user = users_integration.edit_user(user.id, users_schema.UsersEdit.from_read(updated_user), db, if_match="*")
        db.commit()

    return user
