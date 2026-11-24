"""A provider's icon flag is written under ``SELECT ... FOR UPDATE``, against real PostgreSQL.

The provider's version is the icon's entity tag. Two replicas setting the icon at once queue on the row, so each gets
its own version and only the first sees that no icon was there before.
"""

import threading
import uuid

import modules.auth.identity_providers.crud as idp_crud
from tests._factories.identity_links import make_identity_provider

_WRITERS = 4


def test_simultaneous_icon_writes_each_get_a_version_of_their_own_and_see_the_one_before(committed_sessions):
    with committed_sessions() as db:
        idp_id = make_identity_provider(db, "icon-race")
        db.commit()
    barrier = threading.Barrier(_WRITERS)
    outcomes: list[tuple[int, bool] | None] = []
    errors: list[Exception] = []

    def set_icon() -> None:
        try:
            with committed_sessions() as db:
                barrier.wait()
                outcomes.append(idp_crud.set_icon_uploaded(idp_id, True, db))
                db.commit()
        except Exception as err:
            errors.append(err)

    threads = [threading.Thread(target=set_icon) for _ in range(_WRITERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    settled = [outcome for outcome in outcomes if outcome is not None]
    versions = sorted(version for version, _had_icon in settled)
    assert errors == []
    assert len(settled) == _WRITERS
    assert versions == list(range(versions[0], versions[0] + _WRITERS))
    assert sorted(had_icon for _version, had_icon in settled) == [False] + [True] * (_WRITERS - 1)


def test_a_missing_provider_is_reported_as_none(committed_sessions):
    with committed_sessions() as db:
        assert idp_crud.set_icon_uploaded(uuid.uuid4(), True, db) is None
