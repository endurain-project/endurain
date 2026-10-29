"""Application logic for users.

Decides who may change what on an account, orchestrates the account lifecycle across
the packages that hang rows off a user, and owns the commit for the unit it runs.
Profile photo storage is :mod:`modules.users.users.photo_service`; what other modules
may consume lives in :mod:`modules.users.users.integration_service`.
"""

from collections.abc import Collection
from datetime import date as datetime_date

from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import core.timezone as core_timezone
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.sign_up_tokens.integration_service as sign_up_tokens_integration
import modules.health.health_targets.integration_service as health_targets_integration
import modules.health.health_weight.integration_service as health_weight_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.schema as server_settings_schema
import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users_default_gear.integration_service as users_default_gear_integration
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration

logger = core_logger.get_logger(__name__)


def require_user(user_id: int, db: Session) -> users_schema.UsersRead:
    """Return a user by id, which must exist.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The user.

    Raises:
        NotFoundError: If the user does not exist.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")

    return user


def require_active_user(user: users_schema.UsersRead) -> None:
    """Require a user to be active.

    Args:
        user: The user to check.

    Raises:
        PermissionDeniedError: If the user is not active.
    """
    if not user.active:
        logger.warning("Refused an inactive user", extra=core_logger.context(user_id=user.id))
        raise core_exceptions.PermissionDeniedError("Inactive user")


def require_admin_users(db: Session) -> list[users_schema.UsersRead]:
    """Return every admin user, of which there must be at least one.

    Args:
        db: Database session.

    Returns:
        The admin users.

    Raises:
        NotFoundError: If there are no admin users.
    """
    admins = users_crud.get_users_admin(db)
    if not admins:
        raise core_exceptions.NotFoundError("No admin users found")

    return admins


def _is_publicly_visible(user: users_schema.UsersRead) -> bool:
    """Return whether a signed-in viewer may look this user up at all.

    Args:
        user: The user to check.

    Returns:
        False for an inactive account or one still awaiting approval.
    """
    return user.active and not user.pending_admin_approval


def get_public_profile(user_id: int, db: Session) -> users_schema.UserPublicRead:
    """Return a user's public projection for a signed-in viewer.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The public projection.

    Raises:
        NotFoundError: If the user does not exist, is inactive or still awaits approval, so a viewer
            cannot tell the three apart.
    """
    user = require_user(user_id, db)
    if not _is_publicly_visible(user):
        raise core_exceptions.NotFoundError("User not found")
    return users_schema.UserPublicRead.model_validate(user)


def list_public_profiles(user_ids: Collection[int], db: Session) -> dict[int, users_schema.UserPublicRead]:
    """Return the public projection of several users in one read, keyed by user ID.

    Applies the same visibility rule as :func:`get_public_profile`, but a user who is missing,
    inactive or awaiting approval is left out instead of raising.

    Args:
        user_ids: The users to look up.
        db: Database session.

    Returns:
        The public projection of each visible user, keyed by ID.
    """
    return {
        user.id: users_schema.UserPublicRead.model_validate(user)
        for user in users_crud.get_users_by_ids(user_ids, db)
        if _is_publicly_visible(user)
    }


def get_public_user(user_id: int, db: Session) -> users_schema.UserPublicRead:
    """Return a user's public projection for an unauthenticated viewer, when sharing allows it.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The public projection.

    Raises:
        NotFoundError: If the user does not exist or public user info is not shared, so a viewer
            cannot tell the two apart.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    if not server_settings.public_shareable_links or not server_settings.public_shareable_links_user_info:
        raise core_exceptions.NotFoundError("User not found")

    return get_public_profile(user_id, db)


def require_user_by_username(username: str, db: Session) -> users_schema.UsersRead:
    """Return a user by exact username, who must exist.

    Args:
        username: Username to search for.
        db: Database session.

    Returns:
        The user.

    Raises:
        NotFoundError: If there is no such user.
    """
    user = users_crud.get_user_by_username(username, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")
    return user


def search_public_users(username: str, page: core_pagination.PageParams, db: Session) -> users_schema.UserPublicPage:
    """Return one page of the active users whose username contains the search term, as public projections.

    Args:
        username: The partial username to search for.
        page: The window of matches to return.
        db: Database session.

    Returns:
        The page of matching users.
    """
    matches = users_crud.search_active_users_by_username(
        username, page.num_records, (page.page_number - 1) * page.num_records, db
    )
    total = users_crud.get_users_number(db, show_inactive=False, username=username)
    return users_schema.UserPublicPage.build(
        [users_schema.UserPublicRead.model_validate(user) for user in matches],
        total,
        page.page_number,
        page.num_records,
    )


def require_user_by_email(email: str, db: Session) -> users_schema.UsersRead:
    """Return a user by email address, who must exist.

    Args:
        email: Email address to search for.
        db: Database session.

    Returns:
        The user.

    Raises:
        NotFoundError: If there is no such user.
    """
    user = users_crud.get_user_by_email(email, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")
    return user


def list_users(
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    show_inactive: bool | None = None,
    show_email_unverified: bool | None = None,
    show_pending_approval: bool | None = None,
    show_external_auth: bool | None = None,
    show_local_auth: bool | None = None,
    username: str | None = None,
) -> core_pagination.Page[users_schema.UsersRead]:
    """List a page of users with their authentication status.

    The external/local filters are applied after the page is read, so a page may hold fewer
    records than ``num_records``.

    Args:
        db: Database session.
        page_number: 1-based page number.
        num_records: Records per page.
        show_inactive: If False, excludes inactive users.
        show_email_unverified: If False, excludes users with unverified emails.
        show_pending_approval: If False, excludes users pending admin approval.
        show_external_auth: If False, excludes users with a linked identity provider.
        show_local_auth: If False, excludes users with no linked identity provider.
        username: If set, keeps only users whose username contains it.

    Returns:
        The page of users and the total matching the first three filters and the username.
    """
    total = users_crud.get_users_number(db, show_inactive, show_email_unverified, show_pending_approval, username)
    users = users_crud.get_users_with_pagination(
        db, page_number, num_records, show_inactive, show_email_unverified, show_pending_approval, username
    )

    user_ids = [user.id for user in users]
    idp_counts = identity_provider_links_integration.get_identity_link_counts_for_users(user_ids, db)
    mfa_enabled_map = mfa_integration.get_mfa_enabled_for_users(user_ids, db)

    records: list[users_schema.UsersRead] = []
    for user in users:
        idp_count = idp_counts.get(user.id, 0)
        user.external_auth_count = idp_count
        user.mfa_enabled = mfa_enabled_map.get(user.id, False)

        if idp_count > 0 and show_external_auth is False:
            continue
        if idp_count == 0 and show_local_auth is False:
            continue

        records.append(user)

    return core_pagination.Page.build(records, total, page_number, num_records)


def _stage_default_data(user_id: int, db: Session) -> None:
    """Stage the rows every new account starts with.

    Args:
        user_id: ID of the new user.
        db: Database session.
    """
    user_integrations_integration.create_integrations(user_id, db)
    users_privacy_settings_integration.create_privacy_settings(user_id, db)
    health_targets_integration.create_health_targets(user_id, db)
    users_default_gear_integration.create_default_gear(user_id, db)
    mfa_integration.create_users_mfa_row(user_id, db)


def create_user(
    user: users_schema.UsersCreate,
    db: Session,
) -> users_schema.UsersRead:
    """Create a user as an administrator, with their password and default data.

    Args:
        user: User creation data with a plain text password.
        db: Database session.

    Returns:
        The created user.

    Raises:
        ConflictError: If the username or email is already taken.
        InvalidInputError: If the password fails the configured policy.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    access_type = users_schema.normalize_access_type(user.access_type)
    hashed_password = credentials_integration.validate_and_hash_password_for_user(
        server_settings, access_type, user.password, db
    )

    fields = user.model_dump(exclude={"password", "access_type", "mfa_enabled"})
    fields.update(username=user.username.lower(), email=user.email.lower(), access_type=access_type)
    try:
        created = users_crud.create_user(fields, db)
    except core_exceptions.ConflictError:
        db.rollback()
        raise

    credentials_integration.set_local_password_hash(created.id, hashed_password, db)
    _stage_default_data(created.id, db)
    db.commit()
    logger.info("User created", extra=core_logger.context(user_id=created.id))
    return created


def _stage_signup_user(
    user: users_schema.UsersSignup,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
    *,
    email_verified: bool,
    persist_credential: bool = True,
) -> users_schema.UsersRead:
    """Stage a user through sign-up or SSO, with their default data.

    The account's state follows the server's sign-up policy: it starts inactive when email
    verification or admin approval is required. Whether the email is verified does not follow the
    policy: it records whether the address was proven, because an unproven address marked verified
    could be pre-claimed and receive its owner's later SSO sign-in.

    Args:
        user: User sign-up data.
        server_settings: Server config for sign-up requirements.
        db: Database session.
        email_verified: Whether the address is already proven.
        persist_credential: When True, validate the supplied password and store its hash.
            SSO-created accounts pass False so they get no local credential and stay SSO-only.

    Returns:
        The created user.

    Raises:
        ConflictError: If the username or email is already taken.
        InvalidInputError: If the password fails the configured policy.
    """
    needs_verification = server_settings.signup_require_email_verification
    needs_approval = server_settings.signup_require_admin_approval

    fields = user.model_dump(
        exclude={"username", "email", "access_type", "active", "email_verified", "pending_admin_approval", "password"}
    )
    fields.update(
        username=user.username.lower(),
        email=user.email.lower(),
        access_type=users_schema.UserAccessType.REGULAR.value,
        active=not (needs_verification or needs_approval),
        email_verified=email_verified,
        pending_admin_approval=needs_approval,
    )

    hashed_password: str | None = None
    if persist_credential:
        hashed_password = credentials_integration.validate_and_hash_password_for_user(
            server_settings, users_schema.UserAccessType.REGULAR.value, user.password, db
        )

    created = users_crud.create_user(fields, db)

    if hashed_password is not None:
        credentials_integration.set_local_password_hash(created.id, hashed_password, db)
    _stage_default_data(created.id, db)
    return created


def create_signup_user(
    user: users_schema.UsersSignup,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
    persist_credential: bool = True,
) -> users_schema.UsersRead:
    """Create a user through sign-up or SSO and commit the staged defaults.

    The address is not proven yet: the verification link proves it.
    """
    try:
        created = _stage_signup_user(
            user, server_settings, db, email_verified=False, persist_credential=persist_credential
        )
    except core_exceptions.ConflictError as err:
        db.rollback()
        # Abstract message to reduce information leakage.
        raise core_exceptions.ConflictError("Unable to create user.") from err
    db.commit()
    logger.info("User signed up", extra=core_logger.context(user_id=created.id))
    return created


def create_sso_user(
    user: users_schema.UsersSignup,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
    *,
    email_verified: bool,
) -> users_schema.UsersRead:
    """Stage an SSO-only user with the defaults used by regular sign-up.

    Args:
        user: User sign-up data mapped from the provider.
        server_settings: Server config for sign-up requirements.
        db: Database session.
        email_verified: Whether the provider asserted the address as verified.

    Returns:
        The staged user.

    Raises:
        ConflictError: If the username or email is already taken.
    """
    try:
        created = _stage_signup_user(user, server_settings, db, email_verified=email_verified, persist_credential=False)
    except core_exceptions.ConflictError as err:
        raise core_exceptions.ConflictError("Unable to create user.") from err
    logger.info("SSO user staged", extra=core_logger.context(user_id=created.id))
    return created


def _recalculate_bmi_if_height_changed(
    before: users_schema.UsersRead, after: users_schema.UsersRead, db: Session
) -> None:
    """Stage a BMI recalculation of the user's weight records when their height changed.

    Args:
        before: The user before the edit.
        after: The user after the edit.
        db: Database session.
    """
    if before.height != after.height:
        health_weight_integration.recalculate_bmi_for_user(
            after.id, float(after.height) if after.height is not None else None, db
        )


def _refuse_to_remove_last_admin(user: users_schema.UsersRead, action: str, db: Session) -> None:
    """Refuse a change that would leave the server without an active administrator.

    Args:
        user: The user the change applies to, as stored now.
        action: What is being refused, for the message and the log.
        db: Database session.

    Raises:
        ConflictError: If the user is the only active administrator.
    """
    if not (
        user.active and users_schema.normalize_access_type(user.access_type) == users_schema.UserAccessType.ADMIN.value
    ):
        return

    admin_ids = users_crud.lock_active_admin_ids(db)
    if user.id in admin_ids and len(admin_ids) <= 1:
        logger.debug(
            "Refused to remove the only administrator", extra=core_logger.context(user_id=user.id, action=action)
        )
        raise core_exceptions.ConflictError(f"The only administrator cannot be {action}")


def stage_user_edit(
    user_id: int, user: users_schema.UsersEdit, db: Session, *, if_match: str
) -> users_schema.UsersRead:
    """Stage an administrative edit of a user.

    Intended for admin endpoints that legitimately set fields like ``access_type``, ``active``
    or ``pending_admin_approval``. Self-service updates go through :func:`stage_profile_edit`,
    whose allow-list prevents privilege escalation through mass assignment.

    Args:
        user_id: ID of the user to update.
        user: The user data to apply.
        db: Database session.
        if_match: The ``If-Match`` precondition, or ``*`` to overwrite (a system writer).

    Returns:
        The updated user.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If the username or email is already taken, or the edit would demote or
            deactivate the only administrator.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    existing = require_user(user_id, db)
    if not user.active:
        _refuse_to_remove_last_admin(existing, "deactivated", db)
    if users_schema.normalize_access_type(user.access_type) != users_schema.UserAccessType.ADMIN.value:
        _refuse_to_remove_last_admin(existing, "demoted", db)

    # ``photo_path`` is excluded because the read schema exposes a resolved, signed URL while
    # the column stores a storage key: echoing the read model back would overwrite the key
    # with its own URL. The photo is owned solely by the upload and delete operations.
    changes = user.model_dump(exclude_unset=True, exclude={"mfa_enabled", "photo_path"})
    changes["username"] = user.username.lower()
    changes["email"] = user.email.lower()

    updated = users_crud.update_user(user_id, changes, db, if_match=if_match)
    if existing.active and not updated.active:
        # Verifying an email activates the account, so a link issued before the deactivation must not work.
        sign_up_tokens_integration.revoke_pending_tokens(user_id, db)
    _recalculate_bmi_if_height_changed(existing, updated, db)
    return updated


def _edit_ends_sessions(before: users_schema.UsersRead, after: users_schema.UsersRead) -> bool:
    """Whether an administrative edit changes who the user is or what they may do.

    Args:
        before: The user before the edit.
        after: The user after the edit.

    Returns:
        True when the email, the access type or the active flag changed, so sessions issued
        under the old values must not outlive the edit.
    """
    return (
        before.email != after.email
        or users_schema.normalize_access_type(before.access_type)
        != users_schema.normalize_access_type(after.access_type)
        or before.active != after.active
    )


def edit_user(
    user_id: int,
    user: users_schema.UsersEdit,
    actor_id: int,
    db: Session,
    *,
    if_match: str,
) -> users_schema.UsersRead:
    """Edit a user as an administrator, commit, and add their authentication status.

    A change of email, access type or active flag signs the edited user out everywhere, so a
    demoted, deactivated or re-addressed account does not keep working sessions. An administrator
    editing their own account stays signed in. A changed email that is left unverified queues a
    verification email in the same transaction as the edit.

    Args:
        user_id: ID of the user to update.
        user: The user data to apply.
        actor_id: ID of the administrator making the edit.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated user, with its identity provider count and MFA status.

    Raises:
        PermissionDeniedError: If the administrator changes their own email, which needs step-up.
        NotFoundError: If the user does not exist.
        ConflictError: If the username or email is already taken.
        PreconditionFailedError: If the user changed since the client read them.
    """
    existing = require_user(user_id, db)
    if existing.email != user.email.lower():
        require_other_user(user_id, actor_id, "change your email")
    with core_etag.refuse_stale_write(
        db, "user", lambda: users_crud.get_user_by_id(user_id, db) is not None, "User not found"
    ):
        try:
            updated = stage_user_edit(user_id, user, db, if_match=if_match)
        except core_exceptions.ConflictError:
            db.rollback()
            raise
        verification_queued = True
        if existing.email != updated.email and not updated.email_verified:
            verification_queued = sign_up_tokens_integration.request_email_reverification(user_id, db)
        if user_id != actor_id and _edit_ends_sessions(existing, updated):
            # Revoked in the edit's own transaction, so a user whose role or address changed cannot keep a session.
            account_security_integration.delete_all_user_sessions(user_id, db)
        db.commit()
    if not verification_queued:
        logger.warning(
            "Email changed but cannot be verified: outgoing email is not configured",
            extra=core_logger.context(user_id=user_id),
        )
    logger.info("User edited by an administrator", extra=core_logger.context(user_id=user_id))

    updated.external_auth_count = identity_provider_links_integration.get_identity_link_counts_for_users(
        [updated.id], db
    ).get(updated.id, 0)
    updated.mfa_enabled = mfa_integration.get_mfa_enabled_for_users([updated.id], db).get(updated.id, False)
    return updated


def stage_profile_edit(
    user_id: int, profile: users_schema.ProfileUpdate, db: Session, *, if_match: str
) -> users_schema.UsersRead:
    """Stage a self-service profile update, keeping only the allow-listed fields.

    Administrative attributes such as ``access_type``, ``active``, ``email_verified`` and
    ``pending_admin_approval`` are never written from this path, even if a payload smuggles
    them through validation.

    Args:
        user_id: ID of the authenticated user.
        profile: The validated self-service payload.
        db: Database session.
        if_match: The ``If-Match`` precondition, or ``*`` to overwrite (the profile importer).

    Returns:
        The updated user.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If the username or email is already taken.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    existing = require_user(user_id, db)

    provided = profile.model_dump(exclude_unset=True)
    changes = {key: value for key, value in provided.items() if key in users_constants.PROFILE_SELF_SERVICE_FIELDS}
    if isinstance(changes.get("username"), str):
        changes["username"] = changes["username"].lower()

    updated = users_crud.update_user(user_id, changes, db, if_match=if_match)
    if "height" in changes:
        _recalculate_bmi_if_height_changed(existing, updated, db)
    return updated


def stage_email_change(user_id: int, email: str, db: Session) -> bool:
    """Stage a new email address for a user and mark it unverified.

    Does nothing when the address is the one the user already has, so re-submitting it does not
    cost them their verified status.

    Args:
        user_id: ID of the user whose email changes.
        email: The new email address.
        db: Database session.

    Returns:
        True when the address changed, False when it was already the user's.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If the email is already taken.
    """
    existing = require_user(user_id, db)
    normalized = email.lower()
    if existing.email == normalized:
        return False

    users_crud.update_user(user_id, {"email": normalized, "email_verified": False}, db)
    return True


def approve_user(user_id: int, db: Session) -> None:
    """Approve a pending user, staging the notice event in the same transaction.

    A verified email is required only while the sign-up policy requires verification: with approval
    alone no verification email is sent, so the user could never meet it.

    Args:
        user_id: ID of the user to approve.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
        InvalidInputError: If verification is required and the user's email is not verified.
    """
    user = require_user(user_id, db)
    if (
        server_settings_integration.get_server_settings(db).signup_require_email_verification
        and not user.email_verified
    ):
        logger.debug("Refused to approve a user with an unverified email", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.InvalidInputError("User email is not verified")

    users_crud.update_user(user_id, {"pending_admin_approval": False, "active": True}, db)
    notified = sign_up_tokens_integration.request_sign_up_approved_email(user_id, db)
    db.commit()
    logger.info("User approved", extra=core_logger.context(user_id=user_id, notified=notified))


def stage_email_verification(
    user_id: int,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
) -> None:
    """Stage a user's email as verified, activating them unless admin approval is pending.

    Args:
        user_id: ID of the user to verify.
        server_settings: Server config that decides whether approval is still required.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
    """
    changes: dict[str, bool] = {"email_verified": True}
    if not server_settings.signup_require_admin_approval:
        changes.update(pending_admin_approval=False, active=True)

    users_crud.update_user(user_id, changes, db)


def require_deletable_user(user_id: int, db: Session, *, if_match: str) -> None:
    """Require a user to exist at the version the caller read and not be the only active administrator.

    Args:
        user_id: ID of the user to be deleted.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user does not exist.
        PreconditionFailedError: If the user changed since the client read it.
        ConflictError: If the user is the only administrator.
    """
    user = require_user(user_id, db)
    core_etag.require_if_match(if_match, user.version, "user")
    _refuse_to_remove_last_admin(user, "deleted", db)


def timezone_or_default(timezone: str | None) -> str:
    """Return the given IANA timezone, or the server default when it is unset.

    ``users.timezone`` is nullable: accounts that predate the setting have none, in which case
    the server default is the only answer available.

    Args:
        timezone: An IANA timezone name, or None.

    Returns:
        An IANA timezone name.
    """
    return core_timezone.or_default(timezone)


def resolve_user_timezone(user_id: int, db: Session) -> str:
    """Return the athlete's IANA timezone, falling back to the server's.

    Args:
        user_id: The user whose timezone to resolve.
        db: Database session.

    Returns:
        An IANA timezone name.
    """
    user = users_crud.get_user_by_id(user_id, db)
    return timezone_or_default(user.timezone if user is not None else None)


def user_local_today(user_id: int, db: Session) -> datetime_date:
    """Return today's calendar date in the athlete's own timezone.

    Everything that answers "what did I do *today*?" must use this rather than ``date.today()``
    (the container's zone) or ``datetime.now(UTC).date()``: both put an athlete in UTC+13 a day
    behind for 13 hours out of every 24, and one in UTC-11 a day ahead for 11.

    Args:
        user_id: The user whose "today" to resolve.
        db: Database session.

    Returns:
        The user's current calendar date.
    """
    return core_timezone.today_in(resolve_user_timezone(user_id, db))


def require_other_user(user_id: int, actor_id: int, action: str) -> None:
    """Refuse an administrative action that an administrator aims at their own account.

    The self-service endpoints verify the caller's password and MFA code before the same change, so
    the administrative route must not offer a way around that check.

    Args:
        user_id: ID of the user the action targets.
        actor_id: ID of the administrator making the request.
        action: What the action does, completing "Use your account settings to ...".

    Raises:
        PermissionDeniedError: If the administrator targets their own account.
    """
    if user_id == actor_id:
        logger.warning(
            "Refused an administrative action on the administrator's own account",
            extra=core_logger.context(user_id=user_id, action=action),
        )
        raise core_exceptions.PermissionDeniedError(f"Use your account settings to {action}")


def change_user_password(user_id: int, new_password: str, actor_id: int, db: Session) -> None:
    """Change another user's password as an administrator, ending their sessions.

    Args:
        user_id: ID of the user whose password changes.
        new_password: New plaintext password; it must satisfy the configured policy.
        actor_id: ID of the administrator making the change.
        db: Database session.

    Raises:
        PermissionDeniedError: If the administrator targets their own account.
        NotFoundError: If the user does not exist.
        InvalidInputError: If the password fails the configured policy.
    """
    require_other_user(user_id, actor_id, "change your password")
    account_security_integration.change_managed_user_password(user_id, new_password, db)
    db.commit()
    logger.info("Password changed by an administrator", extra=core_logger.context(user_id=user_id))


def unlink_identity_provider(user_id: int, idp_id: int, actor_id: int, db: Session) -> None:
    """Unlink an identity provider from another user as an administrator.

    Args:
        user_id: ID of the user to unlink the provider from.
        idp_id: ID of the identity provider.
        actor_id: ID of the administrator making the change.
        db: Database session.

    Raises:
        PermissionDeniedError: If the administrator targets their own account.
        NotFoundError: If the provider or the link does not exist.
        InvalidInputError: If unlinking would remove the user's last way to sign in.
    """
    require_other_user(user_id, actor_id, "unlink an identity provider")
    account_security_integration.admin_delete_identity_provider_link(user_id, idp_id, db)
    db.commit()
    logger.info(
        "Identity provider unlinked by an administrator",
        extra=core_logger.context(user_id=user_id, idp_id=idp_id),
    )
