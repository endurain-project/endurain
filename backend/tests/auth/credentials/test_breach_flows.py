"""Every flow that sets a password refuses a breached one when the check is on, and changes nothing."""

import pytest
import sqlalchemy as sa

import core.config as core_config
import modules.auth.credentials.models as credentials_models
import modules.auth.onboarding.token_store as onboarding_token_store
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.users.users.models as users_models
from tests._factories.breach import fake_range_api
from tests._factories.server_settings import edit_server_settings
from tests._factories.tokens import make_reset_token, make_sign_up_token
from tests._factories.users import PASSWORD, make_admin, make_user

_API = core_config.ROOT_PATH
_PUBLIC = f"{_API}/public"
_LEAKED = "a-password-that-leaked-somewhere"
_FRESH = "a-password-nobody-has-leaked-1"
_BREACHED = "urn:endurain:error:password-breached"
_STEP_UP = {"step_up": {"current_password": PASSWORD}}


@pytest.fixture
def range_api(monkeypatch, committed_sessions):
    """The range API lists ``_LEAKED``, and the administrator switched the check on."""
    api = fake_range_api(monkeypatch)
    api.breach(_LEAKED)
    _configure(committed_sessions, check=True)
    return api


def _configure(committed_sessions, *, check: bool, **settings) -> None:
    with committed_sessions() as db:
        edit_server_settings(db, password_breach_check_enabled=check, **settings)
        db.commit()


def _hash_of(committed_sessions, user_id) -> str:
    with committed_sessions() as db:
        return db.scalars(
            sa.select(credentials_models.LocalCredential.password_hash).where(
                credentials_models.LocalCredential.user_id == user_id
            )
        ).one()


def _user_count(committed_sessions) -> int:
    with committed_sessions() as db:
        return db.scalar(sa.select(sa.func.count()).select_from(users_models.Users)) or 0


class TestPasswordReset:
    def _arrange(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            token = make_reset_token(db, user)
            db.commit()
        return user, token

    def test_a_breached_password_is_refused_and_the_token_still_works(self, client, committed_sessions, range_api):
        user, token = self._arrange(committed_sessions)
        before = _hash_of(committed_sessions, user.id)
        url = f"{_PUBLIC}/password-reset/confirm"

        refused = client.post(url, json={"token": token, "password": _LEAKED})

        assert refused.status_code == 422
        assert refused.json()["type"] == _BREACHED
        assert _hash_of(committed_sessions, user.id) == before
        assert client.post(url, json={"token": token, "password": _FRESH}).status_code == 204

    def test_with_the_check_off_the_breached_password_is_accepted_and_nothing_is_sent(
        self, client, committed_sessions, range_api
    ):
        _configure(committed_sessions, check=False)
        _, token = self._arrange(committed_sessions)

        response = client.post(f"{_PUBLIC}/password-reset/confirm", json={"token": token, "password": _LEAKED})

        assert response.status_code == 204
        assert range_api.requests == []


class TestSignUp:
    def test_a_breached_password_is_refused_and_no_account_is_made(self, client, committed_sessions, range_api):
        _configure(committed_sessions, check=True, signup_enabled=True, signup_require_email_verification=False)
        before = _user_count(committed_sessions)

        response = client.post(
            f"{_PUBLIC}/sign-up/request",
            json={"name": "Test", "username": "testuser", "email": "test@example.com", "password": _LEAKED},
        )

        assert response.status_code == 422
        assert response.json()["type"] == _BREACHED
        assert _user_count(committed_sessions) == before

    def test_a_breached_password_chosen_at_confirmation_is_refused_and_the_link_survives(
        self, client, committed_sessions, range_api
    ):
        _configure(committed_sessions, check=True, signup_enabled=True, signup_require_email_verification=True)
        with committed_sessions() as db:
            user = make_user(db, active=False, email_verified=False, with_password=False, deactivated_at=None)
            token = make_sign_up_token(db, user)
            db.commit()
        url = f"{_PUBLIC}/sign-up/confirm"

        refused = client.post(url, json={"token": token, "password": _LEAKED})

        assert refused.status_code == 422
        assert refused.json()["type"] == _BREACHED
        with committed_sessions() as db:
            used = db.scalars(
                sa.select(sign_up_models.SignUpToken.used).where(sign_up_models.SignUpToken.user_id == user.id)
            ).all()
        assert used == [False]
        assert client.post(url, json={"token": token, "password": _FRESH}).status_code == 200


class TestOnboarding:
    def _token(self) -> str:
        import jasil.runtime as platform_runtime

        return onboarding_token_store.OnboardingTokenStore(platform_runtime.get_state()).issue()

    def _body(self, token: str, password: str) -> dict[str, str]:
        return {
            "token": token,
            "name": "Owner",
            "username": "owner",
            "email": "owner@example.com",
            "password": password,
        }

    def test_a_breached_password_is_refused_and_the_setup_token_is_not_burnt(
        self, client, committed_sessions, range_api
    ):
        with committed_sessions() as db:
            db.execute(sa.delete(users_models.Users))
            db.commit()
        token = self._token()

        refused = client.post(f"{_PUBLIC}/onboarding", json=self._body(token, _LEAKED))

        assert refused.status_code == 422
        assert refused.json()["type"] == _BREACHED
        assert _user_count(committed_sessions) == 0
        assert client.post(f"{_PUBLIC}/onboarding", json=self._body(token, _FRESH)).status_code == 201


class TestAccountPasswordChanges:
    def test_a_user_changing_their_own_password_to_a_breached_one_is_refused(
        self, client, committed_sessions, sign_in, range_api
    ):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        me = sign_in(user)
        before = _hash_of(committed_sessions, user.id)

        response = me.client.post(f"{_API}/profile/password/change", json={"password": _LEAKED, **_STEP_UP})

        assert response.status_code == 422
        assert response.json()["type"] == _BREACHED
        assert _hash_of(committed_sessions, user.id) == before

    def test_an_administrator_setting_a_breached_password_is_refused(self, committed_sessions, sign_in, range_api):
        with committed_sessions() as db:
            admin, subject = make_admin(db), make_user(db)
            db.commit()
        me = sign_in(admin)
        before = _hash_of(committed_sessions, subject.id)

        response = me.client.post(f"{_API}/users/{subject.id}/password/change", json={"password": _LEAKED, **_STEP_UP})

        assert response.status_code == 422
        assert response.json()["type"] == _BREACHED
        assert _hash_of(committed_sessions, subject.id) == before
