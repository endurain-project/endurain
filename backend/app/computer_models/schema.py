from datetime import datetime

from pydantic import BaseModel


class ComputerModelBase(BaseModel):
    manufacturer: str
    product_code: str | None = None
    product_id: int | None = None
    model_name: str
    region: str | None = None


class ComputerModelCreate(ComputerModelBase):
    pass


class ComputerModelRead(ComputerModelBase):
    id: int
    created_at: datetime | str | None = None

    model_config = {"from_attributes": True}
