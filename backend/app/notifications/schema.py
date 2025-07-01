from pydantic import BaseModel

class Notification(BaseModel):
    id: int | None = None
    user_id: int | None = None
    message: str
    read: bool = False
    created_at: str | None = None

    class Config:
        orm_mode = True