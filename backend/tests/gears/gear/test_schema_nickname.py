"""A client-sent gear nickname is not blank and carries no text direction control."""

import pytest
from pydantic import ValidationError

import modules.gears.gear.schema as gear_schema


@pytest.mark.parametrize("nickname", ["   ", "a‮b", "a⁦b", "a‏b"])
def test_a_blank_or_directional_nickname_is_refused(nickname):
    with pytest.raises(ValidationError):
        gear_schema.GearCreateRequest(nickname=nickname, gear_type="bike")
    with pytest.raises(ValidationError):
        gear_schema.GearUpdate(nickname=nickname)


def test_an_ordinary_nickname_is_trimmed():
    assert gear_schema.GearCreateRequest(nickname=" Road bike ", gear_type="bike").nickname == "Road bike"
