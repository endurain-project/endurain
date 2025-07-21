from pydantic import BaseModel


class ActivitySets(BaseModel):
    id: int | None = None
    activity_id: int
    duration: float
    repetitions: int | None
    weight: float | None
    set_type: str
    start_time: str
    category: int | None
    category_subtype: int | None

    model_config = {
        "from_attributes": True
    }
