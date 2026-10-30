"""Application logic for the authenticated user's profile.

Assembles the profile from the packages that own its parts, applies the user's own edits and
runs the profile export and import. Authentication concerns (sessions, MFA, identity provider
links) stay behind the auth boundary and are called straight from the router.
"""

from datetime import date
from typing import TYPE_CHECKING

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.integration_service as activities_integration
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.sign_up_tokens.integration_service as sign_up_tokens_integration
import modules.followers.integration_service as followers_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.export_service as profile_export_service
import modules.users.users_profile.schema as users_profile_schema
import modules.users.users_profile.utils as profile_utils

if TYPE_CHECKING:
    import modules.auth.dependencies as auth_dependencies

logger = core_logger.get_logger(__name__)

#: Server-managed secrets and privileged attributes that never leave in an export.
_NON_EXPORTED_USER_FIELDS = (
    "password",
    "mfa_secret",
    "access_type",
    "active",
    "mfa_enabled",
    "email_verified",
    "pending_admin_approval",
    "deletion_requested_at",
    "deletion_attempts",
)


def get_profile(
    user_id: int,
    db: Session,
) -> users_schema.UsersMe:
    """Assemble the authenticated user's profile.

    Args:
        user_id: The authenticated user.
        db: Database session.

    Returns:
        The user with their integration links, privacy settings and authentication status.

    Raises:
        NotFoundError: If the user, their integrations or their privacy settings are missing.
    """
    user = users_integration.require_user(user_id, db)

    user_integrations = user_integrations_integration.get_user_integrations(user.id, db)
    if user_integrations is None:
        raise core_exceptions.NotFoundError("User integrations not found")

    privacy_settings = users_privacy_settings_integration.get_privacy_settings(user.id, db)
    if privacy_settings is None:
        raise core_exceptions.NotFoundError("User privacy settings not found")

    pending_email = sign_up_tokens_integration.get_pending_email_changes([user_id], db).get(user_id)

    return users_schema.UsersMe.model_validate(
        {
            **user.model_dump(),
            "pending_email": pending_email.email if pending_email else None,
            "pending_email_expires_at": pending_email.expires_at if pending_email else None,
            "integrations_version": user_integrations.version,
            "is_strava_linked": 1 if user_integrations.strava_token else 0,
            "is_garminconnect_linked": 1 if user_integrations.garminconnect_token else 0,
            "privacy_settings_version": privacy_settings.version,
            "default_activity_visibility": privacy_settings.default_activity_visibility,
            "hide_activity_start_time": privacy_settings.hide_activity_start_time,
            "hide_activity_location": privacy_settings.hide_activity_location,
            "hide_activity_map": privacy_settings.hide_activity_map,
            "hide_activity_hr": privacy_settings.hide_activity_hr,
            "hide_activity_power": privacy_settings.hide_activity_power,
            "hide_activity_cadence": privacy_settings.hide_activity_cadence,
            "hide_activity_elevation": privacy_settings.hide_activity_elevation,
            "hide_activity_speed": privacy_settings.hide_activity_speed,
            "hide_activity_pace": privacy_settings.hide_activity_pace,
            "hide_activity_laps": privacy_settings.hide_activity_laps,
            "hide_activity_workout_sets_steps": privacy_settings.hide_activity_workout_sets_steps,
            "hide_activity_gear": privacy_settings.hide_activity_gear,
            # Lets the frontend tell an account that signs in through an identity provider from one with a
            # local password, so a step-up asks for the right proof. Both flags are auth-owned and come
            # through the auth boundary, so the hash never leaves it.
            "has_local_password": credentials_integration.has_local_password(user_id, db),
            "mfa_enabled": account_security_integration.get_mfa_status(user_id, db).mfa_enabled,
        }
    )


def get_user_profile_overview(
    user_id: int,
    requester_user_id: int,
    db: Session,
    *,
    anchor_date: date | None = None,
) -> users_profile_schema.UserProfileOverviewRead:
    """Assemble the public profile and its visible summary metrics.

    Args:
        user_id: The profile owner.
        requester_user_id: The authenticated viewer.
        db: Database session.
        anchor_date: The viewer's local calendar date for week/month boundaries.

    Returns:
        The public profile and its activity and follower summaries.

    Raises:
        NotFoundError: If the profile is missing, inactive or awaits approval.
    """
    user = users_integration.get_public_profile(user_id, db)
    activity_summary = activities_integration.get_user_profile_summary(
        user_id, requester_user_id, db, anchor=anchor_date
    )
    follow_counts = followers_integration.get_profile_follow_counts(user_id, requester_user_id, db)
    return users_profile_schema.UserProfileOverviewRead(
        user=user,
        week_stats=activity_summary.week_stats,
        month_stats=activity_summary.month_stats,
        month_activity_count=activity_summary.month_activity_count,
        followers_count=follow_counts.followers if follow_counts else None,
        following_count=follow_counts.following if follow_counts else None,
    )


def edit_profile(
    user_id: int, profile: users_schema.ProfileUpdate, db: Session, *, if_match: str
) -> users_schema.UsersMe:
    """Apply the user's own profile edits and commit.

    Args:
        user_id: The authenticated user.
        profile: The allow-listed profile fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The edited profile, whose ``version`` the client sends as its next ``If-Match``.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If the username or email is already taken.
        PreconditionFailedError: If the user changed since the client read them.
    """
    with core_etag.refuse_stale_write(
        db, "profile", lambda: users_integration.get_user(user_id, db) is not None, "User not found"
    ):
        users_integration.edit_profile(user_id, profile, db, if_match=if_match)
        db.commit()
    logger.debug("Profile updated", extra=core_logger.context(user_id=user_id))
    return get_profile(user_id, db)


def change_email(
    user_id: int,
    change: users_schema.EmailChange,
    session_id: str,
    step_up_store: "auth_dependencies.StepUpStore",
    db: Session,
) -> users_schema.UsersMe:
    """Request an email change after step-up verification, to take effect once the new address is confirmed.

    The address is where password resets go, so a stolen access token alone must not be able to
    redirect it. The user keeps their current address until the link emailed to the new one is
    followed; a later request replaces an earlier one, and re-submitting the current address cancels
    a pending change. When the server cannot send mail nothing can be confirmed, so the address is
    changed at once and left unverified. When the request asks for it, the user's other sessions are
    revoked, so a session an attacker holds does not outlive the change.

    Args:
        user_id: The authenticated user.
        change: The new address with the step-up credentials.
        session_id: The caller's current session, which stays signed in when other sessions are revoked.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        The profile after the request: ``pending_email`` is set while a confirmation is awaited, and ``email``
        is the new address when it was applied at once.

    Raises:
        UnauthenticatedError: If step-up verification fails.
        NotFoundError: If the user does not exist.
        ConflictError: If another account uses the email.
    """
    account_security_integration.verify_step_up(
        users_schema.StepUpVerification(**change.model_dump(exclude={"email", "revoke_other_sessions"})),
        user_id,
        session_id,
        identity_providers_constants.StepUpAction.EMAIL_CHANGE,
        step_up_store,
        db,
    )
    new_email = change.email.lower()
    current_email = users_integration.require_user(user_id, db).email
    if new_email == current_email:
        sign_up_tokens_integration.revoke_pending_tokens(user_id, db)
        db.commit()
        return get_profile(user_id, db)

    verification_queued = True
    try:
        users_integration.require_email_available(user_id, new_email, db)
        verification_queued = sign_up_tokens_integration.request_email_change(user_id, new_email, current_email, db)
        if not verification_queued:
            users_integration.stage_email_change(user_id, new_email, db)
    except core_exceptions.ConflictError:
        db.rollback()
        raise
    if change.revoke_other_sessions:
        account_security_integration.delete_other_user_sessions(user_id, session_id, db)
    db.commit()
    logger.info("Email change requested", extra=core_logger.context(user_id=user_id))
    if not verification_queued:
        logger.warning(
            "Email changed but cannot be verified: outgoing email is not configured",
            extra=core_logger.context(user_id=user_id),
        )
    return get_profile(user_id, db)


def resend_email_change(user_id: int, state: platform_providers.StateProvider, db: Session) -> None:
    """Send the confirmation email of the user's pending email change again, at most once per cooldown.

    Nothing tells the caller whether an email was queued: the answer is the same with no pending
    change, no mail configured or a resend inside the cooldown.

    Args:
        user_id: The authenticated user.
        state: The platform state provider, for the resend cooldown.
        db: Database session.
    """
    sign_up_tokens_integration.request_email_change_resend(user_id, state, db)
    db.commit()
    logger.debug("Email change resend handled", extra=core_logger.context(user_id=user_id))


def cancel_email_change(user_id: int, db: Session) -> None:
    """Cancel the user's pending email change, so its confirmation link stops working.

    Args:
        user_id: The authenticated user.
        db: Database session.
    """
    sign_up_tokens_integration.revoke_pending_tokens(user_id, db)
    db.commit()
    logger.info("Pending email change cancelled", extra=core_logger.context(user_id=user_id))


def edit_privacy_settings(
    user_id: int,
    privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsUpdate,
    db: Session,
    *,
    if_match: str,
) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """Apply the user's own privacy settings and commit.

    Args:
        user_id: The authenticated user.
        privacy_settings: The privacy fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The edited settings, whose ``version`` the client sends as its next ``If-Match``.

    Raises:
        NotFoundError: If the user has no privacy settings.
        PreconditionFailedError: If the settings changed since the client read them.
    """
    with core_etag.refuse_stale_write(
        db,
        "privacy settings",
        lambda: users_privacy_settings_integration.get_privacy_settings(user_id, db) is not None,
        "User privacy settings not found",
    ):
        updated = users_privacy_settings_integration.edit_privacy_settings(
            user_id, privacy_settings, db, if_match=if_match
        )
        db.commit()
    logger.debug("Privacy settings updated", extra=core_logger.context(user_id=user_id))
    return updated


def delete_account(
    user_id: int,
    session_id: str,
    step_up: users_schema.StepUpVerification,
    step_up_store: "auth_dependencies.StepUpStore",
    state: platform_providers.StateProvider,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> users_schema.UserDeletionStatus:
    """Queue the deletion of the authenticated user's account and all of their data.

    The right to erasure: the user, their activities and stored files, health records, gear, goals,
    integrations, privacy settings, sessions and every other row that references them are removed. The
    caller must prove their identity again first, so a stolen access token cannot erase an account. The
    account is signed out and deactivated before this returns, and a background job erases the data.

    Args:
        user_id: The authenticated user.
        session_id: The caller's session.
        step_up: Step-up verification payload (password or identity-provider sign-in, and an MFA code when MFA
            is enabled).
        step_up_store: Step-up lockout store.
        state: The platform state provider.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The deletion's initial status.

    Raises:
        UnauthenticatedError: If step-up verification fails.
        ConflictError: If the user is the only administrator, or a deletion is already pending.
    """
    account_security_integration.verify_step_up(
        step_up, user_id, session_id, identity_providers_constants.StepUpAction.ACCOUNT_DELETE, step_up_store, db
    )
    status = users_integration.request_user_deletion(user_id, state, storage, db)
    logger.info("Account deletion requested by its owner", extra=core_logger.context(user_id=user_id))
    return status


def stage_export(user_id: int, storage: platform_providers.StorageProvider, db: Session) -> int:
    """Build the export of the user's profile data as a ZIP archive and stage it for download.

    The archive is complete before it is staged, so a failure never leaves a download that stops
    half way. It is built in a temporary file and streamed into storage, so it is never held in memory.

    Args:
        user_id: The exporting user.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The staged archive's size in bytes.

    Raises:
        NotFoundError: If the user does not exist.
        DomainError: If the archive cannot be built.
    """
    user = users_integration.require_user(user_id, db)

    user_dict = profile_utils.sqlalchemy_obj_to_dict(user)
    for field in _NON_EXPORTED_USER_FIELDS:
        user_dict.pop(field, None)

    exporter = profile_export_service.ExportService(user_id, storage, db)
    try:
        archive = exporter.build_export_archive(user_dict)
    except profile_exceptions.ProfileOperationError as err:
        raise profile_exceptions.to_domain_error(err, "profile data export") from err

    with archive:
        size = storage.save_stream(
            profile_constants.EXPORT_STAGING_AREA,
            profile_constants.export_staged_key(user_id),
            archive,
            content_type="application/zip",
        )
    logger.info("Profile data exported", extra=core_logger.context(user_id=user_id, size_bytes=size))
    return size


def change_password(
    user_id: int,
    change: users_schema.UsersEditPassword,
    session_id: str,
    step_up_store: account_security_integration.StepUpStore,
    db: Session,
) -> None:
    """Change a user's own password after step-up verification.

    Args:
        user_id: ID of the authenticated user.
        change: Current and new password, optional MFA code and whether to end the other sessions.
        session_id: Session of the caller, kept when the other sessions end.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        UnauthenticatedError: If step-up verification fails.
        InvalidInputError: If the new password fails the configured policy.
    """
    account_security_integration.change_own_password(
        user_id,
        change.current_password,
        change.password,
        change.mfa_code,
        step_up_store,
        db,
        revoke_other_sessions=change.revoke_other_sessions,
        current_session_id=session_id,
    )
    db.commit()
    logger.info("Password changed", extra=core_logger.context(user_id=user_id))


def start_identity_provider_link(
    link_token: str,
    idp_id: int,
    redirect: str | None,
    client_ip: str,
    db: Session,
) -> identity_provider_contracts.BrowserFlowStart:
    """Claim a one-time link token and return the identity provider's authorization URL and browser binding.

    Args:
        link_token: One-time token minted for the link.
        idp_id: ID of the identity provider to link.
        redirect: Frontend return path after linking.
        client_ip: Client address of the request, checked against the address the token was issued to.
        db: Database session.

    Returns:
        The provider's authorization URL, and the secret the browser must keep for the callback.
    """
    staged = account_security_integration.stage_browser_idp_link(link_token, idp_id, redirect, client_ip, db)
    # Committed before the provider URL is built: building it may run OIDC discovery, a network call no open
    # transaction may span.
    db.commit()
    authorization_url = account_security_integration.browser_flow_authorization_url(staged)
    logger.debug("Identity provider link started", extra=core_logger.context(idp_id=idp_id))
    return identity_provider_contracts.BrowserFlowStart(
        authorization_url=authorization_url, browser_binding=staged.browser_binding
    )
