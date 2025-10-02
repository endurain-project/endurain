from pydantic import BaseModel


class ServerSettings(BaseModel):
    id: int
    units: int
    public_shareable_links: bool
    public_shareable_links_user_info: bool
    login_photo_set: bool
    currency: int
    num_records_per_page: int

    model_config = {
        "from_attributes": True
    }