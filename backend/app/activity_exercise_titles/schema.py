from pydantic import BaseModel


class ActivityExerciseTitles(BaseModel):
    id: int | None = None
    exercise_category: str
    exercise_name: int
    wkt_step_name: str

    class Config:
        orm_mode = True
