from pydantic import BaseModel

class GarminLogin(BaseModel):
    username: str
    password: str