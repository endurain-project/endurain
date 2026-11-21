"""The "Require MFA" setting: who it covers and which requests an account that must enrol may still make."""

import jasil.providers as platform_providers
import jasil.runtime as jasil_runtime
import pytest

import core.config as core_config
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.constants as auth_constants
import modules.server_settings.contracts as server_settings_contracts
from tests._factories.api_keys import key_client, make_api_key
from tests._factories.server_settings import edit_server_settings
from tests._factories.tokens import audit_rows, make_mfa
from tests._factories.users import make_admin, make_user

_ROOT = core_config.ROOT_PATH
_ENROLMENT_REQUIRED = "urn:endurain:error:mfa-enrolment-required"
_RequireMfa = server_settings_contracts.RequireMfa
#: A route the enrolment page does not need, open to any signed-in user.
_ELSEWHERE = f"{_ROOT}/gears"


def _require(committed_sessions, setting: _RequireMfa) -> None:
    with committed_sessions() as db:
        edit_server_settings(db, require_mfa=setting.value)
        db.commit()


def _signed_in(committed_sessions, sign_in, *, admin: bool = False, enrolled: bool = False):
    with committed_sessions() as db:
        user = make_admin(db) if admin else make_user(db)
        if enrolled:
            make_mfa(db, user)
        db.commit()
    return sign_in(user)


class TestWhoMustEnrol:
    @pytest.mark.parametrize(
        ("setting", "admin", "refused"),
        [
            (_RequireMfa.OFF, True, False),
            (_RequireMfa.OFF, False, False),
            (_RequireMfa.ADMINISTRATORS, True, True),
            (_RequireMfa.ADMINISTRATORS, False, False),
            (_RequireMfa.EVERYONE, True, True),
            (_RequireMfa.EVERYONE, False, True),
        ],
        ids=lambda value: str(getattr(value, "value", value)),
    )
    def test_a_covered_account_without_mfa_is_refused_everywhere_else(
        self, committed_sessions, sign_in, setting, admin, refused
    ):
        _require(committed_sessions, setting)
        signed_in = _signed_in(committed_sessions, sign_in, admin=admin)

        response = signed_in.client.get(_ELSEWHERE)

        assert response.status_code == (403 if refused else 200)
        if refused:
            assert response.json()["type"] == _ENROLMENT_REQUIRED

    @pytest.mark.parametrize("setting", list(_RequireMfa))
    @pytest.mark.parametrize("admin", [True, False], ids=["admin", "regular"])
    def test_an_account_with_mfa_is_never_refused(self, committed_sessions, sign_in, setting, admin):
        _require(committed_sessions, setting)
        signed_in = _signed_in(committed_sessions, sign_in, admin=admin, enrolled=True)

        assert signed_in.client.get(_ELSEWHERE).status_code == 200

    def test_the_refusal_is_not_an_insufficient_scope_challenge(self, committed_sessions, sign_in):
        _require(committed_sessions, _RequireMfa.EVERYONE)
        signed_in = _signed_in(committed_sessions, sign_in)

        assert "www-authenticate" not in signed_in.client.get(_ELSEWHERE).headers

    def test_a_scope_checked_route_is_refused_the_same_way(self, committed_sessions, sign_in):
        _require(committed_sessions, _RequireMfa.EVERYONE)
        signed_in = _signed_in(committed_sessions, sign_in)

        response = signed_in.client.post(f"{_ROOT}/profile/mfa/disable", json={"step_up": {"current_password": "x"}})

        assert response.status_code == 403
        assert response.json()["type"] == _ENROLMENT_REQUIRED

    def test_an_api_key_of_such_an_account_is_refused_too(self, app, committed_sessions):
        _require(committed_sessions, _RequireMfa.EVERYONE)
        with committed_sessions() as db:
            user = make_user(db)
            key, raw_key = make_api_key(db, user, scopes=[api_keys_constants.ApiKeyScope.GEARS_READ])
            db.commit()

        response = key_client(app, user, key, raw_key).client.get(_ELSEWHERE)

        assert response.status_code == 403
        assert response.json()["type"] == _ENROLMENT_REQUIRED

    def test_the_account_is_served_again_once_it_has_enrolled(self, committed_sessions, sign_in):
        _require(committed_sessions, _RequireMfa.EVERYONE)
        signed_in = _signed_in(committed_sessions, sign_in)
        assert signed_in.client.get(_ELSEWHERE).status_code == 403
        with committed_sessions() as db:
            make_mfa(db, signed_in.user)
            db.commit()

        assert signed_in.client.get(_ELSEWHERE).status_code == 200


class TestWhatAnUnenrolledAccountMayStillDo:
    def _unenrolled(self, committed_sessions, sign_in):
        _require(committed_sessions, _RequireMfa.EVERYONE)
        return _signed_in(committed_sessions, sign_in).client

    def test_it_can_read_its_profile_and_mfa_status_and_start_and_finish_an_enrolment(
        self, committed_sessions, sign_in
    ):
        client = self._unenrolled(committed_sessions, sign_in)

        assert client.get(f"{_ROOT}/profile").status_code == 200
        assert client.get(f"{_ROOT}/profile/mfa/status").status_code == 200
        assert client.post(f"{_ROOT}/profile/mfa/setup").status_code == 201
        assert client.get(f"{_ROOT}/profile/identity-providers").status_code == 200

    def test_enable_is_reached_and_answers_for_itself_not_with_the_enrolment_refusal(self, committed_sessions, sign_in):
        client = self._unenrolled(committed_sessions, sign_in)

        response = client.post(
            f"{_ROOT}/profile/mfa/enable", json={"totp_code": "123456", "step_up": {"current_password": "x"}}
        )

        assert response.json()["type"] != _ENROLMENT_REQUIRED

    def test_the_identity_provider_step_up_is_reached(self, committed_sessions, sign_in):
        client = self._unenrolled(committed_sessions, sign_in)

        response = client.post(
            f"{_ROOT}/profile/identity-providers/{'0' * 8}-0000-4000-8000-{'0' * 12}/step-up",
            json={"code_challenge": "c" * 43, "action": "mfa_disable", "redirect": "/"},
        )

        assert response.json()["type"] != _ENROLMENT_REQUIRED

    def test_the_exemption_is_the_method_and_the_route_not_the_path_alone(self, committed_sessions, sign_in):
        client = self._unenrolled(committed_sessions, sign_in)

        assert client.get(f"{_ROOT}/profile/mfa/backup-codes/status").status_code == 403
        assert client.post(f"{_ROOT}/profile/mfa/disable", json={"step_up": {}}).status_code == 403

    def test_the_exempt_set_is_exactly_what_the_enrolment_page_needs(self):
        needed = {
            ("GET", "/profile"),
            ("GET", "/profile/mfa/status"),
            ("POST", "/profile/mfa/setup"),
            ("POST", "/profile/mfa/enable"),
            ("GET", "/profile/identity-providers"),
            ("POST", "/profile/identity-providers/{idp_id}/step-up"),
        }

        assert set(auth_constants.MFA_ENROLMENT_ROUTES) == needed


class TestTheRefusalIsAudited:
    def _rows(self, committed_sessions):
        return audit_rows(committed_sessions, authentication_audit_actions.MFA_ENROLMENT_DENIED)

    def test_a_refusal_writes_a_denied_row_without_any_credential_value(self, committed_sessions, sign_in):
        _require(committed_sessions, _RequireMfa.EVERYONE)
        signed_in = _signed_in(committed_sessions, sign_in)

        signed_in.client.get(_ELSEWHERE)

        (row,) = self._rows(committed_sessions)
        assert (row.outcome, row.actor_id, row.details) == (
            "denied",
            str(signed_in.user.id),
            {"credential_type": "access_token"},
        )
        assert signed_in.access_token not in str(row.__dict__)

    def test_a_client_retrying_in_the_same_session_is_audited_once(self, committed_sessions, sign_in):
        _require(committed_sessions, _RequireMfa.EVERYONE)
        signed_in = _signed_in(committed_sessions, sign_in)

        for _ in range(3):
            assert signed_in.client.get(_ELSEWHERE).status_code == 403

        assert len(self._rows(committed_sessions)) == 1

    def test_another_session_is_audited_on_its_own(self, committed_sessions, sign_in):
        _require(committed_sessions, _RequireMfa.EVERYONE)
        first = _signed_in(committed_sessions, sign_in)
        second = sign_in(first.user)

        first.client.get(_ELSEWHERE)
        second.client.get(_ELSEWHERE)

        assert len(self._rows(committed_sessions)) == 2

    def test_an_account_that_need_not_enrol_writes_nothing(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)

        signed_in.client.get(_ELSEWHERE)

        assert self._rows(committed_sessions) == []

    def test_an_unreachable_state_store_still_audits_the_refusal(self, committed_sessions, sign_in, monkeypatch):
        _require(committed_sessions, _RequireMfa.EVERYONE)
        signed_in = _signed_in(committed_sessions, sign_in)

        def down(*_args, **_kwargs):
            raise platform_providers.StateBackendUnavailableError("down")

        monkeypatch.setattr(jasil_runtime.get_active_platform().state, "set_if_absent", down)

        response = signed_in.client.get(_ELSEWHERE)

        assert response.status_code == 403
        assert len(self._rows(committed_sessions)) == 1
