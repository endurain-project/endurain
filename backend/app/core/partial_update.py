"""Base for an edit schema whose NOT NULL fields may be omitted but not cleared."""

from typing import ClassVar, Self

from pydantic import BaseModel, model_validator


class NotClearable(BaseModel):
    """An edit (``PATCH``/``PUT``) schema that refuses an explicit null for the fields it lists.

    A partial update applies only the fields present, so an omitted field is left alone. A field the
    database stores as NOT NULL must not be sent as ``null`` either: the null would reach the flush as a
    constraint violation, which the API reports as a conflict. Refusing it here answers 422 instead.
    ``tests/architecture/test_update_schemas_not_null.py`` fails when an edit schema leaves such a field
    out of the list.

    Attributes:
        not_clearable: Names of the fields that cannot be sent as null.
    """

    not_clearable: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def _reject_clearing_required_fields(self) -> Self:
        """Reject an explicit null for a listed field.

        Returns:
            The validated edit.

        Raises:
            ValueError: If a listed field is sent as null.
        """
        cleared = [name for name in self.not_clearable if name in self.model_fields_set and getattr(self, name) is None]
        if cleared:
            raise ValueError(f"{', '.join(cleared)} cannot be null")
        return self
