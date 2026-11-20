"""The signed-in user's own two-step verification, mounted under ``/profile/mfa``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, Security, status

import core.cache_control as core_cache_control
import core.dependencies as core_dependencies
import core.openapi_contract as core_openapi_contract
import core.rate_limit as core_rate_limit
import modules.auth.account_security.mfa_workflow_service as mfa_workflow_service
import modules.auth.dependencies as auth_dependencies
import modules.auth.mfa.schema as mfa_schema
import modules.auth.mfa_backup_codes.schema as mfa_backup_codes_schema

router = APIRouter()


# MFA logic
@router.get(
    "/status",
    response_model=mfa_schema.MFAStatusRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
def get_mfa_status(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> mfa_schema.MFAStatusRead:
    """Return whether the account has MFA and the second factors it has enrolled."""
    return mfa_workflow_service.get_mfa_status(token_user_id, db)


@router.get(
    "/backup-codes/status",
    response_model=mfa_backup_codes_schema.MFABackupCodeStatusRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
def get_backup_code_status(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> mfa_backup_codes_schema.MFABackupCodeStatusRead:
    """Retrieve MFA backup code status for authenticated user."""
    return mfa_workflow_service.get_backup_code_status(token_user_id, db)


@router.post(
    "/setup",
    status_code=status.HTTP_201_CREATED,
    response_model=mfa_schema.MFASetupRead,
    responses={201: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS}},
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def setup_mfa(
    request: Request,
    response: Response,
    token_user_id: auth_dependencies.CurrentUserId,
    mfa_secret_store: Annotated[
        auth_dependencies.MFASecretStoreBackend,
        Depends(auth_dependencies.get_mfa_secret_store),
    ],
    db: core_dependencies.DbSession,
) -> mfa_schema.MFASetupRead:
    """Initiate MFA setup for authenticated user."""
    core_cache_control.set_no_store(response)
    return mfa_workflow_service.setup_mfa(token_user_id, mfa_secret_store, db)


@router.post(
    "/enable",
    response_model=mfa_backup_codes_schema.MFABackupCodesRead,
    responses={
        200: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS},
        status.HTTP_400_BAD_REQUEST: {"description": "The authenticator code that confirms the setup is wrong."},
    },
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def enable_mfa(
    request: Request,
    response: Response,
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
) -> mfa_backup_codes_schema.MFABackupCodesRead:
    """Enable MFA for authenticated user after step-up verification.

    A stolen access token alone must not be sufficient to enrol a
    new TOTP secret on a victim's account (which would lock the
    legitimate user out and hand the attacker the backup codes).
    The caller therefore has to re-prove identity with their
    current password before the binding is committed. The step-up
    verification is the ``step_up`` object (see
    :func:`modules.auth.account_security.step_up_service.verify_step_up_credentials`).
    The ``totp_code`` in the request body is the fresh enrolment code from the
    user's authenticator app and is verified separately by
    :func:`modules.auth.mfa.service.enable_user_mfa` against the secret
    issued by ``POST /profile/mfa/setup``. The user's other sessions end with the
    change unless ``revoke_other_sessions`` is false.
    """
    core_cache_control.set_no_store(response)
    return mfa_workflow_service.enable_mfa(
        mfa_request, token_user_id, token_session_id, step_up_store, mfa_secret_store, db
    )


@router.post(
    "/disable",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def disable_mfa(
    request: Request,
    body: mfa_schema.MFADisableRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Disable MFA for authenticated user after step-up verification.

    Disabling MFA materially weakens the account's security
    posture, so a valid access token alone is not sufficient: the
    caller must re-prove identity with both their current
    password and a fresh MFA code, both in ``step_up``. The MFA code may be either a
    6-digit TOTP or an unused ``XXXX-XXXX`` backup code — the
    same set of factors accepted at login. Step-up verification
    is the single source of truth for the MFA check;
    :func:`modules.auth.mfa.service.disable_user_mfa` only clears state. The user's
    other sessions end with the change unless ``revoke_other_sessions`` is false.
    """
    mfa_workflow_service.disable_mfa(
        body.step_up,
        token_user_id,
        token_session_id,
        step_up_store,
        db,
        revoke_other_sessions=body.revoke_other_sessions,
    )


@router.post(
    "/backup-codes",
    status_code=status.HTTP_201_CREATED,
    response_model=mfa_backup_codes_schema.MFABackupCodesRead,
    responses={201: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS}},
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def generate_mfa_backup_codes(
    response: Response,
    request: Request,
    body: mfa_schema.MFABackupCodesRequest,
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
    their second factor. The user's other sessions end with the change
    unless ``revoke_other_sessions`` is false.
    """
    core_cache_control.set_no_store(response)
    return mfa_workflow_service.generate_backup_codes(
        body.step_up,
        token_user_id,
        token_session_id,
        step_up_store,
        db,
        revoke_other_sessions=body.revoke_other_sessions,
    )
