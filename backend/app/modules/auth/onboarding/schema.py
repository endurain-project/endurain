"""Pydantic schemas for first-run onboarding."""

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

import modules.users.users.schema as users_schema


class OnboardingStatusRead(BaseModel):
    """Whether the installation still needs its first administrator.

    Attributes:
        onboarding_required: True while no account exists.
    """

    onboarding_required: StrictBool = Field(..., description="Whether no account exists yet")


class OnboardingCreate(users_schema.FirstAdminCreate):
    """Request to create the first administrator.

    Carries only what the owner chooses; the access level and account state are never accepted.

    Attributes:
        token: The setup token printed in the server log.
    """

    token: StrictStr = Field(..., min_length=1, max_length=256, description="Setup token printed in the server log")

    model_config = ConfigDict(extra="forbid")
