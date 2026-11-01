"""The signed-in user's own two-step verification, mounted under ``/profile/mfa``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.account_security.mfa_workflow_service as mfa_workflow_service
import modules.auth.dependencies as auth_dependencies
import modules.auth.mfa.schema as mfa_schema
import modules.auth.mfa_backup_codes.schema as mfa_backup_codes_schema
import modules.users.users.schema as users_schema

router = APIRouter()


# MFA logic
@router.get(
    "/status",
    response_model=mfa_schema.MFAStatusRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def get_mfa_status(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> mfa_schema.MFAStatusRead:
    """Return MFA enabled status for authenticated user.

    Args:
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        MFA status response with enabled flag.
    """
    return mfa_workflow_service.get_mfa_status(token_user_id, db)


@router.get(
    "/backup-codes/status",
    response_model=mfa_backup_codes_schema.MFABackupCodeStatusRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def get_backup_code_status(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> mfa_backup_codes_schema.MFABackupCodeStatusRead:
    """Retrieve MFA backup code status for authenticated user.

    Args:
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Backup code status with counts and creation date.
    """
    return mfa_workflow_service.get_backup_code_status(token_user_id, db)


@router.post(
    "/setup",
    status_code=status.HTTP_201_CREATED,
    response_model=mfa_schema.MFASetupRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def setup_mfa(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    mfa_secret_store: Annotated[
        auth_dependencies.MFASecretStoreBackend,
        Depends(auth_dependencies.get_mfa_secret_store),
    ],
    db: core_dependencies.DbSession,
) -> mfa_schema.MFASetupRead:
    """Initiate MFA setup for authenticated user.

    Args:
        request: The incoming request, read by the rate limiter.
        token_user_id: User ID from access token.
        mfa_secret_store: Temporary secret storage.
        db: Database session.

    Returns:
        MFA setup response with secret and QR code.
    """
    return mfa_workflow_service.setup_mfa(token_user_id, mfa_secret_store, db)


@router.post(
    "/enable",
    response_model=mfa_schema.MFAEnableRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def enable_mfa(
    request: Request,
    mfa_request: mfa_schema.MFASetupRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    mfa_secret_store: Annotated[
        auth_dependencies.MFASecretStoreBackend,
        Depends(auth_dependencies.get_mfa_secret_store),
    ],
    db: core_dependencies.DbSession,
) -> mfa_schema.MFAEnableRead:
    """Enable MFA for authenticated user after step-up verification.

    A stolen access token alone must not be sufficient to enrol a
    new TOTP secret on a victim's account (which would lock the
    legitimate user out and hand the attacker the backup codes).
    The caller therefore has to re-prove identity with their
    current password before the binding is committed. The TOTP
    code in the request body is the fresh enrolment code from the
    user's authenticator app and is verified separately by
    :func:`modules.auth.mfa.service.enable_user_mfa` against the secret
    issued by ``POST /profile/mfa/setup``. An account without a local
    password sends ``idp_reauth`` instead of ``current_password`` (see
    :func:`modules.auth.account_security.step_up_service.verify_step_up_credentials`).

    Args:
        request: The incoming request, read by the rate limiter.
        mfa_request: MFA setup request with TOTP code and (when the
            account has a local password) current password.
        token_user_id: User ID from access token.
        token_session_id: Session ID from access token.
        mfa_secret_store: Temporary secret storage.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        Success message and the freshly issued backup codes.

    Raises:
        DomainError: 400 if no setup is in progress or the TOTP
            code is invalid; 401 if step-up verification fails.
    """
    return mfa_workflow_service.enable_mfa(
        mfa_request, token_user_id, token_session_id, step_up_store, mfa_secret_store, db
    )


@router.post(
    "/disable",
    response_model=mfa_schema.MFADisableRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def disable_mfa(
    request: Request,
    mfa_request: mfa_schema.MFADisableRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> mfa_schema.MFADisableRead:
    """Disable MFA for authenticated user after step-up verification.

    Disabling MFA materially weakens the account's security
    posture, so a valid access token alone is not sufficient: the
    caller must re-prove identity with both their current
    password and a fresh MFA code. The MFA code may be either a
    6-digit TOTP or an unused ``XXXX-XXXX`` backup code — the
    same set of factors accepted at login. Step-up verification
    is the single source of truth for the MFA check;
    :func:`modules.auth.mfa.service.disable_user_mfa` only clears state.

    Args:
        request: The incoming request, read by the rate limiter.
        mfa_request: MFA disable request with current password and
            MFA code.
        token_user_id: User ID from access token.
        token_session_id: Session ID from access token.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        Success message.

    Raises:
        DomainError: 401 if the current password is wrong or
            the MFA code is invalid; 400 if MFA is not currently
            enabled.
    """
    return mfa_workflow_service.disable_mfa(mfa_request, token_user_id, token_session_id, step_up_store, db)


@router.post(
    "/verify",
    response_model=mfa_schema.MFAVerifyRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def verify_mfa(
    request: Request,
    mfa_request: mfa_schema.MFARequest,
    token_user_id: auth_dependencies.CurrentUserId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> mfa_schema.MFAVerifyRead:
    """Verify MFA code for authenticated user.

    Args:
        request: The incoming request, read by the rate limiter.
        mfa_request: MFA request with code to verify.
        token_user_id: User ID from access token.
        step_up_store: Shared state, which records the TOTP step so the code works once.
        db: Database session.

    Returns:
        Success message.

    Raises:
        DomainError: If MFA code is invalid.
    """
    return mfa_workflow_service.verify_mfa(mfa_request, token_user_id, step_up_store, db)


@router.post(
    "/backup-codes",
    status_code=status.HTTP_201_CREATED,
    response_model=mfa_backup_codes_schema.MFABackupCodesRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def generate_mfa_backup_codes(
    response: Response,
    request: Request,
    step_up: users_schema.StepUpVerification,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> mfa_backup_codes_schema.MFABackupCodesRead:
    """Generate new MFA backup codes for authenticated user.

    Requires step-up verification (current password + MFA code,
    when MFA is enabled). Issuing new backup codes invalidates
    the previous set, so an attacker holding only an access
    token must not be able to lock the legitimate user out of
    their second factor.

    Args:
        response: FastAPI response object.
        request: FastAPI request object for rate limiting.
        step_up: Step-up verification payload.
        token_user_id: User ID from access token.
        token_session_id: Session ID from access token.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        Response with generated backup codes and timestamp.

    Raises:
        DomainError: 401 if step-up verification fails, 404 if
            user not found, 400 if MFA is not enabled.
    """
    return mfa_workflow_service.generate_backup_codes(step_up, token_user_id, token_session_id, step_up_store, db)
