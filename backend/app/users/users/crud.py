"""CRUD operations for user management.

WARNING: Functions prefixed with `_` (underscore) are private and must not
be imported outside this module. They are internal implementation details.
Use only the public functions exported by users.users.__init__ for external
consumption.
"""

import datetime
import posixpath
from typing import TYPE_CHECKING, Literal, overload
from urllib.parse import unquote

if TYPE_CHECKING:
    import auth.identity_service as auth_identity_service

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

import auth.password_policy as auth_password_policy
import core.decorators as core_decorators
import health.health_weight.utils as health_weight_utils
import server_settings.schema as server_settings_schema
import server_settings.utils as server_settings_utils
import users.users.models as users_models
import users.users.schema as users_schema
import users.users.utils as users_utils

# Private internal helpers


@overload
def _transform_users(users: users_models.Users) -> users_schema.UsersRead: ...


@overload
def _transform_users(users: list[users_models.Users]) -> list[users_schema.UsersRead]: ...


def _transform_users(
    users: users_models.Users | list[users_models.Users],
) -> users_schema.UsersRead | list[users_schema.UsersRead]:
    """
    Transform a user or list of users to a Pydantic schema.

    Args:
        users: The user ORM instance or list of instances.

    Returns:
        The user(s) as a schema.
    """
    if isinstance(users, list):
        return [users_schema.UsersRead.model_validate(user) for user in users]
    return users_schema.UsersRead.model_validate(users)


def _get_user_model_by_id_or_404(user_id: int, db: Session) -> users_models.Users:
    """
    Retrieve a mapped Users ORM row by ID or raise 404.

    This is a **private internal helper**. Do not import or call from
    outside this module. Use public CRUD functions instead (e.g.,
    ``get_user_by_id()``, ``edit_user()``, etc.).

    Args:
        user_id: User ID to search for.
        db: SQLAlchemy database session.

    Returns:
        Mapped ``Users`` ORM instance.

    Raises:
        HTTPException: 404 if user not found.
    """
    stmt = select(users_models.Users).where(users_models.Users.id == user_id)
    db_userss = db.execute(stmt).scalar_one_or_none()

    if db_userss is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return db_userss


def _persist_user_edits(
    db_users: users_models.Users,
    height_before: int | None,
    max_heart_rate_before: int | None,
    birthdate_before: datetime.date | None,
    recalculate_bmi_on_height_change: bool,
    db: Session,
) -> users_schema.UsersRead:
    """
    Commit pending user edits and refresh derived data.

    Bundles the blocking portion of an edit into a single unit so
    callers can offload it with ``run_in_threadpool`` and keep the API
    event loop responsive. The commit/refresh, the bulk BMI
    recalculation, the HR zone recomputation, and the ``mfa_enabled``
    lazy-load triggered while serializing are all synchronous
    SQLAlchemy calls.

    Args:
        db_users: Mapped ``Users`` row carrying pending in-memory
            changes that have not yet been committed.
        height_before: User height prior to the edit, used to detect a
            change that requires recalculating BMI.
        max_heart_rate_before: Max heart rate prior to the edit, used
            to detect a change that requires recomputing HR zones.
        birthdate_before: Birthdate prior to the edit; it feeds the
            age-derived max-HR fallback, so a change can also require
            recomputing HR zones.
        recalculate_bmi_on_height_change: When ``True`` and the height
            actually changed, recompute BMI for every weight entry.
        db: SQLAlchemy database session.

    Returns:
        The persisted user serialized as ``users_schema.UsersRead``.
    """
    db.commit()
    db.refresh(db_users)

    if recalculate_bmi_on_height_change and height_before != db_users.height:
        # Update the user's health data
        health_weight_utils.calculate_bmi_all_user_entries(db_users.id, db)

    # HR zones are pre-computed and stored per stream at import time
    # from the user's resolved max heart rate. Recompute them when the
    # max heart rate or birthdate changes so previously imported
    # activities show up-to-date zones (issue #776). Imported lazily to
    # avoid a users <-> activity_streams import cycle; the recompute
    # logs and swallows its own errors so it can't fail the edit.
    if max_heart_rate_before != db_users.max_heart_rate or birthdate_before != db_users.birthdate:
        # Lazy import to avoid a users <-> activity_streams import cycle
        import activities.activity_streams.crud as activity_streams_crud

        activity_streams_crud.recompute_hr_zone_percentages_for_user(db_users.id, db)

    return _transform_users(db_users)


def _apply_user_photo_update(
    user_id: int,
    photo_path: str | None,
    db: Session,
) -> None:
    """
    Persist a user's photo path change.

    Bundles the blocking DB work (lookup, update, commit, refresh)
    so callers can offload it with ``run_in_threadpool`` and keep
    the API event loop responsive.

    Args:
        user_id: ID of the user whose photo path is updated.
        photo_path: New photo path, or ``None`` to clear it.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    db_users = _get_user_model_by_id_or_404(user_id, db)
    db_users.photo_path = photo_path
    db.commit()
    db.refresh(db_users)


def _delete_user_row(user_id: int, db: Session) -> None:
    """
    Delete a user row from the database.

    Bundles the blocking DB work (lookup, delete, commit) so callers
    can offload it with ``run_in_threadpool`` and keep the API event
    loop responsive.

    Args:
        user_id: ID of the user to delete.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    db_users = _get_user_model_by_id_or_404(user_id, db)
    db.delete(db_users)
    db.commit()


# Public CRUD functions


@core_decorators.handle_db_errors
def get_all_users(db: Session) -> list[users_schema.UsersRead]:
    """
    Retrieve all users from the database.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of all user schemas.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(users_models.Users).options(selectinload(users_models.Users.auth_mfa))
    users: list[users_models.Users] = list(db.execute(stmt).scalars().all())

    return _transform_users(users)


@core_decorators.handle_db_errors
def get_users_number(
    db: Session,
    show_inactive: bool | None = True,
    show_email_unverified: bool | None = True,
    show_pending_approval: bool | None = True,
) -> int:
    """
    Count users matching the optional list filters.

    Args:
        db: SQLAlchemy database session.
        show_inactive: If False, excludes inactive users.
            Defaults to True.
        show_email_unverified: If False, excludes users with
            unverified emails. Defaults to True.
        show_pending_approval: If False, excludes users pending
            admin approval. Defaults to True.

    Returns:
        Number of users matching the filters.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(func.count(users_models.Users.id))

    if show_inactive is False:
        stmt = stmt.where(users_models.Users.active.is_(True))
    if show_email_unverified is False:
        stmt = stmt.where(users_models.Users.email_verified.is_(True))
    if show_pending_approval is False:
        stmt = stmt.where(users_models.Users.pending_admin_approval.is_(False))

    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_users_with_pagination(
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    show_inactive: bool | None = True,
    show_email_unverified: bool | None = True,
    show_pending_approval: bool | None = True,
) -> list[users_schema.UsersRead]:
    """
    Retrieve a paginated list of users with optional filtering.

    Args:
        db (Session): Database session for executing queries.
        page_number (int | None): The page number for pagination (1-indexed).
            If None, pagination is not applied. Defaults to None.
        num_records (int | None): The number of records per page.
            If None, pagination is not applied. Defaults to None.
        show_inactive (bool | None): If False, excludes inactive users.
            Defaults to True (includes inactive users).
        show_email_unverified (bool | None): If False, excludes users with
            unverified emails. Defaults to True (includes email unverified
            users).
        show_pending_approval (bool | None): If False, excludes users pending
            admin approval. Defaults to True (includes pending approval users).

    Returns:
        list[users_schema.UsersRead]: A list of User schemas matching the specified
            criteria, ordered by username. Returns an empty list if no users
            match the filters.
    """
    stmt = select(users_models.Users).options(selectinload(users_models.Users.auth_mfa))

    if show_inactive is False:
        stmt = stmt.where(users_models.Users.active.is_(True))
    if show_email_unverified is False:
        stmt = stmt.where(users_models.Users.email_verified.is_(True))
    if show_pending_approval is False:
        stmt = stmt.where(users_models.Users.pending_admin_approval.is_(False))

    stmt = stmt.order_by(users_models.Users.username)

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    users: list[users_models.Users] = list(db.execute(stmt).scalars().all())
    return _transform_users(users)


@overload
def get_user_by_username(
    username: str,
    db: Session,
    contains: Literal[False] = False,
) -> users_schema.UsersRead | None: ...


@overload
def get_user_by_username(
    username: str,
    db: Session,
    contains: Literal[True],
) -> list[users_schema.UsersRead]: ...


@core_decorators.handle_db_errors
def get_user_by_username(
    username: str, db: Session, contains: bool = False
) -> list[users_schema.UsersRead] | users_schema.UsersRead | None:
    """
    Retrieve user by username.

    Args:
        username: Username to search for.
        db: SQLAlchemy database session.
        contains: If True, performs partial match search and returns
                  list of matching users. If False, performs exact
                  match and returns single user or None.

    Returns:
        If contains=False: User schema if found, None otherwise.
        If contains=True: List of user schemas matching the search.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    # Decode and normalize search term (needed for both exact and partial matches)
    normalized_username = unquote(username).replace("+", " ").lower()

    if contains:
        # Escape LIKE special characters to prevent SQL injection
        escaped_username = normalized_username.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")

        # Query users with username containing the search term
        stmt = (
            select(users_models.Users)
            .options(selectinload(users_models.Users.auth_mfa))
            .where(func.lower(users_models.Users.username).like(f"%{escaped_username}%", escape="\\"))
        )
        users: list[users_models.Users] = list(db.execute(stmt).scalars().all())
        return _transform_users(users)
    else:
        # Exact match - no LIKE escaping needed
        stmt = select(users_models.Users).where(users_models.Users.username == normalized_username)
        user = db.execute(stmt).scalar_one_or_none()
        return _transform_users(user) if user else None


@core_decorators.handle_db_errors
def get_user_by_email(email: str, db: Session) -> users_schema.UsersRead | None:
    """
    Retrieve user by email address.

    Args:
        email: Email address to search for (case-insensitive).
        db: SQLAlchemy database session.

    Returns:
        User schema if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(users_models.Users).where(users_models.Users.email == email.lower())
    user = db.execute(stmt).scalar_one_or_none()
    return _transform_users(user) if user else None


@core_decorators.handle_db_errors
def get_user_by_id(user_id: int, db: Session, public_check: bool = False) -> users_schema.UsersRead | None:
    """
    Retrieve user by ID.

    Args:
        user_id: User ID to search for.
        db: SQLAlchemy database session.
        public_check: If True, only returns user when public sharing
                      is enabled in server settings.

    Returns:
        User schema if found (and public sharing enabled if
        public_check=True), None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    if public_check:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Return None if public sharable links are disabled
        if not server_settings.public_shareable_links or not server_settings.public_shareable_links_user_info:
            return None

    stmt = select(users_models.Users).where(users_models.Users.id == user_id)
    user = db.execute(stmt).scalar_one_or_none()
    return _transform_users(user) if user else None


@core_decorators.handle_db_errors
def get_users_admin(db: Session) -> list[users_schema.UsersRead]:
    """
    Retrieve all admin users from the database.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of admin user schemas.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = (
        select(users_models.Users)
        .options(selectinload(users_models.Users.auth_mfa))
        .where(users_models.Users.access_type == users_schema.UserAccessType.ADMIN.value)
    )
    users: list[users_models.Users] = list(db.execute(stmt).scalars().all())
    return _transform_users(users)


@core_decorators.handle_db_errors
def create_user(
    user: users_schema.UsersCreate,
    identity_service: "auth_identity_service.IdentityService",
    db: Session,
) -> users_schema.UsersRead:
    """
    Create a new user with hashed password.

    Args:
        user: User creation data with plain text password.
        identity_service: Identity service dependency.
        db: SQLAlchemy database session.

    Returns:
        Created user schema with hashed password.

    Raises:
        HTTPException: 409 if email/username already exists.
        HTTPException: 500 if database error occurs.
    """
    try:
        user.username = user.username.lower()
        user.email = user.email.lower()

        # Get server settings to determine password policy
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Normalize access_type to string value
        access_type_value = users_schema.normalize_access_type(user.access_type)

        # Hash the password with configurable policy and length
        hashed_password = auth_password_policy.validate_and_hash_for_user(
            identity_service,
            server_settings,
            access_type_value,
            user.password,
        )

        # Create a new user
        db_users = users_models.Users(
            **user.model_dump(exclude={"password", "access_type", "mfa_enabled"}),
            access_type=access_type_value,
        )

        # Add the user to the database
        db.add(db_users)
        db.commit()
        db.refresh(db_users)

        # Persist the password hash in the auth-owned credential table.
        identity_service.set_local_password_hash(db_users.id, hashed_password)

        # Return user
        return _transform_users(db_users)
    except HTTPException:
        # Rollback the transaction
        db.rollback()
        raise
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Duplicate entry error. Check if email and username are unique"),
        ) from integrity_error


@core_decorators.handle_db_errors
def create_signup_user(
    user: users_schema.UsersSignup,
    server_settings: server_settings_schema.ServerSettingsRead,
    identity_service: "auth_identity_service.IdentityService",
    db: Session,
    persist_credential: bool = True,
) -> users_schema.UsersRead:
    """
    Create a new user during signup process.

    Args:
        user: User signup data.
        server_settings: Server config for signup requirements.
        identity_service: Identity service dependency.
        db: SQLAlchemy database session.
        persist_credential: When ``True`` (default), validate the supplied
            password and store its hash in the auth-owned credential table.
            SSO-created accounts pass ``False`` so they get no local
            credential row and remain SSO-only (``has_local_password`` then
            correctly reports ``False``).

    Returns:
        Created user schema.

    Raises:
        HTTPException: 409 if email/username already exists. Abstract message
            to reduce information leakage.
        HTTPException: 500 if database error occurs.
    """
    try:
        # Determine user status based on server settings
        active = True
        email_verified = False
        pending_admin_approval = False

        if server_settings.signup_require_email_verification:
            email_verified = False
            active = False  # Inactive until email verified

        if server_settings.signup_require_admin_approval:
            pending_admin_approval = True
            active = False  # Inactive until approved

        # If both email verification and admin approval are disabled, user is immediately active
        if not server_settings.signup_require_email_verification and not server_settings.signup_require_admin_approval:
            active = True
            email_verified = True

        # Create a new user
        db_users = users_models.Users(
            **user.model_dump(
                exclude={
                    "username",
                    "email",
                    "access_type",
                    "active",
                    "email_verified",
                    "pending_admin_approval",
                    "password",
                }
            ),
            username=user.username.lower(),
            email=user.email.lower(),
            access_type=users_schema.UserAccessType.REGULAR.value,
            active=active,
            email_verified=email_verified,
            pending_admin_approval=pending_admin_approval,
        )

        # Hash the signup password with the configured policy. SSO-created
        # accounts opt out (persist_credential=False) so the supplied
        # placeholder password is never validated or hashed.
        hashed_password: str | None = None
        if persist_credential:
            hashed_password = auth_password_policy.validate_and_hash_for_user(
                identity_service,
                server_settings,
                users_schema.UserAccessType.REGULAR.value,
                user.password,
            )

        # Add the user to the database
        db.add(db_users)
        db.commit()
        db.refresh(db_users)

        # Persist the password hash in the auth-owned credential table. Skipped
        # for SSO-only accounts so that ``has_local_password`` stays a true row
        # existence check.
        if hashed_password is not None:
            identity_service.set_local_password_hash(db_users.id, hashed_password)

        # Return user
        return _transform_users(db_users)
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Unable to create user."),
        ) from integrity_error


@core_decorators.handle_db_errors
async def edit_user(user_id: int, user: users_schema.UsersRead, db: Session) -> users_schema.UsersRead:
    """
    Update an existing user's information.

    Note:
        This dynamic-assignment helper is intended for **admin**
        endpoints that legitimately need to set fields like
        ``access_type``, ``active``, or ``pending_admin_approval``.
        Self-service profile updates MUST NOT call this — use
        :func:`edit_profile_user` instead, which enforces an
        explicit allow-list and prevents privilege escalation
        through mass assignment.

    Args:
        user_id: ID of user to update.
        user: User data to update with.
        db: SQLAlchemy database session.

    Returns:
        users_schema.UsersRead

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 409 if email/username conflict.
        HTTPException: 500 if database error occurs.
    """
    try:
        # Fetch the user off the event loop (blocking DB read).
        db_users = await run_in_threadpool(_get_user_model_by_id_or_404, user_id, db)

        height_before = db_users.height
        max_heart_rate_before = db_users.max_heart_rate
        birthdate_before = db_users.birthdate

        # Check if the photo_path is being updated
        if user.photo_path:
            # Delete the user photo in the filesystem
            await users_utils.delete_user_photo_filesystem(db_users.id)

        user.username = user.username.lower()

        # Dictionary of the fields to update if they are not None
        user_data = user.model_dump(exclude_unset=True, exclude={"password", "external_auth_count", "mfa_enabled"})
        # Iterate over the fields and update the db_users dynamically
        for key, value in user_data.items():
            # Skip read-only computed properties exposed by the read schema
            # (e.g. mfa_enabled, derived from the users_mfa table with no
            # setter). They appear in UsersRead for output but must never be
            # mass-assigned, otherwise setattr raises AttributeError.
            class_attr = getattr(type(db_users), key, None)
            if isinstance(class_attr, property) and class_attr.fset is None:
                continue
            setattr(db_users, key, value)

        # Persist the changes off the event loop. The commit/refresh, the
        # bulk BMI recalculation, and the ``mfa_enabled`` lazy-load triggered
        # while serializing are blocking SQLAlchemy calls, so run them in a
        # worker thread to keep the API event loop responsive.
        updated_user = await run_in_threadpool(
            _persist_user_edits,
            db_users,
            height_before,
            max_heart_rate_before,
            birthdate_before,
            True,
            db,
        )

        if db_users.photo_path is None:
            # Delete the user photo in the filesystem
            await users_utils.delete_user_photo_filesystem(db_users.id)

        return updated_user
    except HTTPException:
        raise
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Duplicate entry error. Check if email and username are unique"),
        ) from integrity_error


# Allow-list of fields a user is permitted to change on their own
# account via the self-service profile endpoint. Any field not in
# this set is silently dropped before persistence to prevent
# privilege escalation through mass assignment (e.g. setting
# ``access_type`` to ``admin`` on the caller's own row).
PROFILE_SELF_SERVICE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "username",
        "email",
        "city",
        "birthdate",
        "preferred_language",
        "gender",
        "units",
        "height",
        "max_heart_rate",
        "first_day_of_week",
        "currency",
        "photo_path",
    }
)


@core_decorators.handle_db_errors
async def edit_profile_user(
    user_id: int,
    profile: users_schema.ProfileUpdate,
    db: Session,
) -> users_schema.UsersRead:
    """
    Apply a self-service profile update with strict allow-listing.

    Only fields enumerated in :data:`PROFILE_SELF_SERVICE_FIELDS`
    are persisted. Administrative attributes such as
    ``access_type``, ``active``, ``mfa_enabled``, ``mfa_secret``,
    ``email_verified``, and ``pending_admin_approval`` are NEVER
    written from this path — even if a malicious payload smuggles
    them through validation, they cannot reach the database here.

    Args:
        user_id: ID of the authenticated user invoking the update.
        profile: Validated self-service profile payload.
        db: SQLAlchemy database session.

    Returns:
        The updated user schema (``users_schema.UsersRead``).

    Raises:
        HTTPException: 404 if the user does not exist, 409 on
            email/username uniqueness conflict, 500 on DB errors.
    """
    try:
        # Fetch the user off the event loop (blocking DB read).
        db_users = await run_in_threadpool(_get_user_model_by_id_or_404, user_id, db)

        height_before = db_users.height
        max_heart_rate_before = db_users.max_heart_rate
        birthdate_before = db_users.birthdate
        previous_photo_path = db_users.photo_path

        # exclude_unset means only fields the caller actually sent
        # are considered. The intersection with the allow-list is
        # the second line of defence.
        provided = profile.model_dump(exclude_unset=True)
        updates = {k: v for k, v in provided.items() if k in PROFILE_SELF_SERVICE_FIELDS}

        if "username" in updates and isinstance(updates["username"], str):
            updates["username"] = updates["username"].lower()
        if "email" in updates and isinstance(updates["email"], str):
            updates["email"] = updates["email"].lower()

        # Constrain photo_path to the user's own image directory to
        # prevent path-traversal or pointing at another user's
        # photo via the profile update. A naive ``startswith``
        # against the raw payload is bypassable with traversal
        # sequences (e.g. ``data/user_images/5./../3.jpg`` passes
        # the prefix check for user 5 but resolves to user 3's
        # avatar — a stored IDOR). We therefore:
        #   1. reject any payload containing a ``..`` segment or
        #      a backslash (Windows-style separator) outright,
        #   2. normalise the path through ``posixpath.normpath``
        #      so ``./`` and redundant slashes collapse,
        #   3. then enforce the per-user prefix on the NORMALISED
        #      value.
        # A tampered path is silently dropped rather than 400'd —
        # the legitimate upload flow always sets this correctly,
        # so the only callers who reach the drop branch are
        # malicious or buggy clients and surfacing the error
        # would just be an oracle.
        if "photo_path" in updates:
            new_path = updates["photo_path"]
            if new_path is not None:
                expected_prefix = f"data/user_images/{user_id}."
                has_traversal = "\\" in new_path or any(part == ".." for part in new_path.split("/"))
                normalised = posixpath.normpath(new_path)
                if has_traversal or not normalised.startswith(expected_prefix):
                    updates.pop("photo_path")
                else:
                    # Persist the normalised form so downstream
                    # consumers always see a canonical path.
                    updates["photo_path"] = normalised

        # If the photo_path is being cleared or replaced, delete
        # the on-disk file (matches legacy edit_user behaviour).
        photo_changed = "photo_path" in updates and updates["photo_path"] != previous_photo_path
        if photo_changed and previous_photo_path:
            await users_utils.delete_user_photo_filesystem(db_users.id)

        for key, value in updates.items():
            setattr(db_users, key, value)

        # Persist the changes off the event loop. The commit/refresh, the
        # bulk BMI recalculation, and the ``mfa_enabled`` lazy-load triggered
        # while serializing are blocking SQLAlchemy calls, so run them in a
        # worker thread to keep the API event loop responsive.
        return await run_in_threadpool(
            _persist_user_edits,
            db_users,
            height_before,
            max_heart_rate_before,
            birthdate_before,
            "height" in updates,
            db,
        )
    except HTTPException:
        raise
    except IntegrityError as integrity_error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Duplicate entry error. Check if email and username are unique"),
        ) from integrity_error


@core_decorators.handle_db_errors
def approve_user(user_id: int, db: Session) -> None:
    """
    Approve a user by marking them as active.

    Args:
        user_id: ID of user to approve.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 400 if user email not verified.
        HTTPException: 500 if database error occurs.
    """
    # Get the user from the database
    db_users = _get_user_model_by_id_or_404(user_id, db)

    if not db_users.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User email is not verified",
        )

    db_users.pending_admin_approval = False
    db_users.active = True

    # Commit the transaction
    db.commit()
    db.refresh(db_users)


@core_decorators.handle_db_errors
def verify_user_email(
    user_id: int,
    server_settings: server_settings_schema.ServerSettingsRead,
    db: Session,
) -> None:
    """
    Verify user email and conditionally activate account.

    Args:
        user_id: ID of user to verify.
        server_settings: Server config determining activation policy.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 500 if database error occurs.
    """
    # Get the user from the database
    db_users = _get_user_model_by_id_or_404(user_id, db)

    db_users.email_verified = True
    if not server_settings.signup_require_admin_approval:
        db_users.pending_admin_approval = False
        db_users.active = True

    # Commit the transaction
    db.commit()
    db.refresh(db_users)


@core_decorators.handle_db_errors
async def update_user_photo(user_id: int, db: Session, photo_path: str | None = None) -> str | None:
    """
    Update a user's photo path.

    Args:
        user_id: ID of user to update photo for.
        db: SQLAlchemy database session.
        photo_path: New photo path. If None, removes photo.

    Returns:
        The updated photo path, or None if removed.

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 500 if database error occurs.
    """
    # Persist the photo path change off the event loop (blocking sync
    # DB calls), keeping the API event loop responsive.
    await run_in_threadpool(_apply_user_photo_update, user_id, photo_path, db)

    if photo_path:
        # Return the photo path
        return photo_path

    # Delete the user photo in the filesystem
    await users_utils.delete_user_photo_filesystem(user_id)

    return None


@core_decorators.handle_db_errors
async def delete_user(user_id: int, db: Session) -> None:
    """
    Delete a user from the database.

    Args:
        user_id: ID of user to delete.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 if user not found.
        HTTPException: 500 if database error occurs.
    """
    # Delete the user row off the event loop (blocking sync DB calls),
    # keeping the API event loop responsive.
    await run_in_threadpool(_delete_user_row, user_id, db)

    # Delete the user photo in the filesystem
    await users_utils.delete_user_photo_filesystem(user_id)
