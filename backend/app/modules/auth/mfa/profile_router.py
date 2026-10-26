"""The signed-in user's own two-step verification, mounted under ``/profile/mfa``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_service as auth_identity_service
import modules.auth.mfa.backup_codes.schema as mfa_backup_codes_schema
import modules.auth.mfa.schema as mfa_schema
import modules.users.users.schema as users_schema

router = APIRouter()


# MFA logic
@router.get(
    "/status",
    status_code=status.HTTP_200_OK,
    response_model=mfa_schema.MFAStatusResponse,
)
def get_mfa_status(
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> mfa_schema.MFAStatusResponse:
    """Return MFA enabled status for authenticated user.

    Args:
        token_user_id: User ID from access token.
        identity_service: Identity service dependency.

    Returns:
        MFA status response with enabled flag.
    """
    return identity_service.get_mfa_status(token_user_id)


@router.get(
    "/backup-codes/status",
    status_code=status.HTTP_200_OK,
    response_model=mfa_backup_codes_schema.MFABackupCodeStatus,
)
def get_backup_code_status(
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> mfa_backup_codes_schema.MFABackupCodeStatus:
    """Retrieve MFA backup code status for authenticated user.

    Args:
        token_user_id: User ID from access token.
        identity_service: Identity service dependency.

    Returns:
        Backup code status with counts and creation date.
    """
    return identity_service.get_backup_code_status(token_user_id)


@router.post(
    "/setup",
    status_code=status.HTTP_201_CREATED,
    response_model=mfa_schema.MFASetupResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def setup_mfa(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    mfa_secret_store: Annotated[
        auth_dependencies.MFASecretStoreBackend,
        Depends(auth_dependencies.get_mfa_secret_store),
    ],
) -> mfa_schema.MFASetupResponse:
    """Initiate MFA setup for authenticated user.

    Args:
        request: The incoming request, read by the rate limiter.
        token_user_id: User ID from access token.
        identity_service: Identity service dependency.
        mfa_secret_store: Temporary secret storage.

    Returns:
        MFA setup response with secret and QR code.
    """
    return identity_service.setup_mfa(
        user_id=token_user_id,
        mfa_secret_store=mfa_secret_store,
    )


@router.put("/enable", status_code=status.HTTP_200_OK, response_model=dict)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def enable_mfa(
    request: Request,
    mfa_request: mfa_schema.MFASetupRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    mfa_secret_store: Annotated[
        auth_dependencies.MFASecretStoreBackend,
        Depends(auth_dependencies.get_mfa_secret_store),
    ],
) -> dict:
    """Enable MFA for authenticated user after step-up verification.

    A stolen access token alone must not be sufficient to enrol a
    new TOTP secret on a victim's account (which would lock the
    legitimate user out and hand the attacker the backup codes).
    The caller therefore has to re-prove identity with their
    current password before the binding is committed. The TOTP
    code in the request body is the fresh enrolment code from the
    user's authenticator app and is verified separately by
    :func:`modules.auth.mfa.service.enable_user_mfa` against the secret
    issued by ``POST /profile/mfa/setup``. SSO-only accounts may
    omit ``current_password`` (see
    :func:`modules.auth._internal.services.step_up_service.verify_step_up_credentials`).

    Args:
        request: The incoming request, read by the rate limiter.
        mfa_request: MFA setup request with TOTP code and (when the
            account has a local password) current password.
        token_user_id: User ID from access token.
        identity_service: Identity service instance for backup code
            generation and step-up verification.
        mfa_secret_store: Temporary secret storage.
        step_up_store: Step-up lockout store.

    Returns:
        Success message and the freshly issued backup codes.

    Raises:
        HTTPException: 400 if no setup is in progress or the TOTP
            code is invalid; 401 if step-up verification fails.
    """
    return identity_service.enable_mfa(
        request=mfa_request,
        user_id=token_user_id,
        step_up_store=step_up_store,
        mfa_secret_store=mfa_secret_store,
    )


@router.put("/disable", status_code=status.HTTP_200_OK, response_model=dict)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def disable_mfa(
    request: Request,
    mfa_request: mfa_schema.MFADisableRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
) -> dict:
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
        identity_service: Identity service dependency.
        step_up_store: Step-up lockout store.

    Returns:
        Success message.

    Raises:
        HTTPException: 401 if the current password is wrong or
            the MFA code is invalid; 400 if MFA is not currently
            enabled.
    """
    return identity_service.disable_mfa(
        request=mfa_request,
        user_id=token_user_id,
        step_up_store=step_up_store,
    )


@router.post("/verify", status_code=status.HTTP_200_OK, response_model=dict)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def verify_mfa(
    request: Request,
    mfa_request: mfa_schema.MFARequest,
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> dict:
    """Verify MFA code for authenticated user.

    Args:
        request: The incoming request, read by the rate limiter.
        mfa_request: MFA request with code to verify.
        token_user_id: User ID from access token.
        identity_service: Identity service instance for backup code verification.

    Returns:
        Success message.

    Raises:
        HTTPException: If MFA code is invalid.
    """
    return identity_service.verify_mfa(
        request=mfa_request,
        user_id=token_user_id,
    )


@router.post(
    "/backup-codes",
    status_code=status.HTTP_201_CREATED,
    response_model=mfa_backup_codes_schema.MFABackupCodesResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def generate_mfa_backup_codes(
    response: Response,
    request: Request,
    step_up: users_schema.StepUpVerification,
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
) -> mfa_backup_codes_schema.MFABackupCodesResponse:
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
        identity_service: Identity service for code generation.
        step_up_store: Step-up lockout store.

    Returns:
        Response with generated backup codes and timestamp.

    Raises:
        HTTPException: 401 if step-up verification fails, 404 if
            user not found, 400 if MFA is not enabled.
    """
    return identity_service.generate_backup_codes(
        step_up=step_up,
        user_id=token_user_id,
        step_up_store=step_up_store,
    )
