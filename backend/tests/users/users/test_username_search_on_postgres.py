"""The administrators' username search runs ``lower(username) LIKE`` on real PostgreSQL."""

import pytest
from tests._factories.users import make_user

import modules.users.users.crud as users_crud

_USERNAMES = ("Alice.Smith", "bob_jones", "bobxjones", "CAROL-99")


@pytest.fixture(autouse=True)
def _users(db) -> None:
    for username in _USERNAMES:
        make_user(db, username=username)


def _found(db, term: str) -> list[str]:
    return sorted(user.username.lower() for user in users_crud.get_users_with_pagination(db, username_contains=term))


class TestUsernameSearch:
    @pytest.mark.parametrize("term", ["alice", "ALICE", "Alice.S", ".smith", "SMITH"])
    def test_a_fragment_is_found_whatever_its_case(self, db, term):
        assert _found(db, term) == ["alice.smith"]

    def test_wildcards_in_the_term_match_literally(self, db):
        assert _found(db, "bob_j") == ["bob_jones"]
        assert _found(db, "%") == []

    def test_the_count_follows_the_same_filter(self, db):
        assert users_crud.get_users_number(db, username_contains="BOB") == 2

    @pytest.mark.parametrize("term", ["ärzte", "İstanbul", "straße", "ΣΑΣ", "東京"])
    def test_a_term_with_non_ascii_text_matches_no_username_and_is_not_an_error(self, db, term):
        assert _found(db, term) == []
