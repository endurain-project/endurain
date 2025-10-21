import json
import pyotp
import qrcode
import base64
import zipfile
from io import BytesIO
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.logger as core_logger
import profile.schema as profile_schema
import users.user.crud as users_crud


def generate_totp_secret() -> str:
    """
    Generate a base32-encoded secret suitable for TOTP.

    This function returns a cryptographically secure base32 string, generated via
    pyotp.random_base32(), that can be used as the shared secret when provisioning
    time-based one-time password (TOTP) authenticators (e.g., for 2FA).

    Returns:
        str: A base32-encoded secret key for use with TOTP.

    Notes:
        - Treat the returned secret as sensitive; do not log or expose it.
        - The exact length/entropy is determined by pyotp.random_base32().
    """
    return pyotp.random_base32()


def verify_totp(secret: str, token: str) -> bool:
    """
    Verify a Time-based One-Time Password (TOTP) token against a shared secret.

    Parameters
    ----------
    secret : str
        Shared secret used to initialize the TOTP generator (as expected by pyotp, commonly a base32 string).
    token : str
        One-time password (OTP) provided by the user to validate.

    Returns
    -------
    bool
        True if the token is valid within a tolerance of one time-step (current step ±1), False otherwise.

    Notes
    -----
    This function uses pyotp.TOTP.verify with valid_window=1 to allow for minor clock skew between client and server.
    Ensure the secret and token are provided in the formats expected by pyotp.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)  # Allow 1 window tolerance


def generate_qr_code(secret: str, username: str, app_name: str = "Endurain") -> str:
    """
    Generate a base64-encoded PNG data URI containing a QR code for a TOTP provisioning URI.
    Parameters:
        secret (str): Base32-encoded secret key used to initialize pyotp.TOTP (the shared TOTP secret).
        username (str): Account name (e.g., an email or username) to include in the provisioning URI and display in authenticator apps.
        app_name (str, optional): Issuer name to include in the provisioning URI (default: "Endurain").
    Returns:
        str: A data URI string of the form "data:image/png;base64,<base64-data>" containing the generated QR code PNG.
             This value can be used directly as the src attribute of an HTML <img> element.
    Raises:
        Any exceptions raised by pyotp, qrcode, or the underlying image library (Pillow) may propagate if inputs are invalid
        or if image generation/encoding fails.
    Notes:
        - Builds an otpauth://totp/... provisioning URI via pyotp.TOTP.provisioning_uri(name=username, issuer_name=app_name).
        - Renders the QR code using qrcode with version=1, error correction level L, box_size=10 and border=4.
        - The image is written to an in-memory buffer and base64-encoded so it can be embedded in web pages without a file.
        - Ensure dependencies are installed: pyotp, qrcode, pillow.
    """
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=username, issuer_name=app_name)

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
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return f"data:image/png;base64,{img_base64}"


def setup_user_mfa(user_id: int, db: Session) -> profile_schema.MFASetupResponse:
    """
    Prepare a TOTP-based MFA enrollment for a user by generating a new secret and a QR code.

    Parameters
    ----------
    user_id : int
        The primary key of the user to prepare MFA for.
    db : Session
        Database session used to look up the user.

    Returns
    -------
    profile_schema.MFASetupResponse
        A response object containing:
          - secret (str): The generated TOTP secret (typically base32).
          - qr_code (str): A representation of the QR code (format depends on implementation;
            commonly a data URI or base64-encoded PNG) that encodes the provisioning URI.
          - app_name (str): Human-friendly application name (set to "Endurain").

    Raises
    ------
    HTTPException
        404 Not Found: if no user with the provided user_id exists.
        400 Bad Request: if MFA is already enabled for the user.

    Notes
    -----
    - This function only generates and returns the secret and QR code; it does not persist the
      secret to the database or enable MFA on the user's account. The caller should verify a
      one-time TOTP code from the user's authenticator and, upon successful verification,
      securely store the secret and mark MFA as enabled.
    - Secrets and QR codes should be transmitted over secure channels (e.g., TLS) and stored
      encrypted at rest. Treat the generated secret as sensitive data.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user",
        )

    # Generate new secret
    secret = generate_totp_secret()

    # Generate QR code
    qr_code = generate_qr_code(secret, user.username)

    return profile_schema.MFASetupResponse(
        secret=secret, qr_code=qr_code, app_name="Endurain"
    )


def enable_user_mfa(user_id: int, secret: str, mfa_code: str, db: Session):
    """
    Enable multi-factor authentication (MFA) for a user by validating a TOTP code and storing the encrypted secret.

    This function:
    - Confirms the user exists.
    - Ensures MFA is not already enabled for the user.
    - Verifies the provided TOTP (mfa_code) against the provided secret.
    - Encrypts the secret and updates the user's record to enable MFA.

    Parameters
    ----------
    user_id : int
        The ID of the user for whom MFA should be enabled.
    secret : str
        The plain-text TOTP secret provided by the user (will be encrypted before storage).
    mfa_code : str
        The one-time password generated by the user's authenticator app to prove possession of the secret.
    db : Session
        Database session used to look up and update the user record.

    Raises
    ------
    HTTPException
        - 404 NOT FOUND: "User not found" if no user exists with the given user_id.
        - 400 BAD REQUEST: "MFA is already enabled for this user" if MFA is already active for the user.
        - 400 BAD REQUEST: "Invalid MFA code" if the provided mfa_code does not validate against the secret.

    Returns
    -------
    None
        The function performs side effects (encrypting the secret and updating the user's MFA state) and does not return a value.

    Notes
    -----
    Relies on external helpers: users_crud.get_user_by_id, verify_totp, core_cryptography.encrypt_token_fernet, and users_crud.enable_user_mfa.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user",
        )

    # Verify the MFA code
    if not verify_totp(secret, mfa_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code"
        )

    # Encrypt the secret before storing
    encrypted_secret = core_cryptography.encrypt_token_fernet(secret)

    # Check if encryption was successful
    if not encrypted_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt MFA secret",
        )

    # Update user with MFA enabled and secret
    users_crud.enable_user_mfa(user_id, encrypted_secret, db)


def disable_user_mfa(user_id: int, mfa_code: str, db: Session):
    """
    Disable a user's multi-factor authentication (MFA) after verifying a provided TOTP code.

    This function retrieves the user by ID, ensures MFA is currently enabled, decrypts
    the stored MFA secret, verifies the provided TOTP code, and disables MFA for the user
    via the persistence layer.

    Args:
        user_id (int): ID of the user whose MFA should be disabled.
        mfa_code (str): Time-based one-time password (TOTP) code supplied by the user.
        db (Session): Database session used to load and update the user record.

    Returns:
        None

    Raises:
        HTTPException: If the user is not found (404).
        HTTPException: If MFA is not enabled for the user (400).
        HTTPException: If the provided TOTP code is invalid (400).

    Side effects:
        - Decrypts the user's stored MFA secret and uses it to verify the TOTP code.
        - Calls the users_crud layer to disable MFA for the user; commit behavior depends
          on how the provided db session is managed.

    Security considerations:
        - Treat mfa_code and decrypted secrets as sensitive information; avoid logging them.
        - Ensure the db session and cryptographic utilities are used in a secure context.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this user",
        )

    # Decrypt the secret
    secret = core_cryptography.decrypt_token_fernet(user.mfa_secret)

    # Check if decryption was successful
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt MFA secret",
        )

    # Verify the MFA code
    if not verify_totp(secret, mfa_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code"
        )

    # Disable MFA for user
    users_crud.disable_user_mfa(user_id, db)


def verify_user_mfa(user_id: int, mfa_code: str, db: Session) -> bool:
    """
    Verify a user's MFA TOTP code.

    Args:
        user_id (int): ID of the user to verify.
        mfa_code (str): Time-based one-time password (TOTP) code provided by the user.
        db (Session): Database session used to retrieve the user record.

    Returns:
        bool: True if the provided TOTP matches the user's decrypted MFA secret;
        False if MFA is not enabled for the user, no secret is stored, the code is invalid,
        or if any decryption/verification error occurs.

    Raises:
        HTTPException: If no user with the given user_id is found (HTTP 404).

    Notes:
        - The function loads the user from the database, ensures MFA is enabled and a secret exists,
          decrypts the stored secret, and then verifies the provided TOTP against that secret.
        - Any exceptions during decryption or verification are treated as verification failures
          and result in a False return value rather than propagating the error.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not user.mfa_enabled or not user.mfa_secret:
        return False

    # Decrypt the secret
    try:
        secret = core_cryptography.decrypt_token_fernet(user.mfa_secret)
        if not secret:
            core_logger.print_to_log("Failed to decrypt MFA secret", "error")
            return False
        return verify_totp(secret, mfa_code)
    except Exception as err:
        core_logger.print_to_log(f"Error in verify_user_mfa: {err}", "error", exc=err)
        return False


def is_mfa_enabled_for_user(user_id: int, db: Session) -> bool:
    """
    Return whether multi-factor authentication (MFA) is enabled for a given user.

    This function looks up the user by ID using the provided database session and
    returns True only if the user exists, the user's `mfa_enabled` flag equals 1,
    and `mfa_secret` is not None.

    Args:
        user_id (int): ID of the user to check.
        db (Session): Database session used to retrieve the user record.

    Returns:
        bool: True if MFA is enabled for the user, False otherwise.

    Notes:
        - The function treats mfa_enabled == 1 as enabled.
        - If the user does not exist, the function returns False.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        return False
    return bool(user.mfa_enabled == 1 and user.mfa_secret is not None)


# Export utility functions
def sqlalchemy_obj_to_dict(obj):
    """
    Converts a SQLAlchemy model instance into a dictionary mapping column names to their values.

    Args:
        obj: The object to convert. If the object has a __table__ attribute (i.e., is a SQLAlchemy model instance),
             its columns and corresponding values are extracted into a dictionary. Otherwise, the object is returned as is.

    Returns:
        dict: A dictionary representation of the SQLAlchemy model instance if applicable, otherwise the original object.
    """
    if hasattr(obj, "__table__"):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    return obj


def write_json_to_zip(
    zipf: zipfile.ZipFile, filename: str, data, counts: dict, ensure_ascii: bool = False
):
    """
    Writes JSON-serialized data to a file within a ZIP archive.

    Args:
        zipf (zipfile.ZipFile): The ZIP file object to write into.
        filename (str): The name of the file to create within the ZIP archive.
        data (Any): The data to serialize as JSON and write to the file.
        counts (dict): Dictionary to track counts of exported items.
        ensure_ascii (bool, optional): Whether to escape non-ASCII characters in the output. Defaults to False.

    Notes:
        - If data is falsy (e.g., None, empty), nothing is written.
        - Uses json.dumps with default=str to handle non-serializable objects.
    """
    if data:
        counts[filename.split("/")[-1].replace(".json", "")] = (
            len(data) if isinstance(data, (list, tuple)) else 1
        )
        zipf.writestr(
            filename,
            json.dumps(data, default=str, ensure_ascii=ensure_ascii),
        )
