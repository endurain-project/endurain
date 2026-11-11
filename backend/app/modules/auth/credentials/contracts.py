"""Contracts for credential operations."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

import core.exceptions as core_exceptions

#: Longest password, in characters, that any request accepts, whether it sets the password or presents it.
PASSWORD_MAX_LENGTH = 256


class PasswordPolicyError(core_exceptions.DomainError):
    """A password a caller supplied failed policy validation, answered as an unprocessable request.

    The base class answers for any rejection; each subclass names the reason so a client can branch on the
    problem ``type``.
    """

    status_code = 422
    code = "password-rejected"
    title = "Unprocessable Content"
    default_detail = "The password does not meet the configured policy"


class PasswordTooShortError(PasswordPolicyError):
    """The password has fewer characters than the account type's minimum."""

    code = "password-too-short"
    default_detail = "The password is too short"


class PasswordTooCommonError(PasswordPolicyError):
    """The password is on the list of commonly used passwords."""

    code = "password-too-common"
    default_detail = "The password is too common; choose a different one"


class PasswordBreachedError(PasswordPolicyError):
    """The password appears in a known data breach."""

    code = "password-breached"
    default_detail = "The password appears in a known data breach; choose a different one"


class PasswordMatchesAccountError(PasswordPolicyError):
    """The password equals the account's username, email address or the application name."""

    code = "password-matches-account"
    default_detail = "The password must not contain your username, your email address or the application name"


class PasswordBlankError(PasswordPolicyError):
    """The password is only whitespace."""

    code = "password-blank"
    default_detail = "The password must not be only whitespace"


class PasswordUnchangedError(PasswordPolicyError):
    """The new password is the account's current password."""

    code = "password-unchanged"
    default_detail = "The new password must be different from the current one"


class SupportsHashPassword(Protocol):
    """Structural protocol for objects that can hash a password."""

    def hash_password(self, password: str) -> str:
        """Implement the hash password operation."""
        ...


class SupportsVerifyPassword(Protocol):
    """Structural protocol for objects that can verify a password against a hash."""

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Implement the verify password operation."""
        ...


class CredentialRead(BaseModel):
    """Stored local credential data used by auth workflows."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    password_hash: str
    password_change_required: bool
    created_at: datetime
    updated_at: datetime
