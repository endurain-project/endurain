"""The opt-in breached-password check against the Have I Been Pwned range API, faked at the HTTP boundary."""

import hashlib
import logging

import httpx2
import pytest

import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.credentials.password_breach as credentials_password_breach
import modules.users.users.crud as users_crud
from tests._factories.breach import fake_range_api
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_PASSWORD = "correct horse battery staple"
_DIGEST = hashlib.sha1(_PASSWORD.encode(), usedforsecurity=False).hexdigest().upper()
_PREFIX = _DIGEST[:5]


@pytest.fixture
def range_api(monkeypatch):
    return fake_range_api(monkeypatch)


class TestIsBreached:
    def test_a_password_the_api_lists_is_breached(self, range_api):
        range_api.breach(_PASSWORD)

        assert credentials_password_breach.is_breached(_PASSWORD) is True

    def test_a_password_the_api_does_not_list_is_allowed(self, range_api):
        assert credentials_password_breach.is_breached(_PASSWORD) is False

    def test_a_padding_entry_with_a_count_of_zero_is_not_a_breach(self, monkeypatch):
        api = fake_range_api(monkeypatch)
        api.fail_with(lambda request: httpx2.Response(200, text=f"{_DIGEST[5:]}:0\r\n", request=request))

        assert credentials_password_breach.is_breached(_PASSWORD) is False

    def test_only_the_five_character_prefix_leaves_the_server(self, range_api):
        credentials_password_breach.is_breached(_PASSWORD)

        (request,) = range_api.requests
        assert str(request.url) == f"{credentials_password_breach.RANGE_API_URL}{_PREFIX}"
        assert request.headers["Add-Padding"] == "true"
        assert range_api.options == [
            {"timeout": credentials_password_breach.REQUEST_TIMEOUT_SECONDS, "follow_redirects": False}
        ]
        assert _PASSWORD not in repr(request) and _DIGEST[5:] not in repr(request)

    def test_the_password_is_hashed_in_its_nfc_form(self, range_api):
        decomposed = "café-au-lait-noir"
        composed = "café-au-lait-noir"
        range_api.breach(composed)

        assert credentials_password_breach.is_breached(decomposed) is True

    @pytest.mark.parametrize(
        "failure",
        [
            pytest.param(lambda request: (_ for _ in ()).throw(httpx2.ReadTimeout("slow")), id="timeout"),
            pytest.param(lambda request: (_ for _ in ()).throw(httpx2.ConnectError("down")), id="unreachable"),
            pytest.param(lambda request: httpx2.Response(503, request=request), id="service-error"),
        ],
    )
    def test_a_failing_service_allows_the_password_and_warns_without_leaking_it(self, range_api, failure, caplog):
        range_api.fail_with(failure)

        with caplog.at_level(logging.WARNING):
            assert credentials_password_breach.is_breached(_PASSWORD) is False

        assert any(record.levelno == logging.WARNING for record in caplog.records)
        logged = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
        assert _PASSWORD not in logged and _DIGEST not in logged and _PREFIX not in logged


class TestRejectBreachedPassword:
    def test_a_breached_password_is_refused_after_the_open_transaction_ends(self, db, range_api):
        range_api.breach(_PASSWORD)
        settings = edit_server_settings(db, password_breach_check_enabled=True)
        in_transaction_at_request = []
        range_api.on_request(lambda: in_transaction_at_request.append(db.in_transaction()))
        user = make_user(db)

        with pytest.raises(credentials_contracts.PasswordBreachedError):
            credentials_integration.reject_breached_password(settings, _PASSWORD, db)

        assert in_transaction_at_request == [False]
        assert users_crud.get_user_by_id(user.id, db) is None

    def test_a_password_that_is_not_breached_is_allowed(self, db, range_api):
        settings = edit_server_settings(db, password_breach_check_enabled=True)

        credentials_integration.reject_breached_password(settings, _PASSWORD, db)

        assert len(range_api.requests) == 1

    def test_with_the_check_off_nothing_is_sent_and_the_transaction_stays_open(self, db, range_api):
        range_api.breach(_PASSWORD)
        settings = edit_server_settings(db, password_breach_check_enabled=False)
        user = make_user(db)

        credentials_integration.reject_breached_password(settings, _PASSWORD, db)

        assert range_api.requests == []
        assert users_crud.get_user_by_id(user.id, db) is not None
