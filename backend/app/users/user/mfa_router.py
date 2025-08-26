from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import core.database as core_database
import session.security as session_security
import users.user.schema as users_schema
import users.user.mfa_utils as mfa_utils

# Define the API router
router = APIRouter()


@router.get("/status", response_model=users_schema.MFAStatusResponse)
async def get_mfa_status(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Get MFA status for the current user"""
    is_enabled = mfa_utils.is_mfa_enabled_for_user(token_user_id, db)
    return users_schema.MFAStatusResponse(mfa_enabled=is_enabled)


@router.post("/setup", response_model=users_schema.MFASetupResponse)
async def setup_mfa(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    mfa_secret_store: Annotated[
        users_schema.MFASecretStore, Depends(users_schema.get_mfa_secret_store)
    ],
):
    """Setup MFA for the current user - generates secret and QR code"""
    response = mfa_utils.setup_user_mfa(token_user_id, db)
    
    # Store the secret temporarily for the enable step
    mfa_secret_store.add_secret(token_user_id, response.secret)
    
    return response


@router.post("/enable")
async def enable_mfa(
    request: users_schema.MFASetupRequest,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    mfa_secret_store: Annotated[
        users_schema.MFASecretStore, Depends(users_schema.get_mfa_secret_store)
    ],
):
    """Enable MFA after verifying the setup code"""
    # Get the secret from temporary storage
    secret = mfa_secret_store.get_secret(token_user_id)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No MFA setup in progress. Please run setup first."
        )
    
    try:
        mfa_utils.enable_user_mfa(token_user_id, secret, request.mfa_code, db)
        # Clean up the temporary secret
        mfa_secret_store.delete_secret(token_user_id)
        return {"message": "MFA enabled successfully"}
    except HTTPException:
        # Clean up on error
        mfa_secret_store.delete_secret(token_user_id)
        raise


@router.post("/disable")
async def disable_mfa(
    request: users_schema.MFADisableRequest,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Disable MFA for the current user"""
    mfa_utils.disable_user_mfa(token_user_id, request.mfa_code, db)
    return {"message": "MFA disabled successfully"}


@router.post("/verify")
async def verify_mfa(
    request: users_schema.MFARequest,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Verify MFA code for the current user"""
    is_valid = mfa_utils.verify_user_mfa(token_user_id, request.mfa_code, db)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code"
        )
    return {"message": "MFA code verified successfully"}