"""Provider tokens: JSON column semantics and compare-and-swap row locks, against real PostgreSQL.

The Garmin Connect token is a ``json`` column, where assigning ``None`` stores a JSON ``null`` and not SQL ``NULL``;
the token refreshes, unlinks and listing rely on that. The ``FOR UPDATE`` compare-and-swap writes decide what two
processes that hold the same previous token do to one row.
"""

import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

import core.cryptography as core_cryptography
import modules.users.users_integrations.crud as integrations_crud
from tests._factories.users import make_user


def _garmin_token(label: str) -> dict[str, Any]:
    return {
        "di_token": core_cryptography.encrypt_token_fernet(f"access-{label}"),
        "di_refresh_token": core_cryptography.encrypt_token_fernet(f"refresh-{label}"),
        "client_id": "Ärzte-ñandú-東京",
        "nested": {"scopes": ["a", "b"], "expires_in": 3600, "revoked": None, "ratio": 0.5},
    }


def _user(factory, token: dict[str, Any] | None = None) -> uuid.UUID:
    with factory() as db:
        user_id = make_user(db).id
        if token is not None:
            integrations_crud.link_garminconnect_account(user_id, token, db)
        db.commit()
    return user_id


def _stored_garmin_token(factory, user_id: uuid.UUID) -> Any:
    with factory() as db:
        return db.execute(
            text("SELECT garminconnect_token FROM users_integrations WHERE user_id = :u"), {"u": user_id}
        ).scalar_one()


def _race(*tasks) -> list[Any]:
    """Run the tasks at the same moment, each with its own committed session, and return their results in order."""
    barrier = threading.Barrier(len(tasks))
    results: list[Any] = [None] * len(tasks)
    errors: list[Exception] = []

    def run(position: int, task) -> None:
        try:
            barrier.wait()
            results[position] = task()
        except Exception as err:
            errors.append(err)

    threads = [threading.Thread(target=run, args=(position, task)) for position, task in enumerate(tasks)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    return results


class TestGarminTokenJson:
    def test_a_token_comes_back_as_it_was_stored(self, committed_sessions):
        token = _garmin_token("one")
        user_id = _user(committed_sessions, token)

        assert _stored_garmin_token(committed_sessions, user_id) == token

    def test_unlinking_stores_a_json_null_and_never_linking_stores_sql_null(self, committed_sessions):
        unlinked = _user(committed_sessions, _garmin_token("gone"))
        never_linked = _user(committed_sessions)
        with committed_sessions() as db:
            integrations_crud.unlink_garminconnect_account(unlinked, db)
            db.commit()

        with committed_sessions() as db:
            rows = dict(
                db.execute(
                    text(
                        "SELECT user_id, garminconnect_token IS NULL AS sql_null FROM users_integrations"
                        " WHERE user_id IN (:a, :b)"
                    ),
                    {"a": unlinked, "b": never_linked},
                ).all()
            )
        assert rows == {unlinked: False, never_linked: True}

    def test_the_linked_listing_skips_both_kinds_of_empty_token_and_pages_past_them(self, committed_sessions):
        linked = sorted(_user(committed_sessions, _garmin_token(f"linked-{n}")) for n in range(3))
        for _ in range(4):
            unlinked = _user(committed_sessions, _garmin_token("gone"))
            with committed_sessions() as db:
                integrations_crud.unlink_garminconnect_account(unlinked, db)
                db.commit()
        for _ in range(2):
            _user(committed_sessions)

        with committed_sessions() as db:
            everyone = integrations_crud.list_user_ids_with_garminconnect_linked(None, 100, db)
            first_page = integrations_crud.list_user_ids_with_garminconnect_linked(None, 2, db)
            second_page = integrations_crud.list_user_ids_with_garminconnect_linked(first_page[-1], 2, db)

        assert everyone == linked
        assert first_page + second_page == linked


class TestTokenCompareAndSwap:
    def test_two_refreshes_from_the_same_token_store_one_of_them(self, committed_sessions):
        old = _garmin_token("old")
        user_id = _user(committed_sessions, old)
        new_tokens = [_garmin_token("new-a"), _garmin_token("new-b")]

        def refresh(new: dict[str, Any]):
            def run() -> bool:
                with committed_sessions() as db:
                    replaced = integrations_crud.replace_garminconnect_token_if_token(user_id, old, new, db)
                    db.commit()
                return replaced

            return run

        results = _race(*(refresh(new) for new in new_tokens))

        assert sorted(results) == [False, True]
        assert _stored_garmin_token(committed_sessions, user_id) == new_tokens[results.index(True)]

    def test_a_refresh_and_an_unlink_from_the_same_token_cannot_both_win(self, committed_sessions):
        old = _garmin_token("old")
        new = _garmin_token("new")
        user_id = _user(committed_sessions, old)

        def refresh() -> bool:
            with committed_sessions() as db:
                replaced = integrations_crud.replace_garminconnect_token_if_token(user_id, old, new, db)
                db.commit()
            return replaced

        def unlink() -> bool:
            with committed_sessions() as db:
                unlinked = integrations_crud.unlink_garminconnect_account_if_token(user_id, old, db)
                db.commit()
            return unlinked

        refreshed, unlinked = _race(refresh, unlink)

        assert refreshed != unlinked
        assert _stored_garmin_token(committed_sessions, user_id) == (new if refreshed else None)

    def test_two_strava_refreshes_from_the_same_refresh_token_store_one_of_them(self, committed_sessions):
        user_id = _user(committed_sessions)
        expires_at = int(datetime.now(UTC).timestamp()) + 3600
        with committed_sessions() as db:
            integrations_crud.link_strava_account(
                user_id, {"access_token": "access-old", "refresh_token": "refresh-old", "expires_at": expires_at}, db
            )
            db.commit()
        with committed_sessions() as db:
            old_refresh_token = integrations_crud.get_user_integrations_by_user_id(user_id, db).strava_refresh_token

        def refresh(label: str):
            def run() -> bool:
                tokens = {
                    "access_token": f"access-{label}",
                    "refresh_token": f"refresh-{label}",
                    "expires_at": expires_at,
                }
                with committed_sessions() as db:
                    replaced = integrations_crud.replace_strava_tokens_if_refresh_token(
                        user_id, old_refresh_token, tokens, db
                    )
                    db.commit()
                return replaced

            return run

        results = _race(refresh("a"), refresh("b"))

        assert sorted(results) == [False, True]
        winner = "a" if results[0] else "b"
        with committed_sessions() as db:
            stored = integrations_crud.get_user_integrations_by_user_id(user_id, db).strava_refresh_token
        assert core_cryptography.decrypt_token_fernet(stored) == f"refresh-{winner}"
