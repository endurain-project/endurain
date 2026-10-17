"""Tests for core.rate_limit — rate-limit bucket key and 429 handler."""

from unittest.mock import MagicMock, patch


class TestRateLimitConstants:
    """Tests for rate-limit tier constants."""

    def test_default_constant(self):
        from core.rate_limit import DEFAULT

        assert DEFAULT == "120/minute"

    def test_write_constant(self):
        from core.rate_limit import WRITE

        assert WRITE == "30/minute"

    def test_sensitive_constant(self):
        from core.rate_limit import SENSITIVE

        assert SENSITIVE == "10/minute"


class TestGetRateLimitKey:
    """Tests for _get_rate_limit_key."""

    def test_bearer_token_returns_hashed_key(self):
        from core.rate_limit import _get_rate_limit_key

        request = MagicMock()
        request.headers = {"authorization": "Bearer my-secret-token-12345"}

        result = _get_rate_limit_key(request)

        assert result.startswith("user:")
        assert len(result) == 16 + 5  # "user:" + 16 hex chars

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
        call_args = mock_log.warning.call_args[0]
        assert "Rate limit exceeded" in call_args[0]
        assert "10.0.0.1" in call_args[0]

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
