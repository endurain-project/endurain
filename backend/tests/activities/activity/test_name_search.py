"""The activity name search is case-insensitive for non-ASCII text, against real PostgreSQL.

The term is lower-cased in Python and the column in the database (``lower(name) LIKE``), so the two must agree on
what lower-casing does to a character: whatever a user types of a name, in any case, finds that activity.
"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
from tests._factories.users import make_user

_PRIVACY_FLAGS = (
    "hide_start_time",
    "hide_location",
    "hide_map",
    "hide_hr",
    "hide_power",
    "hide_cadence",
    "hide_elevation",
    "hide_speed",
    "hide_pace",
    "hide_laps",
    "hide_workout_sets_steps",
    "hide_gear",
)

_NAMES = ("Ärzte-Lauf", "İstanbul Marathon", "Straße Lauf", "ΣΑΣ Trail", "Ñandú Ride", "東京 Run")


def _add(db: Session, user_id: uuid.UUID, name: str, minutes: int, **fields: object) -> None:
    start = datetime.fromisoformat("2026-07-28T09:00:00Z") + timedelta(minutes=minutes)
    activity_crud.create_activity(
        activity_contracts.ActivityCore(
            user_id=user_id,
            name=name,
            distance=1000,
            activity_type=1,
            start_time=start.isoformat(),
            end_time=(start + timedelta(minutes=20)).isoformat(),
            timezone="UTC",
            total_elapsed_time=1300.0,
            total_timer_time=1200.0,
            calories=100,
            visibility=0,
            **{flag: False for flag in _PRIVACY_FLAGS},
            **fields,
        ),
        db,
    )


@pytest.fixture
def user_id(db) -> uuid.UUID:
    owner_id = make_user(db).id
    for position, name in enumerate(_NAMES):
        _add(db, owner_id, name, position * 60)
    return owner_id


def _found(db: Session, user_id: uuid.UUID, term: str) -> list[str]:
    return sorted(
        activity.name
        for activity in activity_crud.get_user_activities(user_id, db, name_search=term, user_is_owner=True)
    )


class TestNameSearchWithNonAsciiText:
    @pytest.mark.parametrize("name", _NAMES)
    def test_a_name_is_found_by_what_the_user_typed_of_it(self, db, user_id, name):
        assert _found(db, user_id, name) == [name]

    # Python's lower() turns İ into i + U+0307 and a final Σ into ς, which PostgreSQL's lower() does not, so a term
    # lower-cased in Python is a different string; the cases PostgreSQL folds the same way are checked here.
    @pytest.mark.parametrize("name", [name for name in _NAMES if not any(char in name for char in "İΣ")])
    def test_a_name_is_found_by_its_lower_case(self, db, user_id, name):
        assert _found(db, user_id, name.lower()) == [name]

    @pytest.mark.parametrize("name", [name for name in _NAMES if "ß" not in name])
    def test_a_name_is_found_by_its_upper_case(self, db, user_id, name):
        assert _found(db, user_id, name.upper()) == [name]

    def test_a_sharp_s_is_found_in_its_own_case_but_not_as_ss(self, db, user_id):
        assert _found(db, user_id, "STRAßE") == ["Straße Lauf"]
        assert _found(db, user_id, "strasse") == []

    @pytest.mark.parametrize(
        ("term", "expected"),
        [
            ("ärz", ["Ärzte-Lauf"]),
            ("ÄRZ", ["Ärzte-Lauf"]),
            ("tanbul", ["İstanbul Marathon"]),
            ("东", []),
            ("京 ru", ["東京 Run"]),
        ],
    )
    def test_a_fragment_is_found_inside_a_name(self, db, user_id, term, expected):
        assert _found(db, user_id, term) == expected

    def test_an_accented_letter_is_not_folded_to_its_base_letter(self, db, user_id):
        assert _found(db, user_id, "arzte") == []
        assert _found(db, user_id, "nandu") == []

    def test_wildcards_in_the_term_match_literally(self, db, user_id):
        _add(db, user_id, "100% Ärzte_Lauf", 600)

        assert _found(db, user_id, "100%") == ["100% Ärzte_Lauf"]
        assert _found(db, user_id, "e_l") == ["100% Ärzte_Lauf"]
        assert _found(db, user_id, "%") == ["100% Ärzte_Lauf"]

    def test_a_location_is_searched_the_same_way(self, db, user_id):
        _add(db, user_id, "Morning run", 700, city="Zürich", town="Männedorf", country="Österreich")

        assert _found(db, user_id, "ZÜRICH") == ["Morning run"]
        assert _found(db, user_id, "männe") == ["Morning run"]
        assert _found(db, user_id, "ÖSTERREICH") == ["Morning run"]
