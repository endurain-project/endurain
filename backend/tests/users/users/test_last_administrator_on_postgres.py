"""The last active administrator survives two administrators removing each other at once, against real PostgreSQL.

Each request counts the active administrators before it demotes or deactivates one. The count runs under
``SELECT ... FOR UPDATE`` on every administrator row, so the second request waits for the first, reads the committed
result and refuses; without the lock both see two administrators and both succeed, leaving none.
"""

import threading
from collections.abc import Callable

import pytest
from httpx2 import Response
from sqlalchemy import text

import core.config as core_config
from tests._factories.users import PASSWORD, make_admin

_URL = f"{core_config.ROOT_PATH}/users"


@pytest.fixture
def admins(committed_sessions, sign_in):
    with committed_sessions() as db:
        users = [make_admin(db), make_admin(db)]
        db.commit()
    return [sign_in(user) for user in users]


def _active_admins(committed_sessions) -> int:
    with committed_sessions() as db:
        return db.execute(
            text("SELECT count(*) FROM users WHERE access_type = :admin AND active"), {"admin": "admin"}
        ).scalar_one()


def _edit(actor, target, changes: dict[str, object]) -> Callable[[], Response]:
    """Read ``target`` as ``actor`` now and return the PATCH that applies ``changes`` with the version read."""
    version = actor.client.get(f"{_URL}/{target.user.id}").headers["ETag"]

    def patch() -> Response:
        return actor.client.patch(
            f"{_URL}/{target.user.id}",
            json={**changes, "step_up": {"current_password": PASSWORD}},
            headers={"If-Match": version},
        )

    return patch


def _race(first: Callable[[], Response], second: Callable[[], Response]) -> list[Response]:
    barrier = threading.Barrier(2)
    responses: list[Response | None] = [None, None]

    def run(position: int, task) -> None:
        barrier.wait()
        responses[position] = task()

    threads = [threading.Thread(target=run, args=(position, task)) for position, task in enumerate((first, second))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return [response for response in responses if response is not None]


class TestTwoAdministratorsRemovingEachOther:
    @pytest.mark.parametrize("changes", [{"access_type": "regular"}, {"active": False}], ids=["demote", "deactivate"])
    def test_one_removal_succeeds_and_the_other_is_refused(self, committed_sessions, admins, changes):
        first, second = admins
        responses = _race(_edit(first, second, changes), _edit(second, first, changes))

        assert sorted(response.status_code for response in responses)[0] == 200, [r.text for r in responses]
        refused = next(response for response in responses if response.status_code != 200)
        assert refused.status_code == 409, refused.text
        assert _active_admins(committed_sessions) == 1

    @pytest.mark.parametrize("changes", [{"access_type": "regular"}, {"active": False}], ids=["demote", "deactivate"])
    def test_the_only_administrator_cannot_remove_itself(self, committed_sessions, admins, changes):
        first, second = admins
        assert _edit(first, second, changes)().status_code == 200

        refused = _edit(first, first, changes)()

        assert refused.status_code == 409, refused.text
        assert _active_admins(committed_sessions) == 1
