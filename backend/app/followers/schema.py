from pydantic import BaseModel


class Follower(BaseModel):
    follower_id: int
    following_id: int
    is_accepted: bool

    model_config = {
        "from_attributes": True
    }