"""Re-encrypting stored provider secrets under the first key, as the scheduled job does it."""

import pytest
from cryptography.fernet import Fernet

import modules.users.users_integrations.crud as crud
import modules.users.users_integrations.scheduled_jobs as scheduled_jobs
import modules.users.users_integrations.service as service
from tests._factories.users import make_user

_NEW_KEY = Fernet.generate_key().decode()
_OLD_KEY = Fernet.generate_key().decode()
_STRANGER_KEY = Fernet.generate_key().decode()


def _under(key: str, plaintext: str) -> str:
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def _opens_with_only(key: str, token: str) -> bool:
    try:
        return Fernet(key.encode()).decrypt(token.encode()) is not None
    except Exception:
        return False


@pytest.fixture
def keys(monkeypatch):
    """The old key is the only one configured at first; the new key joins in front of it."""
    monkeypatch.setenv("FERNET_KEY", _OLD_KEY)

    def rotate():
        monkeypatch.setenv("FERNET_KEY", f"{_NEW_KEY},{_OLD_KEY}")

    return rotate


def _link_under_old_key(db, user_id):
    from sqlalchemy import update

    import modules.users.users_integrations.models as models

    garmin = {"di_token": _under(_OLD_KEY, "g-access"), "di_refresh_token": _under(_OLD_KEY, "g-refresh"), "n": 1}
    db.execute(
        update(models.UsersIntegrations)
        .where(models.UsersIntegrations.user_id == user_id)
        .values(
            strava_client_id=_under(_OLD_KEY, "client"),
            strava_client_secret=_under(_OLD_KEY, "secret"),
            strava_token=_under(_OLD_KEY, "access"),
            strava_refresh_token=_under(_OLD_KEY, "refresh"),
            garminconnect_token=garmin,
        )
    )
    db.expire_all()


def test_every_secret_moves_to_the_first_key_and_keeps_its_value(db, keys):
    user = make_user(db)
    _link_under_old_key(db, user.id)
    keys()

    service.reencrypt_stored_secrets(db)

    stored = crud.get_user_integrations_by_user_id(user.id, db)
    assert stored is not None
    for secret, plain in (
        (stored.strava_client_id, "client"),
        (stored.strava_client_secret, "secret"),
        (stored.strava_token, "access"),
        (stored.strava_refresh_token, "refresh"),
    ):
        assert secret is not None
        assert Fernet(_NEW_KEY.encode()).decrypt(secret.encode()).decode() == plain
    assert stored.garminconnect_token is not None
    assert Fernet(_NEW_KEY.encode()).decrypt(stored.garminconnect_token["di_token"].encode()) == b"g-access"
    assert Fernet(_NEW_KEY.encode()).decrypt(stored.garminconnect_token["di_refresh_token"].encode()) == b"g-refresh"
    assert stored.garminconnect_token["n"] == 1


def test_nothing_changes_while_one_key_is_configured(db, keys):
    user = make_user(db)
    _link_under_old_key(db, user.id)
    before = crud.get_user_integrations_by_user_id(user.id, db)

    service.reencrypt_stored_secrets(db)

    assert crud.get_user_integrations_by_user_id(user.id, db) == before


def test_a_secret_no_configured_key_opens_is_left_as_it_is(db, keys):
    user = make_user(db)
    _link_under_old_key(db, user.id)
    stranger_token = {"di_token": _under(_STRANGER_KEY, "x"), "di_refresh_token": _under(_OLD_KEY, "y")}
    crud.link_garminconnect_account(user.id, stranger_token, db)
    keys()

    service.reencrypt_stored_secrets(db)

    stored = crud.get_user_integrations_by_user_id(user.id, db)
    assert stored is not None
    assert stored.garminconnect_token is not None
    assert stored.garminconnect_token["di_token"] == stranger_token["di_token"]
    assert _opens_with_only(_NEW_KEY, stored.garminconnect_token["di_refresh_token"])


def test_a_user_with_nothing_linked_is_untouched(db, keys):
    user = make_user(db)
    keys()

    service.reencrypt_stored_secrets(db)

    stored = crud.get_user_integrations_by_user_id(user.id, db)
    assert stored is not None
    assert (stored.strava_token, stored.garminconnect_token) == (None, None)


def test_the_scheduled_job_runs_it_in_its_own_session(committed_sessions, keys):
    with committed_sessions() as db:
        user = make_user(db)
        _link_under_old_key(db, user.id)
        db.commit()
    keys()

    scheduled_jobs.reencrypt_stored_secrets()

    with committed_sessions() as db:
        stored = crud.get_user_integrations_by_user_id(user.id, db)
    assert stored is not None
    assert stored.strava_token is not None
    assert _opens_with_only(_NEW_KEY, stored.strava_token)


def test_a_token_with_no_secrets_and_a_secret_already_under_the_first_key_are_left_as_they_are(db, keys):
    bare, current = make_user(db), make_user(db)
    crud.link_garminconnect_account(bare.id, {"client_id": "garmin"}, db)
    already = {"di_token": _under(_NEW_KEY, "g-access"), "di_refresh_token": _under(_NEW_KEY, "g-refresh")}
    crud.link_garminconnect_account(current.id, already, db)
    keys()

    service.reencrypt_stored_secrets(db)

    db.expire_all()
    assert crud.get_user_integrations_by_user_id(bare.id, db).garminconnect_token == {"client_id": "garmin"}
    assert crud.get_user_integrations_by_user_id(current.id, db).garminconnect_token == already
