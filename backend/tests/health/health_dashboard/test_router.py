"""The dashboard route, through the production application."""

import pytest

import core.config as core_config
import core.timezone as core_timezone
import modules.auth.api_keys.constants as api_keys_constants
from tests._factories.api_keys import key_client, make_api_key
from tests._factories.health import make_health_steps
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/health/stats/daily"
_EMPTY_METRICS = ("sleep", "weight", "steps", "fasting", "water", "poop")


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, timezone="UTC")
        make_health_steps(db, created.id, date=core_timezone.today_in(core_timezone.or_default(None)), steps=4321)
        db.commit()
    return created


def _key_client(app, committed_sessions, user, *scopes):
    with committed_sessions() as db:
        key, raw_key = make_api_key(db, user, scopes=list(scopes))
        db.commit()
    return key_client(app, user, key, raw_key).client


class TestDailyStats:
    def test_a_signed_in_user_gets_their_dashboard_with_the_targets(self, sign_in, user):
        response = sign_in(user).client.get(_URL)

        assert response.status_code == 200
        body = response.json()
        assert body["steps"] == {"steps": 4321}
        assert [body[m] for m in _EMPTY_METRICS if m != "steps"] == [None] * 5
        assert body["targets"]["user_id"] == str(user.id)

    def test_without_the_targets_scope_the_targets_are_null_and_the_rest_is_shown(self, app, committed_sessions, user):
        client = _key_client(app, committed_sessions, user, api_keys_constants.ApiKeyScope.HEALTH_READ)

        body = client.get(_URL).json()

        assert body["targets"] is None
        assert body["steps"] == {"steps": 4321}

    def test_with_the_targets_scope_the_targets_are_shown(self, app, committed_sessions, user):
        client = _key_client(
            app,
            committed_sessions,
            user,
            api_keys_constants.ApiKeyScope.HEALTH_READ,
            api_keys_constants.ApiKeyScope.HEALTH_TARGETS_READ,
        )

        assert client.get(_URL).json()["targets"]["user_id"] == str(user.id)

    def test_another_users_records_are_not_in_the_dashboard(self, sign_in, committed_sessions, user):
        with committed_sessions() as db:
            stranger = make_user(db, timezone="UTC")
            db.commit()

        assert sign_in(stranger).client.get(_URL).json()["steps"] is None
