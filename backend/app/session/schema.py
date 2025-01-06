from pydantic import BaseModel
from datetime import datetime


class UsersSessions(BaseModel):
    id: str
    user_id: int
    refresh_token: str
    ip_address: str
    device_type: str
    operating_system: str
    operating_system_version: str
    browser: str
    browser_version: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True