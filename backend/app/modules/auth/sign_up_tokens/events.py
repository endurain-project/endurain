"""Domain event channels owned by the sign-up tokens module.

Payloads carry user ids only: events are persisted, so neither a verification token
nor an email address may be put in one.
"""

import uuid
from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after a user signed up and must verify their email address.
SIGN_UP_VERIFICATION_REQUESTED = "auth.sign_up_verification_requested"

# Published after an administrator created an account without a password, so its owner can choose one.
ADMIN_INVITATION_REQUESTED = "auth.admin_invitation_requested"

# Published after an email change was requested and the pending address must confirm it.
EMAIL_CHANGE_VERIFICATION_REQUESTED = "auth.email_change_verification_requested"

# Published when someone asked to move an account to this user's email address, so its holder can be told.
EMAIL_CHANGE_ADDRESS_TAKEN = "auth.email_change_address_taken"

# Published after an email change was requested, so the current address can be told and can cancel it.
EMAIL_CHANGE_REQUESTED = "auth.email_change_requested"

# Published after a pending email change was confirmed, so the previous address can be told.
EMAIL_CHANGED = "auth.email_changed"

# Published once per admin after a sign-up needs admin approval.
SIGN_UP_APPROVAL_REQUESTED = "auth.sign_up_approval_requested"

# Published after an admin approved a pending sign-up.
SIGN_UP_APPROVED = "auth.sign_up_approved"

# Published when a sign-up used the email address of an existing account.
SIGN_UP_EXISTING_ACCOUNT = "auth.sign_up_existing_account"


class SignUpUserPayload(VersionedPayload):
    """Validated payload for the events that email one user: verification, invitation, approval and notices.

    Attributes:
        user_id: The user who receives the email.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: uuid.UUID


class SignUpApprovalRequestedPayload(VersionedPayload):
    """Validated payload for the ``auth.sign_up_approval_requested`` event.

    Attributes:
        user_id: The user who signed up and awaits approval.
        admin_user_id: The admin who receives the email.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: uuid.UUID
    admin_user_id: uuid.UUID


class EmailChangedPayload(VersionedPayload):
    """Validated payload for the ``auth.email_changed`` event.

    Attributes:
        user_id: The user whose email address changed.
        token_id: The confirmed token, which records the previous and the new address.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: uuid.UUID
    token_id: uuid.UUID
