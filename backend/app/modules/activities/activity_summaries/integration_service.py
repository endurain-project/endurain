"""Public activity-summary operations."""

from datetime import date

from sqlalchemy.orm import Session

import modules.activities.activity_summaries.service as summary_service

SummaryResponse = summary_service.SummaryResponse


def build_summary(
    user_id: int,
    period: str,
    db: Session,
    *,
    anchor: date | None = None,
    target_year: int | None = None,
    activity_type: str | None = None,
) -> SummaryResponse:
    """Build one user's summary for the requested period."""
    return summary_service.build_summary(
        user_id,
        period,
        db,
        anchor=anchor,
        target_year=target_year,
        activity_type=activity_type,
    )
