from pydantic import BaseModel


class Notification(BaseModel):
    """
    Represents a notification entity.

    Attributes:
        id (int | None): Unique identifier of the notification.
        user_id (int | None): Identifier of the user associated with the notification.
        type (int | None): Type of the notification.
        options (dict | None): Additional options or metadata for the notification.
        read (bool): Indicates whether the notification has been read. Defaults to False.
        created_at (str | None): Timestamp of when the notification was created.

    Config:
        orm_mode (bool): Enables ORM mode for compatibility with ORMs like SQLAlchemy.
    """

    id: int | None = None
    user_id: int | None = None
    type: int | None = None
    options: dict | None = None
    read: bool = False
    created_at: str | None = None

    model_config = {
        "from_attributes": True
    }
