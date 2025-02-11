from pydantic import BaseModel


class ServerSettings(BaseModel):
    id: int
    units: int

    class Config:
        orm_mode = True