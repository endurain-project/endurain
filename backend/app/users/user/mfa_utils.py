import pyotp
import qrcode
import base64
from io import BytesIO
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import users.user.crud as users_crud
import users.user.schema as users_schema


def generate_secret() -> str:
    """Generate a new secret for TOTP"""
    return pyotp.random_base32()


def verify_totp(secret: str, token: str) -> bool:
    """Verify a TOTP token against a secret"""
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)  # Allow 1 window tolerance


def generate_qr_code(secret: str, username: str, app_name: str = "Endurain") -> str:
    """Generate QR code for TOTP setup"""
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=username,
        issuer_name=app_name
    )
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_base64}"


def setup_user_mfa(user_id: int, db: Session) -> users_schema.MFASetupResponse:
    """Setup MFA for a user - generate secret and QR code"""
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user"
        )
    
    # Generate new secret
    secret = generate_secret()
    
    # Generate QR code
    qr_code = generate_qr_code(secret, user.username)
    
    return users_schema.MFASetupResponse(
        secret=secret,
        qr_code=qr_code,
        app_name="Endurain"
    )


def enable_user_mfa(user_id: int, secret: str, mfa_code: str, db: Session) -> bool:
    """Enable MFA for a user after verifying the code"""
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user"
        )
    
    # Verify the MFA code
    if not verify_totp(secret, mfa_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code"
        )
    
    # Encrypt the secret before storing
    encrypted_secret = core_cryptography.encrypt_text(secret)
    
    # Update user with MFA enabled and secret
    users_crud.enable_user_mfa(user_id, encrypted_secret, db)
    
    return True


def disable_user_mfa(user_id: int, mfa_code: str, db: Session) -> bool:
    """Disable MFA for a user after verifying the code"""
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this user"
        )
    
    # Decrypt the secret
    secret = core_cryptography.decrypt_text(user.mfa_secret)
    
    # Verify the MFA code
    if not verify_totp(secret, mfa_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code"
        )
    
    # Disable MFA for user
    users_crud.disable_user_mfa(user_id, db)
    
    return True


def verify_user_mfa(user_id: int, mfa_code: str, db: Session) -> bool:
    """Verify MFA code for a user during login"""
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        return False
    
    if not user.mfa_enabled or not user.mfa_secret:
        return False
    
    # Decrypt the secret
    try:
        secret = core_cryptography.decrypt_text(user.mfa_secret)
        return verify_totp(secret, mfa_code)
    except Exception:
        return False


def is_mfa_enabled_for_user(user_id: int, db: Session) -> bool:
    """Check if MFA is enabled for a user"""
    user = users_crud.get_user_by_id(user_id, db)
    return user and user.mfa_enabled == 1 and user.mfa_secret is not None