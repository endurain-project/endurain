"""The browser legs of an SSO flow: starting a login, accepting the callback and finishing it.

The routes only translate HTTP; these tests cover the decisions that used to sit in them.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.utils as idp_utils
from modules.auth.identity_providers.service import IdentityProviderService

HOST = "https://app.example.com"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
ALLOWED = {"gadgetbridge"}


@pytest.fixture
def service():
    return IdentityProviderService(MagicMock(), HOST, "test")


def _idp(enabled=True, **overrides):
    values = {"id": 1, "slug": "test", "name": "Test", "enabled": enabled}
    values.update(overrides)
    return SimpleNamespace(**values)


class TestAppendQueryParams:
    def test_appends_to_path_without_query(self):
        assert idp_utils.append_query_params("/settings/security", {"idp_link": "success"}) == (
            "/settings/security?idp_link=success"
        )

    def test_preserves_existing_query(self):
        assert idp_utils.append_query_params("/settings?tab=security", {"idp_link": "success"}) == (
            "/settings?tab=security&idp_link=success"
        )

    def test_url_encodes_values(self):
        assert idp_utils.append_query_params("/settings/security", {"idp_name": "My IdP"}) == (
            "/settings/security?idp_name=My+IdP"
        )


class TestBuildLinkResultUrl:
    def test_default_path_when_no_return_path(self):
        assert idp_utils.build_link_result_url(HOST, None, "Google", success=True) == (
            f"{HOST}/settings/security?idp_link=success&idp_name=Google"
        )

    def test_honors_relative_return_path(self):
        assert idp_utils.build_link_result_url(HOST, "/settings/security", "Google", success=True) == (
            f"{HOST}/settings/security?idp_link=success&idp_name=Google"
        )

    def test_custom_scheme_is_not_host_prefixed(self):
        assert idp_utils.build_link_result_url(HOST, "gadgetbridge://callback", "Google", success=True) == (
            "gadgetbridge://callback?idp_link=success&idp_name=Google"
        )

    def test_error_omits_idp_name(self):
        assert idp_utils.build_link_result_url(HOST, "/settings/security", None, success=False) == (
            f"{HOST}/settings/security?idp_link=error"
        )

    def test_error_falls_back_to_default_path(self):
        assert idp_utils.build_link_result_url(HOST, None, None, success=False) == (
            f"{HOST}/settings/security?idp_link=error"
        )


class TestBeginLogin:
    def _begin(self, service, *, idp=None, challenge=CHALLENGE, method="S256", redirect=None, header=None):
        with (
            patch.object(service, "get_identity_provider_by_slug", return_value=idp),
            patch.object(service, "create_login_oauth_state", return_value="state-id") as create_state,
            patch.object(service, "initiate_login", return_value="https://provider.example/auth") as initiate,
        ):
            url = service.begin_login("test", challenge, method, redirect, "10.0.0.1", header, ALLOWED, MagicMock())
        return url, create_state, initiate

    def test_an_unknown_provider_is_not_found(self, service):
        with pytest.raises(core_exceptions.NotFoundError):
            self._begin(service, idp=None)

    def test_a_disabled_provider_is_not_found(self, service):
        with pytest.raises(core_exceptions.NotFoundError):
            self._begin(service, idp=_idp(enabled=False))

    @pytest.mark.parametrize(("challenge", "method"), [("", "S256"), (CHALLENGE, ""), (CHALLENGE, "plain")])
    def test_pkce_is_mandatory_and_s256(self, service, challenge, method):
        with pytest.raises(core_exceptions.InvalidInputError):
            self._begin(service, idp=_idp(), challenge=challenge, method=method)

    def test_a_malformed_challenge_is_refused(self, service):
        with pytest.raises(core_exceptions.DomainError):
            self._begin(service, idp=_idp(), challenge="short")

    def test_a_redirect_that_leaves_the_app_is_refused(self, service):
        with pytest.raises(core_exceptions.InvalidInputError):
            self._begin(service, idp=_idp(), redirect="https://evil.example/")

    def test_a_valid_request_returns_the_authorization_url(self, service):
        url, create_state, initiate = self._begin(service, idp=_idp(), redirect="/dashboard")

        assert url == "https://provider.example/auth"
        assert create_state.call_args.kwargs["redirect_path"] == "/dashboard"
        assert create_state.call_args.kwargs["ip_address"] == "10.0.0.1"
        assert initiate.call_args.kwargs["oauth_state_id"] == "state-id"

    @pytest.mark.parametrize(("header", "expected"), [(None, "web"), ("mobile", "mobile"), ("desktop", "web")])
    def test_the_client_type_comes_from_the_header_and_defaults_to_web(self, service, header, expected):
        _, create_state, _ = self._begin(service, idp=_idp(), header=header)

        assert create_state.call_args.kwargs["client_type"] == expected

    def test_a_custom_scheme_redirect_means_a_mobile_client(self, service):
        _, create_state, _ = self._begin(service, idp=_idp(), redirect="gadgetbridge://done", header="web")

        assert create_state.call_args.kwargs["client_type"] == "mobile"


class TestPrepareCallback:
    def _prepare(self, service, *, idp, oauth_state, claimed=True):
        with (
            patch.object(service, "get_identity_provider_by_slug", return_value=idp),
            patch.object(service, "get_unused_oauth_state", return_value=oauth_state),
            patch.object(service, "claim_oauth_state", return_value=claimed),
        ):
            return service.prepare_callback("test", "state-id", MagicMock())

    def test_an_unknown_or_disabled_provider_is_not_found(self, service):
        for idp in (None, _idp(enabled=False)):
            with pytest.raises(core_exceptions.NotFoundError):
                self._prepare(service, idp=idp, oauth_state=SimpleNamespace(idp_id=1, client_type="web"))

    def test_an_unknown_state_is_refused(self, service):
        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired OAuth state"):
            self._prepare(service, idp=_idp(), oauth_state=None)

    def test_a_state_issued_for_another_provider_is_refused(self, service):
        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired OAuth state"):
            self._prepare(service, idp=_idp(id=1), oauth_state=SimpleNamespace(idp_id=2, client_type="web"))

    def test_a_replayed_state_is_refused_with_the_same_message(self, service):
        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired OAuth state"):
            self._prepare(service, idp=_idp(), oauth_state=SimpleNamespace(idp_id=1, client_type="web"), claimed=False)

    def test_a_good_state_is_claimed_and_returned_with_its_provider(self, service):
        idp, oauth_state = _idp(), SimpleNamespace(idp_id=1, client_type="web")

        assert self._prepare(service, idp=idp, oauth_state=oauth_state) == (idp, oauth_state)


class TestCompleteCallback:
    def _complete(self, service, result, oauth_state, *, session_id="session-1", error=None):
        request = MagicMock()
        with (
            patch.object(service, "handle_callback", side_effect=error, return_value=result),
            patch.object(service, "create_callback_session", return_value=session_id) as create_session,
        ):
            url = service.complete_callback(_idp(), "code", "state", oauth_state, request, MagicMock(), MagicMock())
        return url, create_session

    def _state(self, **overrides):
        values = {"id": "state-id", "redirect_path": None, "user_id": None}
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_a_link_returns_to_the_originating_page_without_a_session(self, service):
        user = SimpleNamespace(username="alice")

        url, create_session = self._complete(
            service, {"user": user, "mode": "link"}, self._state(redirect_path="/settings/security", user_id=7)
        )

        assert url == f"{HOST}/settings/security?idp_link=success&idp_name=Test"
        create_session.assert_not_called()

    def test_a_login_returns_the_session_id_for_the_token_exchange(self, service):
        url, create_session = self._complete(service, {"user": SimpleNamespace(username="a")}, self._state())

        assert url == f"{HOST}/login?sso=success&session_id=session-1"
        assert create_session.call_args.args[3] == "state-id"

    def test_a_login_carries_a_relative_return_path(self, service):
        url, _ = self._complete(
            service, {"user": SimpleNamespace(username="a"), "redirect_path": "/activities?x=1"}, self._state()
        )

        assert url.endswith("&redirect=/activities%3Fx%3D1")
        assert "external_redirect" not in url

    def test_a_custom_scheme_return_path_is_flagged_for_the_native_client(self, service):
        url, _ = self._complete(
            service,
            {"user": SimpleNamespace(username="a"), "redirect_path": "gadgetbridge://done"},
            self._state(),
        )

        assert url.endswith("&external_redirect=true")

    def test_the_session_id_is_not_logged_in_the_clear(self, service, caplog):
        with caplog.at_level(logging.DEBUG):
            self._complete(service, {"user": SimpleNamespace(username="a")}, self._state(), session_id="secret-session")

        assert "secret-session" not in caplog.text

    def test_a_failed_login_returns_to_the_login_page_with_an_error(self, service):
        url, _ = self._complete(service, None, self._state(), error=core_exceptions.UpstreamError("down"))

        assert url == f"{HOST}/login?error=sso_failed"

    def test_a_failed_link_returns_to_the_originating_page_with_an_error(self, service):
        url, _ = self._complete(
            service,
            None,
            self._state(redirect_path="/settings/security", user_id=7),
            error=RuntimeError("boom"),
        )

        assert url == f"{HOST}/settings/security?idp_link=error"
