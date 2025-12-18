from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class UsersSessions(BaseModel):
    """
    Represents a user session with metadata about the device, browser, and session timing.
    Attributes:
        id (str): Unique session identifier.
        user_id (int): User ID that owns this session.
        refresh_token (str): Session refresh token.
        ip_address (str): Client IP address (max length: 45).
        device_type (str): Device type (max length: 45).
        operating_system (str): Operating system (max length: 45).
        operating_system_version (str): OS version (max length: 45).
        browser (str): Browser name (max length: 45).
        browser_version (str): Browser version (max length: 45).
        created_at (datetime): Session creation timestamp.
        last_activity_at (datetime): Last activity timestamp for idle timeout.
        expires_at (datetime): Session expiration timestamp.
    Config:
        from_attributes (bool): Allows model initialization from attributes.
        extra (str): Forbids extra fields not defined in the model.
        validate_assignment (bool): Enables validation on assignment.
    Validators:
        expires_at: Ensures that the expiration timestamp is after the creation timestamp.
    """

    id: str = Field(..., description="Unique session identifier")
    user_id: int = Field(..., description="User ID that owns this session")
    refresh_token: str = Field(..., description="Session refresh token")
    ip_address: str = Field(..., max_length=45, description="Client IP address")
    device_type: str = Field(..., max_length=45, description="Device type")
    operating_system: str = Field(..., max_length=45, description="Operating system")
    operating_system_version: str = Field(..., max_length=45, description="OS version")
    browser: str = Field(..., max_length=45, description="Browser name")
    browser_version: str = Field(..., max_length=45, description="Browser version")
    created_at: datetime = Field(..., description="Session creation timestamp")
    last_activity_at: datetime = Field(
        ..., description="Last activity timestamp for idle timeout"
    )
    expires_at: datetime = Field(..., description="Session expiration timestamp")
    oauth_state_id: str | None = Field(
        None, max_length=64, description="Link to OAuth state for PKCE validation"
    )
    tokens_exchanged: bool = Field(
        default=False, description="Prevents duplicate token exchange for mobile"
    )

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )
