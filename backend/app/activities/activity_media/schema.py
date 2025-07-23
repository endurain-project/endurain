from pydantic import BaseModel


class ActivityMedia(BaseModel):
    id: int | None = None
    activity_id: int
    media_path: str
    media_type: int

    model_config = {
        "from_attributes": True
    }
