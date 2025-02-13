from pydantic import BaseModel


class ServerSettings(BaseModel):
    id: int
    units: int
    public_shareable_links: bool

    class Config:
        orm_mode = True