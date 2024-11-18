from pydantic import BaseModel


class User(BaseModel):
    id: int | None = None
    name: str
    username: str
    email: str
    city: str | None = None
    birthdate: str | None = None
    preferred_language: str
    gender: int
    height: int | None = None
    access_type: int
    photo_path: str | None = None
    is_active: int

    class Config:
        orm_mode = True


class UserCreate(User):
    password: str


class UserMe(User):
    is_strava_linked: int | None = None
    is_garminconnect_linked: int | None = None

class UserEditPassword(BaseModel):
    password: str