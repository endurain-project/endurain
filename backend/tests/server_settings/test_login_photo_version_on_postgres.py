"""The singleton settings row is written under ``SELECT ... FOR UPDATE``, against real PostgreSQL.

The version of the settings is the login photo's entity tag. Two replicas setting the photo at once must queue on the
row so each gets its own version and the second sees that a photo was already there (and so removes the old file).
"""

import threading

import modules.server_settings.crud as server_settings_crud

_WRITERS = 5


def test_simultaneous_photo_writes_each_get_a_version_of_their_own_and_see_the_one_before(committed_sessions):
    barrier = threading.Barrier(_WRITERS)
    outcomes: list[tuple[int, bool]] = []
    errors: list[Exception] = []

    def set_photo() -> None:
        try:
            with committed_sessions() as db:
                barrier.wait()
                outcomes.append(server_settings_crud.set_login_photo(True, db))
                db.commit()
        except Exception as err:
            errors.append(err)

    threads = [threading.Thread(target=set_photo) for _ in range(_WRITERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    versions = sorted(version for version, _had_photo in outcomes)
    assert errors == []
    assert versions == list(range(versions[0], versions[0] + _WRITERS))
    assert sorted(had_photo for _version, had_photo in outcomes) == [False] + [True] * (_WRITERS - 1)


def test_the_stored_version_is_the_last_one_handed_out(committed_sessions):
    with committed_sessions() as db:
        first_version, had_photo = server_settings_crud.set_login_photo(True, db)
        db.commit()
    with committed_sessions() as db:
        removed_version, had_photo_before_removal = server_settings_crud.set_login_photo(False, db)
        db.commit()

    with committed_sessions() as db:
        stored = server_settings_crud.get_server_settings(db)

    assert had_photo is False and had_photo_before_removal is True
    assert removed_version == first_version + 1
    assert stored is not None and stored.version == removed_version
