"""Known-device operations owned by account security: listing and forgetting a user's devices."""

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.known_devices.integration_service as known_devices_integration
import modules.auth.known_devices.schema as known_devices_schema
import modules.auth.schema as auth_schema
import modules.auth.sessions.audit_actions as sessions_audit_actions

logger = core_logger.get_logger(__name__)


def list_user_devices(
    user_id: int, device_id: str | None, page: core_pagination.PageParams, db: Session
) -> known_devices_schema.KnownDevicePage:
    """Return one page of the user's known devices, marking the one the request comes from."""
    return known_devices_integration.list_devices(user_id, device_id, page, db)


def forget_user_device(
    device_id: int,
    user_id: int,
    session_id: str,
    current_device_id: str | None,
    step_up: auth_schema.StepUpVerification,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> None:
    """Verify step-up, then forget one of the user's known devices but the caller's, end its sessions and commit.

    Args:
        device_id: ID of the device to forget.
        user_id: The authenticated user.
        session_id: The caller's session, which the step-up is bound to.
        current_device_id: The device id the request carries, or None when it carries no valid one.
        step_up: The step-up verification.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        NotFoundError: When the user has no such known device.
        ConflictError: When the device is the one the request comes from.
    """
    step_up_service.verify_step_up_credentials(
        user_id,
        step_up.current_password,
        step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=step_up.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.PROFILE_DEVICE_FORGET,
    )
    sessions_ended = known_devices_integration.forget_device(device_id, user_id, current_device_id, db)
    jasil_audit.stage(
        db,
        account_security_audit_actions.DEVICE_FORGET,
        target_type="device",
        target_id=str(device_id),
        target_owner_id=str(user_id),
        details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=sessions_ended),
    )
    db.commit()
    logger.info("Known device forgotten", extra=core_logger.context(user_id=user_id, device_id=device_id))


def forget_other_user_devices(
    user_id: int,
    session_id: str,
    device_id: str | None,
    step_up: auth_schema.StepUpVerification,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> None:
    """Verify step-up, then forget every known device of the user but the caller's, end their sessions and commit.

    Args:
        user_id: The authenticated user.
        session_id: The caller's session, which the step-up is bound to.
        device_id: The device id the request carries, which stays known, or None when it carries no valid one.
        step_up: The step-up verification.
        step_up_store: Step-up lockout store.
        db: Database session.
    """
    step_up_service.verify_step_up_credentials(
        user_id,
        step_up.current_password,
        step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=step_up.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.PROFILE_DEVICES_FORGET_OTHERS,
    )
    sessions_ended = known_devices_integration.forget_other_devices(user_id, device_id, db)
    jasil_audit.stage(
        db,
        account_security_audit_actions.DEVICES_FORGET_OTHERS,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=sessions_ended),
    )
    db.commit()
    logger.info("Other known devices forgotten", extra=core_logger.context(user_id=user_id))


def forget_all_user_devices(
    user_id: int,
    session_id: str,
    step_up: auth_schema.StepUpVerification,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> None:
    """Verify step-up, then forget every known device of the user, end their sessions and commit.

    The caller's own session ends too, since its device is forgotten with the rest.

    Args:
        user_id: The authenticated user.
        session_id: The caller's session, which the step-up is bound to.
        step_up: The step-up verification.
        step_up_store: Step-up lockout store.
        db: Database session.
    """
    step_up_service.verify_step_up_credentials(
        user_id,
        step_up.current_password,
        step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=step_up.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.PROFILE_DEVICES_FORGET_ALL,
    )
    sessions_ended = known_devices_integration.forget_other_devices(user_id, None, db)
    jasil_audit.stage(
        db,
        account_security_audit_actions.DEVICES_FORGET_ALL,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=sessions_ended),
    )
    db.commit()
    logger.info("All known devices forgotten", extra=core_logger.context(user_id=user_id))
