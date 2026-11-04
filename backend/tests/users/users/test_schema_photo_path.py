"""A client cannot write ``photo_path``: only the read shapes carry it."""

import pytest
from pydantic import ValidationError

import modules.users.users.schema as users_schema

_FIELDS = {"name": "Ana", "username": "ana", "email": "ana@example.com", "access_type": "regular", "active": True}


def test_admin_create_refuses_photo_path():
    with pytest.raises(ValidationError) as exc:
        users_schema.UsersCreate(**_FIELDS, password="SecurePass1!", photo_path="users/2/photo.jpg")
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_admin_edit_refuses_photo_path():
    with pytest.raises(ValidationError) as exc:
        users_schema.UsersEdit(**_FIELDS, photo_path="users/2/photo.jpg")
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_the_read_shape_carries_photo_path_and_the_edit_built_from_it_does_not():
    read = users_schema.UsersRead(id=1, photo_path="https://example.com/p.jpg", **_FIELDS)
    assert read.photo_path == "https://example.com/p.jpg"
    assert "photo_path" not in users_schema.UsersEdit.from_read(read).model_dump()
