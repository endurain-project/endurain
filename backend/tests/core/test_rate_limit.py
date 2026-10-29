"""Tests for core.rate_limit — rate-limit bucket key and 429 handler."""

import time
from unittest.mock import MagicMock, patch

import pytest


class TestRateLimitConstants:
    """Tests for rate-limit tier constants."""

    def test_default_constant(self):
        from core.rate_limit import DEFAULT

        assert DEFAULT == "120/minute"

    def test_write_constant(self):
        from core.rate_limit import WRITE

        assert WRITE == "30/minute"

    def test_expensive_read_constant(self):
        from core.rate_limit import DEFAULT, EXPENSIVE_READ, WRITE

        assert EXPENSIVE_READ == "30/minute"
        assert EXPENSIVE_READ != DEFAULT
        assert EXPENSIVE_READ == WRITE

    def test_public_read_starts_at_the_default(self):
        from core.rate_limit import DEFAULT, PUBLIC_READ

        assert PUBLIC_READ == DEFAULT

    def test_expensive_public_read_constant(self):
        from core.rate_limit import DEFAULT, EXPENSIVE_PUBLIC_READ, EXPENSIVE_READ

        assert EXPENSIVE_PUBLIC_READ == "30/minute"
        assert EXPENSIVE_PUBLIC_READ != DEFAULT
        assert EXPENSIVE_PUBLIC_READ == EXPENSIVE_READ

    def test_sensitive_constant(self):
        from core.rate_limit import SENSITIVE

        assert SENSITIVE == "10/minute"


def _claims(*, sub="1", typ="access", exp_delta=300, **extra):
    claims = {"typ": typ, "exp": int(time.time()) + exp_delta, **extra}
    if sub is not None:
        claims["sub"] = sub
    return claims


class TestGetRateLimitKey:
    """Tests for _get_rate_limit_key."""

    def test_a_verified_token_is_keyed_by_its_user(self):
        from core.rate_limit import _get_rate_limit_key

        request = MagicMock()
        request.headers = {"authorization": "Bearer my-secret-token-12345"}

        with patch("core.rate_limit._verified_subject", return_value="42"):
            result = _get_rate_limit_key(request)

        assert result == "user:42"

    def test_a_refreshed_token_keeps_the_users_bucket(self):
        from joserfc import jwt
        from joserfc.jwk import OctKey

        import core.rate_limit as rl

        key = OctKey.import_key("k" * 32)
        first = jwt.encode({"alg": "HS256"}, _claims(sub="7", jti="a"), key)
        second = jwt.encode({"alg": "HS256"}, _claims(sub="7", jti="b"), key)
        keys = []
        with patch("core.rate_limit._jwt_verification_key", return_value=key):
            for token in (first, second):
                request = MagicMock()
                request.headers = {"authorization": f"Bearer {token}"}
                keys.append(rl._get_rate_limit_key(request))

        assert keys == ["user:7", "user:7"]

    def test_a_verified_token_without_a_subject_falls_back_to_the_ip(self):
        from joserfc import jwt
        from joserfc.jwk import OctKey

        import core.rate_limit as rl

        key = OctKey.import_key("k" * 32)
        token = jwt.encode({"alg": "HS256"}, _claims(sub=None), key)
        request = MagicMock()
        request.headers = {"authorization": f"Bearer {token}"}

        with (
            patch("core.rate_limit._jwt_verification_key", return_value=key),
            patch("core.rate_limit.core_network.get_ip_address", return_value="10.0.0.4"),
        ):
            assert rl._get_rate_limit_key(request) == "10.0.0.4"

    def test_unverified_bearer_token_returns_ip(self):
        from core.rate_limit import _get_rate_limit_key

        request = MagicMock()
        request.headers = {"authorization": "Bearer random-garbage"}

        with patch("core.rate_limit.core_network.get_ip_address", return_value="10.0.0.3"):
            result = _get_rate_limit_key(request)

        assert result == "10.0.0.3"

    def test_signed_token_is_accepted_and_tampered_rejected(self):
        from joserfc import jwt
        from joserfc.jwk import OctKey

        import core.rate_limit as rl

        key = OctKey.import_key("k" * 32)
        token = jwt.encode({"alg": "HS256"}, _claims(sub="1"), key)
        with patch("core.rate_limit._jwt_verification_key", return_value=key):
            assert rl._verified_subject(token) == "1"
            assert rl._verified_subject(token[:-2] + "xx") is None
            assert rl._verified_subject("not-a-jwt") is None

    @pytest.mark.parametrize(
        "claims",
        [
            _claims(exp_delta=-60),
            _claims(typ="refresh"),
            {"sub": "1", "typ": "access"},
            {"sub": "1", "exp": int(time.time()) + 300},
        ],
        ids=["expired", "refresh-token", "no-expiry", "no-type"],
    )
    def test_a_token_that_is_not_a_live_access_token_gets_no_user_bucket(self, claims):
        from joserfc import jwt
        from joserfc.jwk import OctKey

        import core.rate_limit as rl

        key = OctKey.import_key("k" * 32)
        token = jwt.encode({"alg": "HS256"}, claims, key)
        with patch("core.rate_limit._jwt_verification_key", return_value=key):
            assert rl._verified_subject(token) is None

    def test_no_auth_header_returns_ip(self):
        from core.rate_limit import _get_rate_limit_key

        request = MagicMock()
        request.headers = {}

        with patch("core.rate_limit.core_network.get_ip_address", return_value="10.0.0.1"):
            result = _get_rate_limit_key(request)

        assert result == "10.0.0.1"

    def test_non_bearer_auth_returns_ip(self):
        from core.rate_limit import _get_rate_limit_key

        request = MagicMock()
        request.headers = {"authorization": "Basic dXNlcjpwYXNz"}

        with patch("core.rate_limit.core_network.get_ip_address", return_value="10.0.0.2"):
            result = _get_rate_limit_key(request)

        assert result == "10.0.0.2"


class TestRateLimitExceededHandler:
    """Tests for rate_limit_exceeded_handler."""

    def test_returns_json_429_response(self):
        from starlette.responses import JSONResponse

        from core.rate_limit import rate_limit_exceeded_handler

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/test"
        mock_limiter = MagicMock()
        mock_limiter._inject_headers.side_effect = lambda resp, *a: resp
        request.app.state.limiter = mock_limiter
        request.state.view_rate_limit = "120/minute"

        exc = MagicMock()

        with patch("core.rate_limit.logger"):
            response = rate_limit_exceeded_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 429

    def test_logs_warning_on_rate_limit(self):
        from core.rate_limit import rate_limit_exceeded_handler

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/test"
        request.headers = {}
        request.app.state.limiter._inject_headers = MagicMock()
        request.state.view_rate_limit = "120/minute"

        exc = MagicMock()

        with (
            patch("core.rate_limit.core_network.get_ip_address", return_value="10.0.0.1"),
            patch("core.rate_limit.logger") as mock_log,
        ):
            rate_limit_exceeded_handler(request, exc)

        assert len(mock_log.method_calls) == 1
        assert mock_log.warning.call_args[0] == ("Rate limit exceeded",)
        fields = mock_log.warning.call_args.kwargs["extra"]
        assert fields["caller"] == "10.0.0.1"
        assert (fields["method"], fields["path"]) == ("GET", "/api/v1/test")

    def test_header_injection_failure_caught(self):
        from core.rate_limit import rate_limit_exceeded_handler

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/test"
        request.headers = {}
        request.app.state.limiter._inject_headers = MagicMock(side_effect=RuntimeError("boom"))
        request.state.view_rate_limit = "120/minute"

        exc = MagicMock()

        with patch("core.rate_limit.logger"):
            response = rate_limit_exceeded_handler(request, exc)

        assert response.status_code == 429


class TestStorageOutageFallback:
    """A state backend outage degrades the limiter to per-process counters instead of failing requests."""

    @staticmethod
    def _client(limit: str):
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient
        from slowapi.errors import RateLimitExceeded

        from core.rate_limit import RateLimitMiddleware, build_limiter, rate_limit_exceeded_handler

        limiter = build_limiter(storage_uri="memory://", enabled=True)
        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
        app.add_middleware(RateLimitMiddleware)

        @app.get("/limited")
        @limiter.limit(limit)
        def limited(request: Request) -> dict[str, str]:
            return {"ok": "yes"}

        return TestClient(app), limiter

    def test_a_failing_storage_does_not_fail_the_request(self, caplog):
        client, limiter = self._client("5/minute")
        with (
            patch.object(limiter._limiter, "hit", side_effect=ConnectionError("redis down")),
            caplog.at_level("WARNING"),
        ):
            response = client.get("/limited")

        assert response.status_code == 200
        assert "falling back to in-memory storage" in caplog.text

    def test_the_limit_still_applies_per_process_during_the_outage(self):
        client, limiter = self._client("2/minute")
        with patch.object(limiter._limiter, "hit", side_effect=ConnectionError("redis down")):
            statuses = [client.get("/limited").status_code for _ in range(4)]

        assert statuses == [200, 200, 429, 429]


class TestRateLimitMiddleware:
    """The default-limit check runs off the event loop, with unchanged limiting behaviour."""

    @staticmethod
    def _app(monkeypatch, default: str = "2/minute"):
        import threading

        from fastapi import FastAPI
        from slowapi.errors import RateLimitExceeded

        import core.rate_limit as core_rate_limit

        monkeypatch.setattr(core_rate_limit, "DEFAULT", default)
        limiter = core_rate_limit.build_limiter(storage_uri="memory://", enabled=True)
        threads: dict[str, set[int]] = {"check": set(), "loop": set()}
        original = limiter._check_request_limit

        def recording_check(*args, **kwargs):
            threads["check"].add(threading.get_ident())
            return original(*args, **kwargs)

        monkeypatch.setattr(limiter, "_check_request_limit", recording_check)

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, core_rate_limit.rate_limit_exceeded_handler)
        app.add_middleware(core_rate_limit.RateLimitMiddleware)

        @app.get("/open")
        async def open_route() -> dict[str, str]:
            threads["loop"].add(threading.get_ident())
            return {"ok": "yes"}

        return app, limiter, threads

    def test_the_check_does_not_run_on_the_event_loop_thread(self, monkeypatch):
        from fastapi.testclient import TestClient

        app, _, threads = self._app(monkeypatch)
        assert TestClient(app).get("/open").status_code == 200

        assert threads["check"]
        assert threads["loop"]
        assert threads["check"].isdisjoint(threads["loop"])

    def test_the_default_limit_still_answers_429_with_retry_after(self, monkeypatch):
        from fastapi.testclient import TestClient

        app, _, _ = self._app(monkeypatch)
        client = TestClient(app)
        responses = [client.get("/open") for _ in range(3)]

        assert [r.status_code for r in responses] == [200, 200, 429]
        assert responses[2].headers["Retry-After"]
        assert responses[2].json()["title"] == "Too Many Requests"

    def test_a_failing_store_falls_back_to_memory_and_keeps_limiting(self, monkeypatch):
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        app, limiter, _ = self._app(monkeypatch)
        client = TestClient(app)
        with patch.object(limiter._limiter, "hit", side_effect=ConnectionError("redis down")):
            statuses = [client.get("/open").status_code for _ in range(3)]

        assert statuses == [200, 200, 429]

    def test_a_redis_store_fails_fast_instead_of_waiting_forever(self):
        import core.rate_limit as core_rate_limit

        limiter = core_rate_limit.build_limiter(storage_uri="redis://localhost:6399/0", enabled=True)
        kwargs = limiter._storage.storage.connection_pool.connection_kwargs

        assert kwargs["socket_connect_timeout"] == core_rate_limit.STORE_TIMEOUT_SECONDS
        assert kwargs["socket_timeout"] == core_rate_limit.STORE_TIMEOUT_SECONDS
