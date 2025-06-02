from fastapi import HTTPException, status


def validate_view_type(view_type: str):
    if (
        view_type
        not in [
            "week",
            "month",
            "year",
            "lifetime",
        ]
        and view_type is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid view type field",
        )
