"""Application logic for users.

Decides who may change what on an account, orchestrates the account lifecycle across
the packages that hang rows off a user, and owns the commit for the unit it runs.
Profile photo storage is :mod:`modules.users.users.photo_service`; what other modules
may consume lives in :mod:`modules.users.users.integration_service`.
"""

from collections.abc import Collection
from datetime import date as datetime_date
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import core.timezone as core_timezone
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

if TYPE_CHECKING:
    import modules.auth.identity_service as auth_identity_service

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


def search_public_users(username: str, db: Session) -> list[users_schema.UserPublicRead]:
    """Return the active users whose username contains the search term, as public projections.

    Args:
        username: The partial username to search for.
        db: Database session.

    Returns:
        The matching users, at most ``USER_SEARCH_LIMIT``.
    """
    matches = users_crud.search_active_users_by_username(username, users_constants.USER_SEARCH_LIMIT, db)
    return [users_schema.UserPublicRead.model_validate(user) for user in matches]


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
    identity_service: "auth_identity_service.IdentityService",
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
        identity_service: Identity service that answers the authentication status.
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
    idp_counts = identity_service.get_identity_link_counts_for_users(user_ids)
    mfa_enabled_map = identity_service.get_mfa_enabled_for_users(user_ids)

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


def _stage_default_data(user_id: int, identity_service: "auth_identity_service.IdentityService", db: Session) -> None:
    """Stage the rows every new account starts with.

    Args:
        user_id: ID of the new user.
        identity_service: Identity service that stages the auth-owned MFA row.
        db: Database session.
    """
    user_integrations_integration.create_integrations(user_id, db)
    users_privacy_settings_integration.create_privacy_settings(user_id, db)
    health_targets_integration.create_health_targets(user_id, db)
    users_default_gear_integration.create_default_gear(user_id, db)
    identity_service.initialize_user_mfa(user_id)


def create_user(
    user: users_schema.UsersCreate,
    identity_service: "auth_identity_service.IdentityService",
    db: Session,
) -> users_schema.UsersRead:
    """Create a user as an administrator, with their password and default data.

    Args:
        user: User creation data with a plain text password.
        identity_service: Identity service that hashes and stores the password.
        db: Database session.

    Returns:
        The created user.

    Raises:
        ConflictError: If the username or email is already taken.
        HTTPException: If the password fails the configured policy.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    access_type = users_schema.normalize_access_type(user.access_type)
    hashed_password = identity_service.validate_and_hash_password_for_user(server_settings, access_type, user.password)

    fields = user.model_dump(exclude={"password", "access_type", "mfa_enabled"})
    fields.update(username=user.username.lower(), email=user.email.lower(), access_type=access_type)
    try:
        created = users_crud.create_user(fields, db)
    except core_exceptions.ConflictError:
        db.rollback()
        raise

    identity_service.set_local_password_hash(created.id, hashed_password)
    _stage_default_data(created.id, identity_service, db)
    db.commit()
    logger.info("User created", extra=core_logger.context(user_id=created.id))
    return created


def create_signup_user(
    user: users_schema.UsersSignup,
    server_settings: server_settings_schema.ServerSettingsRead,
    identity_service: "auth_identity_service.IdentityService",
    db: Session,
    persist_credential: bool = True,
) -> users_schema.UsersRead:
    """Create a user through sign-up or SSO, with their default data.

    The account's state follows the server's sign-up policy: it starts inactive when email
    verification or admin approval is required.

    Args:
        user: User sign-up data.
        server_settings: Server config for sign-up requirements.
        identity_service: Identity service that hashes and stores the password.
        db: Database session.
        persist_credential: When True, validate the supplied password and store its hash.
            SSO-created accounts pass False so they get no local credential and stay SSO-only.

    Returns:
        The created user.

    Raises:
        ConflictError: If the username or email is already taken.
        HTTPException: If the password fails the configured policy.
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
        email_verified=not (needs_verification or needs_approval),
        pending_admin_approval=needs_approval,
    )

    hashed_password: str | None = None
    if persist_credential:
        hashed_password = identity_service.validate_and_hash_password_for_user(
            server_settings, users_schema.UserAccessType.REGULAR.value, user.password
        )

    try:
        created = users_crud.create_user(fields, db)
    except core_exceptions.ConflictError as err:
        db.rollback()
        # Abstract message to reduce information leakage.
        raise core_exceptions.ConflictError("Unable to create user.") from err

    if hashed_password is not None:
        identity_service.set_local_password_hash(created.id, hashed_password)
    _stage_default_data(created.id, identity_service, db)
    db.commit()
    logger.info("User signed up", extra=core_logger.context(user_id=created.id))
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
        logger.warning(
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
    identity_service: "auth_identity_service.IdentityService",
    db: Session,
    *,
    if_match: str,
) -> users_schema.UsersRead:
    """Edit a user as an administrator, commit, and add their authentication status.

    A change of email, access type or active flag signs the edited user out everywhere, so a
    demoted, deactivated or re-addressed account does not keep working sessions. An administrator
    editing their own account stays signed in.

    Args:
        user_id: ID of the user to update.
        user: The user data to apply.
        actor_id: ID of the administrator making the edit.
        identity_service: Identity service that answers the authentication status and ends sessions.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated user, with its identity provider count and MFA status.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If the username or email is already taken.
        PreconditionFailedError: If the user changed since the client read them.
    """
    existing = require_user(user_id, db)
    with core_etag.refuse_stale_write(
        db, "user", lambda: users_crud.get_user_by_id(user_id, db) is not None, "User not found"
    ):
        try:
            updated = stage_user_edit(user_id, user, db, if_match=if_match)
        except core_exceptions.ConflictError:
            db.rollback()
            raise
        db.commit()
    logger.info("User edited by an administrator", extra=core_logger.context(user_id=user_id))

    if user_id != actor_id and _edit_ends_sessions(existing, updated):
        identity_service.delete_all_user_sessions(user_id)

    updated.external_auth_count = identity_service.get_identity_link_counts_for_users([updated.id]).get(updated.id, 0)
    updated.mfa_enabled = identity_service.get_mfa_enabled_for_users([updated.id]).get(updated.id, False)
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


def approve_user(user_id: int, identity_service: "auth_identity_service.IdentityService", db: Session) -> None:
    """Approve a pending user by activating them, and commit with the notice that tells them.

    Args:
        user_id: ID of the user to approve.
        identity_service: Identity service that commits the approval together with the notice email.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
        InvalidInputError: If the user's email is not verified.
    """
    if not require_user(user_id, db).email_verified:
        logger.warning("Refused to approve a user with an unverified email", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.InvalidInputError("User email is not verified")

    users_crud.update_user(user_id, {"pending_admin_approval": False, "active": True}, db)
    notified = identity_service.request_sign_up_approved_email(user_id, commit=db.commit)
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


def require_deletable_user(user_id: int, db: Session) -> None:
    """Require a user to exist and not be the only active administrator.

    Args:
        user_id: ID of the user to be deleted.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If the user is the only administrator.
    """
    _refuse_to_remove_last_admin(require_user(user_id, db), "deleted", db)


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
