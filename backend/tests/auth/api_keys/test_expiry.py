"""A new API key expires within the server's maximum API key lifetime."""

from datetime import UTC, datetime, timedelta

import core.config as core_config
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import PASSWORD, make_user

_API_KEYS = f"{core_config.ROOT_PATH}/profile/api-keys"


def _create(owner, expires_at: datetime | None = None):
    body: dict[str, object] = {
        "name": "CLI",
        "scopes": ["activities:upload"],
        "step_up": {"current_password": PASSWORD},
    }
    if expires_at is not None:
        body["expires_at"] = expires_at.isoformat()
    return owner.client.post(_API_KEYS, json=body)


def _owner(committed_sessions, sign_in, *, max_lifetime_days: int):
    with committed_sessions() as db:
        edit_server_settings(db, api_key_max_lifetime_days=max_lifetime_days)
        user = make_user(db)
        db.commit()
    return sign_in(user)


def _expiry(response) -> datetime:
    assert response.status_code == 201, response.text
    return datetime.fromisoformat(response.json()["expires_at"])


class TestApiKeyExpiry:
    def test_an_omitted_expiry_is_the_maximum_lifetime(self, committed_sessions, sign_in):
        owner = _owner(committed_sessions, sign_in, max_lifetime_days=30)
        before = datetime.now(UTC)

        expiry = _expiry(_create(owner))

        assert before + timedelta(days=30) <= expiry <= datetime.now(UTC) + timedelta(days=30)

    def test_an_expiry_within_the_maximum_is_kept(self, committed_sessions, sign_in):
        owner = _owner(committed_sessions, sign_in, max_lifetime_days=30)
        requested = datetime.now(UTC) + timedelta(days=10)

        assert _expiry(_create(owner, requested)) == requested

    def test_an_expiry_beyond_the_maximum_is_a_field_error_on_expires_at_and_creates_no_key(
        self, committed_sessions, sign_in
    ):
        owner = _owner(committed_sessions, sign_in, max_lifetime_days=30)

        response = _create(owner, datetime.now(UTC) + timedelta(days=31))

        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "body.expires_at"
        assert owner.client.get(_API_KEYS).json()["total"] == 0

    def test_a_past_expiry_is_refused(self, committed_sessions, sign_in):
        owner = _owner(committed_sessions, sign_in, max_lifetime_days=30)

        response = _create(owner, datetime.now(UTC) - timedelta(days=1))

        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "body.expires_at"
