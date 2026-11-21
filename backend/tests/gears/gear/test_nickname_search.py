"""The gear nickname search and the unique nickname are case-insensitive for non-ASCII text, against real PostgreSQL.

The list filter, the nickname lookup and the ``(user_id, lower(nickname))`` unique index each lower-case in the
database, while the search term and the lookup value are lower-cased in Python, so the two must agree on what
lower-casing does to a character.
"""

import pytest

import core.exceptions as core_exceptions
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.schema as gears_schema
from tests._factories.users import make_user

_NICKNAMES = ("Ärzte Bike", "İstanbul Shoes", "Straße Skis", "ΣΑΣ Racquet", "Ñandú Wetsuit")


@pytest.fixture
def user_id(db):
    owner_id = make_user(db).id
    for nickname in _NICKNAMES:
        gears_crud.create_gear(
            gears_schema.GearCreateRequest(nickname=nickname, gear_type=gears_schema.GearType.BIKE), owner_id, db
        )
    return owner_id


def _listed(db, user_id, term: str) -> list[str]:
    return sorted(
        gear.nickname for gear in gears_crud.get_gear_users_with_pagination(user_id, db, nickname_contains=term)
    )


class TestNicknameSearch:
    @pytest.mark.parametrize("nickname", _NICKNAMES)
    def test_a_gear_is_found_by_what_the_user_typed_of_its_nickname(self, db, user_id, nickname):
        assert _listed(db, user_id, nickname) == [nickname]

    # Python's lower() turns İ into i + U+0307 and a final Σ into ς, which PostgreSQL's lower() does not, so a term
    # lower-cased in Python is a different string; the cases PostgreSQL folds the same way are checked here.
    @pytest.mark.parametrize("nickname", [nickname for nickname in _NICKNAMES if not any(c in nickname for c in "İΣ")])
    def test_a_gear_is_found_by_the_lower_case_of_its_nickname(self, db, user_id, nickname):
        assert _listed(db, user_id, nickname.lower()) == [nickname]

    @pytest.mark.parametrize("nickname", [nickname for nickname in _NICKNAMES if "ß" not in nickname])
    def test_a_gear_is_found_by_the_upper_case_of_its_nickname(self, db, user_id, nickname):
        assert _listed(db, user_id, nickname.upper()) == [nickname]

    def test_the_count_follows_the_same_filter(self, db, user_id):
        assert gears_crud.get_gears_number(user_id, db, nickname_contains="ÄRZTE") == 1
        assert gears_crud.get_gears_number(user_id, db, nickname_contains="arzte") == 0


class TestNicknameUniqueness:
    @staticmethod
    def _create(db, user_id, nickname: str) -> None:
        gears_crud.create_gear(
            gears_schema.GearCreateRequest(nickname=nickname, gear_type=gears_schema.GearType.BIKE), user_id, db
        )

    @pytest.mark.parametrize("nickname", _NICKNAMES)
    def test_the_same_nickname_cannot_be_taken_twice(self, db, user_id, nickname):
        with pytest.raises(core_exceptions.ConflictError):
            self._create(db, user_id, nickname)

    # Python's lower() turns İ into i + U+0307 and a final Σ into ς, which PostgreSQL's lower() does not, so those
    # strings are different nicknames to the index; the upper-case test covers them.
    @pytest.mark.parametrize(
        "nickname", [nickname for nickname in _NICKNAMES if not any(char in nickname for char in "İΣ")]
    )
    def test_a_nickname_cannot_be_taken_again_in_lower_case(self, db, user_id, nickname):
        with pytest.raises(core_exceptions.ConflictError):
            self._create(db, user_id, nickname.lower())

    @pytest.mark.parametrize("nickname", [nickname for nickname in _NICKNAMES if "ß" not in nickname])
    def test_a_nickname_cannot_be_taken_again_in_upper_case(self, db, user_id, nickname):
        with pytest.raises(core_exceptions.ConflictError):
            self._create(db, user_id, nickname.upper())

    @pytest.mark.parametrize("nickname", _NICKNAMES)
    def test_the_lookup_by_nickname_finds_the_gear_the_index_protects(self, db, user_id, nickname):
        found = gears_crud.get_gear_user_by_nickname(user_id, nickname, db)

        assert found is not None
        assert found.nickname == nickname
