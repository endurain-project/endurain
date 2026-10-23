"""Client response shape shared by the paginated health lists."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class HealthListResponse(BaseModel):
    """Response model for listing records.

    Attributes:
        total: Total number of health records for the user.
        num_records: Number of records in this response.
        page_number: Current page number.
    """

    total: StrictInt = Field(
        ...,
        description="Total number of health records for the user",
    )
    num_records: StrictInt | None = Field(
        default=None,
        description="Number of records in this response",
    )
    page_number: StrictInt | None = Field(
        default=None,
        description="Current page number",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
