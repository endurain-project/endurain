from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import server_settings.crud as server_settings_crud
import server_settings.models as server_settings_models


def get_server_settings(db: Session) -> server_settings_models.ServerSettings:
    """
    Get server settings or raise 404.

    Args:
        db: Database session.

    Returns:
        ServerSettings instance.

    Raises:
        HTTPException: If server settings not found.
    """
    server_settings = server_settings_crud.get_server_settings(db)

    if not server_settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server settings not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return server_settings
