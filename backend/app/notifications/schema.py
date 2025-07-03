from pydantic import BaseModel

class Notification(BaseModel):
    id: int | None = None
    user_id: int | None = None
    type: int | None = None
    options: dict | None = None
    read: bool = False
    created_at: str | None = None

    class Config:
        orm_mode = True