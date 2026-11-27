"""Request schemas bound a height to a realistic range; a stored height still reads and re-applies."""

import uuid

import pytest
from pydantic import ValidationError

import modules.users.users.schema as users_schema

_USER_ID = uuid.UUID(int=1)

_ADMIN = {"name": "Ana", "username": "newuser", "email": "new@example.com", "access_type": "regular", "active": True}
_STORED = {"id": _USER_ID, "username": "olduser", "email": "old@example.com", "access_type": "regular", "active": True}


def _shapes():
    return {
        "admin_create": lambda height: users_schema.UserCreate(height=height, password="SecurePass1!", **_ADMIN),
        "admin_edit": lambda height: users_schema.UserEdit(height=height, **_ADMIN),
        "profile_update": lambda height: users_schema.ProfileUpdate(height=height),
    }


@pytest.mark.parametrize("shape", list(_shapes()))
@pytest.mark.parametrize("height", [1, 5, 49, 273, 300])
def test_an_unrealistic_height_is_refused(shape, height):
    with pytest.raises(ValidationError):
        _shapes()[shape](height)


@pytest.mark.parametrize("shape", list(_shapes()))
@pytest.mark.parametrize("height", [50, 175, 272, None])
def test_a_realistic_height_is_accepted(shape, height):
    assert _shapes()[shape](height).height == height


def test_a_stored_height_still_reads_and_re_applies():
    read = users_schema.UserRead(name="Ana", height=5, **_STORED)

    assert read.height == 5
    assert users_schema.UserEdit.from_read(read).height == 5
