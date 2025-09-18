from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import server_settings.crud as server_settings_crud


def get_server_settings(db: Session):
    server_settings = server_settings_crud.get_server_settings(db)

    if not server_settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server settings not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return server_settings
