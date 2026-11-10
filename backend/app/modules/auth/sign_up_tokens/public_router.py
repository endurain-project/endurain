"""Unauthenticated sign-up and email-verification endpoints."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.schema as users_schema

router = APIRouter()


@router.post(
    "/sign-up/request",
    response_model=sign_up_schema.SignUpRead,
    responses={
        400: {
            "description": "A password was sent while the email address is verified first, or none was sent while "
            "it is not (the `password-required` problem type)."
        },
        403: {"description": "Sign-up is not enabled on this server."},
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def signup(
    request: Request,
    user: users_schema.UserSignup,
    state: core_dependencies.PlatformState,
    db: core_dependencies.DbSession,
) -> sign_up_schema.SignUpRead:
    """Create an account using the configured sign-up policy."""
    return sign_up_service.signup(user, state, db)


@router.post(
    "/email-change/cancel",
    response_model=sign_up_schema.EmailChangeCancelRead,
    responses={
        400: {
            "description": "The token is malformed, expired, already used, or names a change that a later change has "
            "replaced."
        },
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def cancel_email_change(
    request: Request,
    cancel_data: sign_up_schema.EmailChangeCancel,
    db: core_dependencies.DbSession,
) -> sign_up_schema.EmailChangeCancelRead:
    """Report an email change as not made by its owner, with the link emailed to the account's address.

    The link works once, for seven days after the change was requested. A pending change is cancelled; a confirmed one
    puts the previous address back unless another account holds it now. Every session of the account ends and its
    API keys are revoked either way. The answer says whether the change had been confirmed and whether the previous
    address was restored.
    """
    return sign_up_service.cancel_email_change(cancel_data.token, db)


@router.post(
    "/sign-up/confirm",
    response_model=sign_up_schema.SignUpRead,
    responses={
        400: {
            "description": "The token is unknown, used or expired; a sign-up confirmation carries no password (the "
            "`password-required` problem type, and the token stays usable); or a password accompanies a token that "
            "does not choose one."
        },
        403: {
            "description": "A sign-up is confirmed while email verification is turned off on this server (the "
            "`email-verification-disabled` problem type)."
        },
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def verify_email(
    request: Request,
    confirm_data: sign_up_schema.SignUpConfirm,
    db: core_dependencies.DbSession,
) -> sign_up_schema.SignUpRead:
    """Verify an account's email address using its one-time token; a sign-up also chooses its password."""
    return sign_up_service.verify_email(confirm_data.token, confirm_data.password, db)


@router.post(
    "/sign-up/resend",
    response_model=sign_up_schema.SignUpRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def resend_verification_email(
    request: Request,
    resend_data: sign_up_schema.SignUpResend,
    state: core_dependencies.PlatformState,
    db: core_dependencies.DbSession,
) -> sign_up_schema.SignUpRead:
    """Send a sign-up's verification email again; the answer is the same whether or not the address is registered."""
    return sign_up_service.resend_sign_up_verification_email(resend_data.email, state, db)
