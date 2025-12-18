import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Response,
    Request,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import session.utils as session_utils
import auth.security as auth_security
import auth.utils as auth_utils
import auth.constants as auth_constants
import session.crud as session_crud
import auth.password_hasher as auth_password_hasher
import auth.token_manager as auth_token_manager
import auth.schema as auth_schema

import auth.mfa_backup_codes.schema as mfa_backup_codes_schema
import auth.mfa_backup_codes.crud as mfa_backup_codes_crud

import auth.identity_providers.utils as idp_utils

import users.user.crud as users_crud
import users.user.utils as users_utils
import profile.utils as profile_utils

import core.database as core_database
import core.rate_limit as core_rate_limit
import core.logger as core_logger

import session.rotated_refresh_tokens.utils as rotated_tokens_utils

# Define the API router
router = APIRouter()


@router.get(
    "/status",
    response_model=mfa_backup_codes_schema.MFABackupCodeStatus,
)
async def get_backup_code_status(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_refresh_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    codes = mfa_backup_codes_crud.get_user_backup_codes(token_user_id, db)

    if not codes:
        return mfa_backup_codes_schema.MFABackupCodeStatus(
            has_codes=False,
            total=0,
            unused=0,
            used=0,
            created_at=None,
        )

    unused = sum(1 for code in codes if not code.used)
    used = sum(1 for code in codes if code.used)
    created_at = codes[0].created_at if codes else None

    return mfa_backup_codes_schema.MFABackupCodeStatus(
        has_codes=True,
        total=len(codes),
        unused=unused,
        used=used,
        created_at=created_at,
    )


@router.post(
    "",
    response_model=mfa_backup_codes_schema.MFABackupCodesResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.MFA_VERIFY_LIMIT)
async def generate_mfa_backup_codes(
    response: Response,
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_refresh_token),
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    user = users_crud.get_user_by_id(token_user_id, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA must be enabled to generate backup codes",
        )

    # Generate codes (invalidates old codes)
    codes = mfa_backup_codes_crud.create_backup_codes(
        token_user_id, password_hasher, db
    )

    # Log event
    core_logger.print_to_log(f"User {user.id} generated MFA backup codes", "info")

    return mfa_backup_codes_schema.MFABackupCodesResponse(
        codes=codes,
        created_at=datetime.now(timezone.utc),
    )
