from pydantic import BaseModel


class Follower(BaseModel):
    follower_id: int
    following_id: int
    is_accepted: bool

    class Config:
        from_attributes = True