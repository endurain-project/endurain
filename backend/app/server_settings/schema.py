from pydantic import BaseModel


class ServerSettings(BaseModel):
    id: int
    units: int
    public_shareable_links: bool
    public_shareable_links_user_info: bool
    login_photo_set: bool

    class Config:
        orm_mode = True