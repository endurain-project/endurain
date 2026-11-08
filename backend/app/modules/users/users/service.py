"""Application logic for users.

Decides who may change what on an account, orchestrates the account lifecycle across
the packages that hang rows off a user, and owns the commit for the unit it runs.
Profile photo storage is :mod:`modules.users.users.photo_service`; what other modules
may consume lives in :mod:`modules.users.users.integration_service`.
"""

from collections.abc import Collection
from datetime import UTC, datetime
from datetime import date as datetime_date

import jasil.audit as jasil_audit
from pydantic import BaseModel
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import core.timezone as core_timezone
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.password_reset_tokens.integration_service as password_reset_tokens_integration
import modules.auth.schema as auth_schema
import modules.auth.sign_up_tokens.integration_service as sign_up_tokens_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.schema as server_settings_schema
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users_default_gear.integration_service as users_default_gear_integration
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration

logger = core_logger.get_logger(__name__)


def require_user(user_id: int, db: Session) -> users_schema.UserRead:
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


def require_active_user(user: users_schema.UserRead) -> None:
    """Require a user to be active.

    Args:
        user: The user to check.

    Raises:
        PermissionDeniedError: If the user is not active.
    """
    if not user.active:
        logger.warning("Refused an inactive user", extra=core_logger.context(user_id=user.id))
        raise core_exceptions.PermissionDeniedError("Inactive user")


def require_admin_users(db: Session) -> list[users_schema.UserRead]:
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


def _is_publicly_visible(user: users_schema.UserRead) -> bool:
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


def list_public_users(
    page: core_pagination.PageParams,
    db: Session,
    *,
    username: str | None = None,
    username_contains: str | None = None,
) -> users_schema.UserPublicPage:
    """Return one page of the active, discoverable users, optionally narrowed by username.

    Users who are inactive, await approval or switched off "Let others find me in search" are not listed.

    Args:
        page: The window of matches to return.
        db: Database session.
        username: If set, keeps only the user with this exact username.
        username_contains: If set, keeps only users whose username contains it.

    Returns:
        The page of matching users' public projections.
    """
    hidden = users_privacy_settings_integration.list_undiscoverable_user_ids(db)
    matches = users_crud.get_users_with_pagination(
        db,
        page.page_number,
        page.num_records,
        active=True,
        pending_approval=False,
        username=username,
        username_contains=username_contains,
        exclude_user_ids=hidden,
    )
    total = users_crud.get_users_number(
        db,
        active=True,
        pending_approval=False,
        username=username,
        username_contains=username_contains,
        exclude_user_ids=hidden,
    )
    return users_schema.UserPublicPage.build(
        [users_schema.UserPublicRead.model_validate(user) for user in matches],
        total,
        page.page_number,
        page.num_records,
    )


def require_user_by_email(email: str, db: Session) -> users_schema.UserRead:
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


def _set_pending_email_changes(users: Collection[users_schema.UserRead], db: Session) -> None:
    """Set each user's unconfirmed email change, in one query for all of them.

    Args:
        users: The users to fill in.
        db: Database session.
    """
    pending = sign_up_tokens_integration.get_pending_email_changes([user.id for user in users], db)
    for user in users:
        change = pending.get(user.id)
        user.pending_email = change.email if change else None
        user.pending_email_expires_at = change.expires_at if change else None


def require_user_with_pending_email(user_id: int, db: Session) -> users_schema.UserRead:
    """Return a user by id with their unconfirmed email change, who must exist.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The user, with ``pending_email`` and ``pending_email_expires_at`` set when a change awaits confirmation.

    Raises:
        NotFoundError: If the user does not exist.
    """
    user = require_user(user_id, db)
    _set_pending_email_changes([user], db)
    return user


def list_users(
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    active: bool | None = None,
    email_verified: bool | None = None,
    pending_approval: bool | None = None,
    external_auth: bool | None = None,
    username: str | None = None,
    username_contains: str | None = None,
) -> core_pagination.Page[users_schema.UserRead]:
    """List a page of users with their authentication status.

    Args:
        db: Database session.
        page_number: 1-based page number.
        num_records: Records per page.
        active: If set, keeps only users whose active flag equals it.
        email_verified: If set, keeps only users whose email verification flag equals it.
        pending_approval: If set, keeps only users whose pending-approval flag equals it.
        external_auth: If set, keeps only users who do (True) or do not (False) have a linked identity provider.
        username: If set, keeps only the user with this exact username.
        username_contains: If set, keeps only users whose username contains it.

    Returns:
        The page of users and the total matching the filters.
    """
    linked_user_ids = identity_provider_links_integration.select_linked_user_ids()
    total = users_crud.get_users_number(
        db,
        active=active,
        email_verified=email_verified,
        pending_approval=pending_approval,
        username=username,
        username_contains=username_contains,
        external_auth=external_auth,
        linked_user_ids=linked_user_ids,
    )
    users = users_crud.get_users_with_pagination(
        db,
        page_number,
        num_records,
        active=active,
        email_verified=email_verified,
        pending_approval=pending_approval,
        username=username,
        username_contains=username_contains,
        external_auth=external_auth,
        linked_user_ids=linked_user_ids,
    )

    user_ids = [user.id for user in users]
    idp_counts = identity_provider_links_integration.get_identity_link_counts_for_users(user_ids, db)
    mfa_enabled_map = mfa_integration.get_mfa_enabled_for_users(user_ids, db)
    _set_pending_email_changes(users, db)

    records: list[users_schema.UserRead] = []
    for user in users:
        idp_count = idp_counts.get(user.id, 0)
        user.external_auth_count = idp_count
        user.mfa_enabled = mfa_enabled_map.get(user.id, False)

        records.append(user)

    return core_pagination.Page[users_schema.UserRead].build(records, total, page_number, num_records)


def _stage_default_data(user_id: int, db: Session) -> None:
    """Stage the rows every new account starts with.

    Args:
        user_id: ID of the new user.
        db: Database session.
    """
    user_integrations_integration.create_integrations(user_id, db)
    users_privacy_settings_integration.create_privacy_settings(user_id, db)
    users_contributor_registry.lifecycle_hooks().stage_new_user(user_id, db)
    users_default_gear_integration.create_default_gear(user_id, db)
    mfa_integration.create_users_mfa_row(user_id, db)


def _stage_user_create_audit(
    created: users_schema.UserRead, access_type: str, method: users_audit_actions.UserCreateMethod, db: Session
) -> None:
    """Stage the audit row of a new account in the transaction that commits it.

    Args:
        created: The staged user.
        access_type: The access tier the account was created with.
        method: How the account is being created.
        db: Database session.
    """
    jasil_audit.stage(
        db,
        users_audit_actions.USER_CREATE,
        target_type="user",
        target_id=str(created.id),
        target_owner_id=str(created.id),
        details=users_audit_actions.UserCreateDetails(access_type=access_type, method=method),
    )


def _stage_user(
    user: users_schema.UserCreate, method: users_audit_actions.UserCreateMethod, db: Session
) -> users_schema.UserRead:
    """Stage a user with their password and default data (flushed, not committed).

    Args:
        user: User creation data with a plain text password.
        method: How the account is being created, for its audit row.
        db: Database session.

    Returns:
        The staged user.

    Raises:
        ConflictError: If the username or email is already taken.
        PasswordPolicyError: If the password fails the configured policy.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    access_type = users_schema.normalize_access_type(user.access_type)
    hashed_password = credentials_integration.validate_and_hash_password_for_user(
        server_settings, access_type, user.password, db, username=user.username, email=user.email
    )

    fields = user.model_dump(exclude={"password", "access_type", "mfa_enabled"})
    fields.update(username=user.username.lower(), email=user.email.lower(), access_type=access_type)
    if not user.active:
        fields["deactivated_at"] = datetime.now(UTC)
    created = users_crud.create_user(fields, db)

    # An administrator knows the password they created an account with, so its owner must choose a new one at the
    # first sign-in; the first administrator and every other creation chose their own.
    credentials_integration.set_local_password_hash(
        created.id, hashed_password, db, change_required=method == users_audit_actions.UserCreateMethod.ADMIN
    )
    _stage_default_data(created.id, db)
    _stage_user_create_audit(created, access_type, method, db)
    return created


def create_user(
    user: users_schema.UserCreate,
    step_up: auth_schema.StepUpVerification | None,
    actor_id: int,
    session_id: str,
    step_up_store: account_security_integration.StepUpStore,
    db: Session,
) -> users_schema.UserRead:
    """Create a user as an administrator, with their password and default data.

    An administrator account needs the creating administrator's own step-up verification, so a stolen access
    token cannot mint one. It is the creating administrator's credentials that are checked, not the new user's.

    Args:
        user: User creation data with a plain text password.
        step_up: The administrator's step-up verification; verified as empty credentials when missing.
        actor_id: ID of the administrator creating the user.
        session_id: The administrator's session.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        The created user.

    Raises:
        StepUpFailedError: If the new user is an administrator and the step-up fails.
        ConflictError: If the username or email is already taken.
        PasswordPolicyError: If the password fails the configured policy.
    """
    if users_schema.normalize_access_type(user.access_type) == users_schema.UserAccessType.ADMIN.value:
        account_security_integration.verify_step_up(
            step_up or auth_schema.StepUpVerification(),
            actor_id,
            session_id,
            identity_providers_constants.StepUpAction.ADMIN_USER_CREATE,
            step_up_store,
            db,
        )
    try:
        created = _stage_user(user, users_audit_actions.UserCreateMethod.ADMIN, db)
    except core_exceptions.ConflictError:
        db.rollback()
        raise

    db.commit()
    logger.info("User created", extra=core_logger.context(user_id=created.id))
    return created


def stage_first_admin(admin: users_schema.FirstAdminCreate, db: Session) -> users_schema.UserRead:
    """Stage the first administrator of a fresh installation (flushed, not committed).

    The account is an active administrator with a verified address, whatever the caller sent. The advisory lock
    is held until the caller's transaction ends, and the zero-user check runs under it, so concurrent
    callers cannot both create a user.

    Args:
        admin: The administrator's name, username, email and plain text password.
        db: Database session.

    Returns:
        The staged administrator.

    Raises:
        ConflictError: If a user already exists, or the username or email is already taken.
        PasswordPolicyError: If the password fails the administrator policy.
    """
    users_crud.lock_first_admin_creation(db)
    if users_crud.any_user_exists(db):
        raise core_exceptions.ConflictError("An account already exists")

    return _stage_user(
        users_schema.UserCreate(
            name=admin.name,
            username=admin.username,
            email=admin.email,
            password=admin.password,
            access_type=users_schema.UserAccessType.ADMIN,
            active=True,
            email_verified=True,
            pending_admin_approval=False,
        ),
        users_audit_actions.UserCreateMethod.ONBOARDING,
        db,
    )


def _stage_signup_user(
    profile: users_schema.UserBase,
    password: str | None,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
    *,
    email_verified: bool,
    method: users_audit_actions.UserCreateMethod,
) -> users_schema.UserRead:
    """Stage a user through sign-up or SSO, with their default data.

    The account's units and currency are the server's defaults. Its state follows the server's sign-up
    policy: it starts inactive when admin approval is required, or when email verification is required and
    the address is not proven yet. Whether the email is verified does not follow the policy: it records
    whether the address was proven, because an unproven address marked verified could be pre-claimed and
    receive its owner's later SSO sign-in.

    Args:
        profile: The account's profile.
        password: Plain text password, or ``None`` to store no local credential.
        server_settings: Server config for sign-up requirements and default units and currency.
        db: Database session.
        email_verified: Whether the address is already proven.
        method: How the account is being created, for its audit row.

    Returns:
        The created user.

    Raises:
        ConflictError: If the username or email is already taken.
        PasswordPolicyError: If the password fails the configured policy.
    """
    needs_verification = server_settings.signup_require_email_verification and not email_verified
    needs_approval = server_settings.signup_require_admin_approval

    fields = profile.model_dump(exclude={"username", "email"})
    fields.update(
        username=profile.username.lower(),
        email=profile.email.lower(),
        units=server_settings.units,
        currency=server_settings.currency,
        access_type=users_schema.UserAccessType.REGULAR.value,
        active=not (needs_verification or needs_approval),
        email_verified=email_verified,
        pending_admin_approval=needs_approval,
    )

    hashed_password: str | None = None
    if password is not None:
        hashed_password = credentials_integration.validate_and_hash_password_for_user(
            server_settings,
            users_schema.UserAccessType.REGULAR.value,
            password,
            db,
            username=profile.username,
            email=profile.email,
        )

    created = users_crud.create_user(fields, db)

    if hashed_password is not None:
        credentials_integration.set_local_password_hash(created.id, hashed_password, db, change_required=False)
    _stage_default_data(created.id, db)
    _stage_user_create_audit(created, users_schema.UserAccessType.REGULAR.value, method, db)
    return created


def stage_signup_user(
    user: users_schema.UserSignup,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
) -> users_schema.UserRead:
    """Stage a user through sign-up with their default data (flushed, not committed).

    The profile starts from the defaults with the chosen language. The address is not proven yet: the
    verification link proves it. A local credential is stored only when the sign-up carries a password.
    """
    profile = users_schema.UserBase(
        name=user.name,
        username=user.username,
        email=user.email,
        preferred_language=user.preferred_language,
    )
    try:
        created = _stage_signup_user(
            profile,
            user.password,
            server_settings,
            db,
            email_verified=False,
            method=users_audit_actions.UserCreateMethod.SIGN_UP,
        )
    except core_exceptions.ConflictError as err:
        # Abstract message to reduce information leakage.
        raise core_exceptions.ConflictError("Unable to create user.") from err
    return created


def create_sso_user(
    profile: users_schema.UserBase,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
    *,
    email_verified: bool,
) -> users_schema.UserRead:
    """Stage an SSO-only user with the defaults used by regular sign-up.

    Args:
        profile: The account's profile mapped from the provider. No local credential is stored.
        server_settings: Server config for sign-up requirements.
        db: Database session.
        email_verified: Whether the provider asserted the address as verified.

    Returns:
        The staged user.

    Raises:
        ConflictError: If the username or email is already taken.
    """
    try:
        created = _stage_signup_user(
            profile,
            None,
            server_settings,
            db,
            email_verified=email_verified,
            method=users_audit_actions.UserCreateMethod.IDENTITY_PROVIDER,
        )
    except core_exceptions.ConflictError as err:
        raise core_exceptions.ConflictError("Unable to create user.") from err
    logger.info("SSO user staged", extra=core_logger.context(user_id=created.id))
    return created


def _recalculate_bmi_if_height_changed(
    before: users_schema.UserRead, after: users_schema.UserRead, db: Session
) -> None:
    """Stage a BMI recalculation of the user's manual weight records when their height changed.

    Args:
        before: The user before the edit.
        after: The user after the edit.
        db: Database session.
    """
    if before.height != after.height:
        users_contributor_registry.lifecycle_hooks().stage_height_change(
            after.id, float(after.height) if after.height is not None else None, db
        )


def _refuse_to_remove_last_admin(user: users_schema.UserRead, action: str, db: Session) -> None:
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


def stage_user_edit(user_id: int, user: users_schema.UserEdit, db: Session, *, if_match: str) -> users_schema.UserRead:
    """Stage an administrative edit of a user.

    Intended for admin endpoints that legitimately set fields like ``access_type``, ``active``
    or ``pending_admin_approval``. Self-service updates go through :func:`stage_profile_edit`,
    whose allow-list prevents privilege escalation through mass assignment. A changed email also
    voids the user's unused password-reset tokens, so this covers every writer of this edit,
    such as the identity-provider sync.

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

    changes = user.model_dump(exclude_unset=True, exclude={"mfa_enabled"})
    changes["username"] = user.username.lower()
    changes["email"] = user.email.lower()

    updated = users_crud.update_user(user_id, changes, db, if_match=if_match)
    if existing.email != updated.email:
        # A reset link mailed to the old address must not set a password once the recovery address moved.
        password_reset_tokens_integration.revoke_unused_tokens(user_id, db)
    if existing.active and not updated.active:
        # Verifying an email activates the account, so a link issued before the deactivation must not work.
        sign_up_tokens_integration.revoke_pending_tokens(user_id, db)
    _recalculate_bmi_if_height_changed(existing, updated, db)
    return updated


def changed_field_names(before: BaseModel, after: BaseModel, names: Collection[str]) -> list[str]:
    """Name the fields, among those a write submitted, whose stored value differs after it.

    Args:
        before: The record before the write.
        after: The record after the write.
        names: The field names the write submitted.

    Returns:
        The submitted names whose value changed, in submission order.
    """
    return [name for name in names if getattr(before, name) != getattr(after, name)]


def _stage_user_update_audit(
    before: users_schema.UserRead, after: users_schema.UserRead, requested: users_schema.UserEdit, db: Session
) -> None:
    """Stage the audit row of an administrative edit, naming the fields whose stored value changed.

    Nothing is staged when the edit changed no field. A requested email that waits for confirmation is not
    yet a change, since the stored address is kept.

    Args:
        before: The user before the edit.
        after: The user after the edit.
        requested: The edit as the administrator submitted it.
        db: Database session.
    """
    submitted = requested.model_dump(exclude_unset=True, exclude={"mfa_enabled"})
    changed_fields = changed_field_names(before, after, submitted)
    if changed_fields:
        jasil_audit.stage(
            db,
            users_audit_actions.USER_UPDATE,
            target_type="user",
            target_id=str(before.id),
            target_owner_id=str(before.id),
            details=users_audit_actions.UserUpdateDetails(changed_fields=changed_fields),
        )


def _edit_ends_sessions(before: users_schema.UserRead, requested: users_schema.UserEdit) -> bool:
    """Whether an administrative edit changes who the user is or what they may do.

    Args:
        before: The user before the edit.
        requested: The edit as the administrator submitted it.

    Returns:
        True when the requested email, access type or active flag differs from the stored one, so
        sessions issued under the old values must not outlive the edit.
    """
    return (
        before.email != requested.email.lower()
        or users_schema.normalize_access_type(before.access_type)
        != users_schema.normalize_access_type(requested.access_type)
        or before.active != requested.active
    )


def _stage_edit_with_email_change(
    existing: users_schema.UserRead, user: users_schema.UserEdit, db: Session, *, if_match: str
) -> tuple[users_schema.UserRead, bool]:
    """Stage an edit that changes the user's email, applying the address now or only requesting it.

    An address the administrator marks verified is applied now. Any other address is requested: the
    edit keeps the stored ``email`` and ``email_verified`` and a confirmation link goes to the new
    address, which replaces the stored one once confirmed. Without outgoing mail nothing can be
    confirmed, so the address is applied now, unverified. An address applied now also voids the user's
    unused verification tokens, and, through :func:`stage_user_edit`, their unused password-reset tokens.

    Args:
        existing: The user as stored.
        user: The edit, whose email differs from the stored one.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The edited user and whether the address was applied without being verifiable.

    Raises:
        ConflictError: If another account uses the address, or the edit would demote or deactivate the
            only administrator.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    if not user.email_verified:
        requested = user.email.lower()
        require_email_available(existing.id, requested, db)
        # Staged before the edit, so an edit that also deactivates the user revokes the new link with the old ones.
        if sign_up_tokens_integration.request_email_change(existing.id, requested, existing.email, db):
            kept = user.model_copy(update={"email": existing.email, "email_verified": existing.email_verified})
            return stage_user_edit(existing.id, kept, db, if_match=if_match), False

    updated = stage_user_edit(existing.id, user, db, if_match=if_match)
    # A link issued for the old address or a pending one must not confirm over the address just applied.
    sign_up_tokens_integration.revoke_pending_tokens(existing.id, db)
    return updated, not user.email_verified


def edit_user(
    user_id: int,
    user: users_schema.UserEdit,
    step_up: auth_schema.StepUpVerification | None,
    actor_id: int,
    session_id: str,
    step_up_store: account_security_integration.StepUpStore,
    db: Session,
    *,
    if_match: str,
) -> users_schema.UserRead:
    """Edit a user as an administrator, commit, and add their authentication status.

    A change of email, access type or active flag needs the administrator's own step-up verification, so a
    stolen access token cannot hand an account over. It signs the edited user out everywhere, so a
    demoted, deactivated or re-addressed account does not keep working sessions. An administrator
    editing their own account stays signed in. A changed email that the administrator does not mark
    verified is requested, not applied: the user keeps the stored address, a confirmation link is queued
    for the new one in the same transaction as the edit, and the response carries it as ``pending_email``.
    A changed email marked verified is applied at once, and one that cannot be confirmed because outgoing
    email is not configured is applied unverified.

    Args:
        user_id: ID of the user to update.
        user: The user data to apply.
        step_up: The administrator's step-up verification; verified as empty credentials when missing.
        actor_id: ID of the administrator making the edit.
        session_id: The administrator's session.
        step_up_store: Step-up lockout store.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated user, with its pending email change, identity provider count and MFA status.

    Raises:
        PermissionDeniedError: If the administrator changes their own email, which needs their account settings.
        StepUpFailedError: If the edit changes the email, access type or active flag and the step-up fails.
        NotFoundError: If the user does not exist.
        ConflictError: If the username or email is already taken.
        PreconditionFailedError: If the user changed since the client read them.
    """
    existing = require_user(user_id, db)
    email_changed = existing.email != user.email.lower()
    if email_changed:
        require_other_user(user_id, actor_id, "change your email")
    if _edit_ends_sessions(existing, user):
        account_security_integration.verify_step_up(
            step_up or auth_schema.StepUpVerification(),
            actor_id,
            session_id,
            identity_providers_constants.StepUpAction.ADMIN_USER_EDIT,
            step_up_store,
            db,
        )
    applied_unverified = False
    with core_etag.refuse_stale_write(
        db, "user", lambda: users_crud.get_user_by_id(user_id, db) is not None, "User not found"
    ):
        try:
            if email_changed:
                updated, applied_unverified = _stage_edit_with_email_change(existing, user, db, if_match=if_match)
            else:
                updated = stage_user_edit(user_id, user, db, if_match=if_match)
        except core_exceptions.ConflictError:
            db.rollback()
            raise
        _stage_user_update_audit(existing, updated, user, db)
        if user_id != actor_id and _edit_ends_sessions(existing, user):
            # Revoked in the edit's own transaction, so a user whose role or address changed cannot keep a session.
            account_security_integration.delete_all_user_sessions(user_id, db)
        db.commit()
    if applied_unverified:
        logger.warning(
            "Email changed but cannot be verified: outgoing email is not configured",
            extra=core_logger.context(user_id=user_id),
        )
    logger.info("User edited by an administrator", extra=core_logger.context(user_id=user_id))

    _set_pending_email_changes([updated], db)
    updated.external_auth_count = identity_provider_links_integration.get_identity_link_counts_for_users(
        [updated.id], db
    ).get(updated.id, 0)
    updated.mfa_enabled = mfa_integration.get_mfa_enabled_for_users([updated.id], db).get(updated.id, False)
    return updated


def stage_profile_edit(
    user_id: int, profile: users_schema.ProfileUpdate, db: Session, *, if_match: str
) -> users_schema.UserRead:
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

    A changed address also voids the user's unused verification and password-reset tokens. Does nothing
    when the address is the one the user already has, so re-submitting it does not cost them their
    verified status.

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
    # A link issued for the old address or a pending one must not confirm over the address just applied.
    sign_up_tokens_integration.revoke_pending_tokens(user_id, db)
    password_reset_tokens_integration.revoke_unused_tokens(user_id, db)
    return True


def require_email_available(user_id: int, email: str, db: Session) -> None:
    """Refuse an address that another account uses.

    A write to the user's own row trips the unique index on its own; this is for a path that stores the
    address elsewhere first, such as a pending email change.

    Args:
        user_id: ID of the user who wants the address.
        email: The address, in any case.
        db: Database session.

    Raises:
        ConflictError: If another account uses the address.
    """
    holder = users_crud.get_user_by_email(email.lower(), db)
    if holder is not None and holder.id != user_id:
        raise core_exceptions.ConflictError("Email is already in use.")


def stage_confirmed_email_change(user_id: int, email: str, db: Session) -> None:
    """Stage a confirmed email address for a user, mark it verified and void their unused password-reset tokens.

    Args:
        user_id: ID of the user whose email changes.
        email: The confirmed email address.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If another account uses the email.
    """
    normalized = email.lower()
    require_email_available(user_id, normalized, db)
    users_crud.update_user(user_id, {"email": normalized, "email_verified": True}, db)
    password_reset_tokens_integration.revoke_unused_tokens(user_id, db)
    jasil_audit.stage(
        db,
        users_audit_actions.USER_EMAIL_CHANGE,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
    )


def stage_synced_email_change(user_id: int, email: str, db: Session) -> None:
    """Stage an email address that a sign-in provider verified as the user's, and tell the previous address.

    The address is applied as a confirmed one: marked verified, with the user's unused password-reset tokens
    voided and the change audited, and the previous address is sent the notice a confirmed change sends. The
    caller owns the transaction.

    Args:
        user_id: ID of the user whose email changes.
        email: The address the provider verified.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If another account uses the email.
    """
    previous_email = require_user(user_id, db).email
    stage_confirmed_email_change(user_id, email, db)
    sign_up_tokens_integration.stage_email_changed_notice(user_id, email.lower(), previous_email, db)


def approve_user(user_id: int, db: Session) -> None:
    """Approve a user awaiting approval, staging the notice event in the same transaction.

    A user who is not awaiting approval, is deactivated or is queued for deletion is refused and left as it was,
    so an approval never reactivates an account or cancels a deletion.

    A verified email is required only while the sign-up policy requires verification: with approval
    alone no verification email is sent, so the user could never meet it.

    Args:
        user_id: ID of the user to approve.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
        InvalidInputError: If verification is required and the user's email is not verified.
        ConflictError: If the user is not awaiting approval, is deactivated or is queued for deletion.
    """
    user = require_user(user_id, db)
    if (
        server_settings_integration.get_server_settings(db).signup_require_email_verification
        and not user.email_verified
    ):
        logger.debug("Refused to approve a user with an unverified email", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.InvalidInputError("User email is not verified")

    if not users_crud.approve_pending_user(user_id, db):
        logger.debug("Refused to approve a user not awaiting approval", extra=core_logger.context(user_id=user_id))
        jasil_audit.record_detached(
            users_audit_actions.USER_APPROVE,
            outcome=jasil_audit.Outcome.DENIED,
            target_type="user",
            target_id=str(user_id),
            target_owner_id=str(user_id),
        )
        raise core_exceptions.ConflictError("User is not awaiting approval")
    notified = sign_up_tokens_integration.request_sign_up_approved_email(user_id, db)
    jasil_audit.stage(
        db, users_audit_actions.USER_APPROVE, target_type="user", target_id=str(user_id), target_owner_id=str(user_id)
    )
    db.commit()
    logger.info("User approved", extra=core_logger.context(user_id=user_id, notified=notified))


def is_deactivated(user_id: int, db: Session) -> bool:
    """Tell whether an administrator or a deletion request deactivated a user.

    Args:
        user_id: ID of the user.
        db: Database session.

    Returns:
        True for a deactivated account, False for an active one and for a sign-up awaiting verification
        or approval.

    Raises:
        NotFoundError: If the user does not exist.
    """
    return users_crud.is_deactivated(user_id, db)


def stage_email_verification(
    user_id: int,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
) -> None:
    """Stage a user's email as verified, activating a sign-up unless admin approval is pending.

    A deactivated account is only marked verified: a link must not undo an administrator's decision.

    Args:
        user_id: ID of the user to verify.
        server_settings: Server config that decides whether approval is still required.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
    """
    changes: dict[str, bool] = {"email_verified": True}
    if not server_settings.signup_require_admin_approval and not users_crud.is_deactivated(user_id, db):
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


def change_user_password(
    user_id: int,
    attributes: users_schema.UserAdminEditPassword,
    actor_id: int,
    session_id: str,
    step_up_store: account_security_integration.StepUpStore,
    db: Session,
) -> None:
    """Change another user's password as an administrator after their step-up, ending the user's sessions.

    Args:
        user_id: ID of the user whose password changes.
        attributes: The new plaintext password, which must satisfy the configured policy, and the
            administrator's step-up verification.
        actor_id: ID of the administrator making the change.
        session_id: The administrator's session.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        PermissionDeniedError: If the administrator targets their own account.
        StepUpFailedError: If the administrator's step-up verification fails.
        NotFoundError: If the user does not exist.
        PasswordPolicyError: If the password fails the configured policy.
    """
    require_other_user(user_id, actor_id, "change your password")
    account_security_integration.verify_step_up(
        attributes.step_up,
        actor_id,
        session_id,
        identity_providers_constants.StepUpAction.ADMIN_CREDENTIAL_RESET,
        step_up_store,
        db,
    )
    account_security_integration.change_managed_user_password(user_id, attributes.password, db)
    db.commit()
    logger.info("Password changed by an administrator", extra=core_logger.context(user_id=user_id))


def reset_user_mfa(
    user_id: int,
    attributes: auth_schema.StepUpRequest,
    actor_id: int,
    session_id: str,
    step_up_store: account_security_integration.StepUpStore,
    db: Session,
) -> None:
    """Reset another user's MFA as an administrator after their step-up, ending all of the user's sessions.

    Args:
        user_id: ID of the user whose MFA is reset.
        attributes: The administrator's step-up verification.
        actor_id: ID of the administrator making the change.
        session_id: The administrator's session.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        PermissionDeniedError: If the administrator targets their own account.
        StepUpFailedError: If the administrator's step-up verification fails.
        NotFoundError: If the user does not exist.
        InvalidInputError: If MFA is not enabled for the user.
    """
    require_other_user(user_id, actor_id, "turn off two-factor authentication")
    account_security_integration.verify_step_up(
        attributes.step_up,
        actor_id,
        session_id,
        identity_providers_constants.StepUpAction.ADMIN_MFA_RESET,
        step_up_store,
        db,
    )
    account_security_integration.reset_managed_user_mfa(user_id, db)
    db.commit()
    logger.info("MFA reset by an administrator", extra=core_logger.context(user_id=user_id))


def require_user_password_change(
    user_id: int,
    attributes: auth_schema.StepUpRequest,
    actor_id: int,
    session_id: str,
    step_up_store: account_security_integration.StepUpStore,
    db: Session,
) -> None:
    """Require another user to choose a new password at their next sign-in, after the administrator's step-up.

    Args:
        user_id: ID of the user who must change their password.
        attributes: The administrator's step-up verification.
        actor_id: ID of the administrator making the change.
        session_id: The administrator's session.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        PermissionDeniedError: If the administrator targets their own account.
        StepUpFailedError: If the administrator's step-up verification fails.
        NotFoundError: If the user does not exist.
        ConflictError: If the user has no local password.
    """
    require_other_user(user_id, actor_id, "change your password")
    account_security_integration.verify_step_up(
        attributes.step_up,
        actor_id,
        session_id,
        identity_providers_constants.StepUpAction.ADMIN_CREDENTIAL_CHANGE_REQUIRE,
        step_up_store,
        db,
    )
    account_security_integration.require_managed_user_password_change(user_id, db)
    db.commit()
    logger.info("Password change required by an administrator", extra=core_logger.context(user_id=user_id))


def unlink_identity_provider(
    user_id: int,
    idp_id: int,
    actor_id: int,
    session_id: str,
    step_up: auth_schema.StepUpVerification,
    step_up_store: account_security_integration.StepUpStore,
    db: Session,
) -> None:
    """Unlink an identity provider from another user as an administrator after their step-up.

    Args:
        user_id: ID of the user to unlink the provider from.
        idp_id: ID of the identity provider.
        actor_id: ID of the administrator making the change.
        session_id: The administrator's session.
        step_up: The administrator's step-up verification.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        PermissionDeniedError: If the administrator targets their own account.
        StepUpFailedError: If the administrator's step-up verification fails.
        NotFoundError: If the provider or the link does not exist.
        InvalidInputError: If unlinking would remove the user's last way to sign in.
    """
    require_other_user(user_id, actor_id, "unlink an identity provider")
    account_security_integration.verify_step_up(
        step_up, actor_id, session_id, identity_providers_constants.StepUpAction.ADMIN_IDP_UNLINK, step_up_store, db
    )
    account_security_integration.admin_delete_identity_provider_link(user_id, idp_id, db)
    db.commit()
    logger.info(
        "Identity provider unlinked by an administrator",
        extra=core_logger.context(user_id=user_id, idp_id=idp_id),
    )
