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


class TestNicknameCollation:
    """PostgreSQL's ICU collation folds what ``lower()`` does not: the final sigma and the Unicode normal forms."""

    @staticmethod
    def _create(db, user_id, nickname: str) -> None:
        gears_crud.create_gear(
            gears_schema.GearCreateRequest(nickname=nickname, gear_type=gears_schema.GearType.BIKE), user_id, db
        )

    @pytest.mark.parametrize("term", ["ΣΑΣ", "\u03c3\u03b1\u03c3", "σας", "ΣΑς"])
    def test_every_form_of_sigma_finds_a_nickname_in_the_search_and_the_lookup(self, db, user_id, term):
        assert _listed(db, user_id, term) == ["ΣΑΣ Racquet"]
        found = gears_crud.get_gear_user_by_nickname(user_id, "σας racquet", db)
        assert found is not None
        assert found.nickname == "ΣΑΣ Racquet"

    def test_the_lookup_matches_a_final_sigma_against_a_capital_sigma(self, db, user_id):
        self._create(db, user_id, "ΟΔΟΣ")

        found = gears_crud.get_gear_user_by_nickname(user_id, "οδος", db)

        assert found is not None
        assert found.nickname == "ΟΔΟΣ"

    def test_a_decomposed_term_finds_a_composed_nickname(self, db, user_id):
        assert _listed(db, user_id, "ARZTE") == []
        self._create(db, user_id, "Caf\u00e9 Bike")

        assert _listed(db, user_id, "CAFE\u0301") == ["Caf\u00e9 Bike"]
        found = gears_crud.get_gear_user_by_nickname(user_id, "cafe\u0301 bike", db)
        assert found is not None
        assert found.nickname == "Caf\u00e9 Bike"

    def test_an_accent_and_a_sharp_s_still_tell_letters_apart(self, db, user_id):
        assert _listed(db, user_id, "straSSe") == []
        assert gears_crud.get_gear_user_by_nickname(user_id, "arzte bike", db) is None

    def test_wildcards_in_the_term_match_literally(self, db, user_id):
        self._create(db, user_id, "100% Bike_One")

        assert _listed(db, user_id, "100%") == ["100% Bike_One"]
        assert _listed(db, user_id, "e_o") == ["100% Bike_One"]
        assert _listed(db, user_id, "%") == ["100% Bike_One"]

    @pytest.mark.parametrize(
        ("existing", "again"),
        [("ΟΔΟΣ", "οδος"), ("ΟΔΟΣ", "ΟΔΟς"), ("Caf\u00e9", "Cafe\u0301"), ("Caf\u00e9", "CAF\u00c9")],
    )
    def test_a_nickname_equal_under_the_collation_is_refused(self, db, user_id, existing, again):
        self._create(db, user_id, existing)

        with pytest.raises(core_exceptions.ConflictError):
            self._create(db, user_id, again)


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
