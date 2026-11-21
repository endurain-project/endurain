"""Tests for core.rate_limit: the bucket key, the 429 answer, the store outage fallback and the store options."""

import logging
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from joserfc import jwt
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request as StarletteRequest

import core.exceptions as core_exceptions
import core.jwt_keys as core_jwt_keys
import core.logger as core_logger
import core.rate_limit as core_rate_limit

_ACCESS_HEADER = {"alg": "HS256", "typ": core_jwt_keys.ACCESS_JWT_TYP}


def _claims(*, sub="1", exp_delta=300, **extra):
    claims = {"exp": int(time.time()) + exp_delta, **extra}
    if sub is not None:
        claims["sub"] = sub
    return claims


def _token(claims, header=None, key=None) -> str:
    """Sign a token with the application's own access key unless another is given."""
    key = key or core_jwt_keys.SIGNING_KEYS[0]
    header = {**(header or _ACCESS_HEADER), "kid": core_jwt_keys.key_id(key)}
    return jwt.encode(header, claims, core_jwt_keys.import_key(key))


def _request(authorization: str | None = None, ip: str = "10.0.0.1") -> StarletteRequest:
    """A request as the server receives it, from a client address and with an optional ``Authorization`` header."""
    headers = [(b"authorization", authorization.encode())] if authorization is not None else []
    return StarletteRequest(
        {"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (ip, 5000), "query_string": b""}
    )


class TestGetRateLimitKey:
    """The bucket a request is counted in."""

    def test_a_verified_token_is_keyed_by_its_user(self):
        request = _request(f"Bearer {_token(_claims(sub='42'))}")

        assert core_rate_limit._get_rate_limit_key(request) == "user:42"

    def test_a_refreshed_token_keeps_the_users_bucket(self):
        keys = [
            core_rate_limit._get_rate_limit_key(_request(f"Bearer {_token(_claims(sub='7', jti=jti))}"))
            for jti in ("a", "b")
        ]

        assert keys == ["user:7", "user:7"]

    def test_a_verified_token_without_a_subject_falls_back_to_the_ip(self):
        request = _request(f"Bearer {_token(_claims(sub=None))}", ip="10.0.0.4")

        assert core_rate_limit._get_rate_limit_key(request) == "10.0.0.4"

    def test_unverified_bearer_token_returns_ip(self):
        assert core_rate_limit._get_rate_limit_key(_request("Bearer random-garbage", ip="10.0.0.3")) == "10.0.0.3"

    def test_an_ipv6_caller_is_keyed_by_its_64_network(self):
        keys = [
            core_rate_limit._get_rate_limit_key(_request(ip=ip))
            for ip in ("2001:db8:1:2::1", "2001:db8:1:2:ffff::9", "2001:db8:1:3::1")
        ]

        assert keys[0] == keys[1] == "2001:db8:1:2::/64"
        assert keys[2] == "2001:db8:1:3::/64"

    def test_signed_token_is_accepted_and_tampered_rejected(self):
        token = _token(_claims(sub="1"))

        assert core_rate_limit._verified_subject(token) == "1"
        assert core_rate_limit._verified_subject(token[:-2] + "xx") is None
        assert core_rate_limit._verified_subject("not-a-jwt") is None

    @pytest.mark.parametrize(
        ("header", "claims"),
        [
            (_ACCESS_HEADER, _claims(exp_delta=-core_jwt_keys.CLOCK_LEEWAY_SECONDS - 300)),
            ({"alg": "HS256", "typ": "rt+jwt"}, _claims()),
            (_ACCESS_HEADER, {"sub": "1"}),
            ({"alg": "HS256"}, _claims()),
        ],
        ids=["expired", "refresh-token", "no-expiry", "no-type"],
    )
    def test_a_token_that_is_not_a_live_access_token_gets_no_user_bucket(self, header, claims):
        assert core_rate_limit._verified_subject(_token(claims, header)) is None

    def test_a_token_that_expired_within_the_clock_leeway_still_names_its_user(self):
        assert core_rate_limit._verified_subject(_token(_claims(exp_delta=-5))) == "1"

    def test_a_refresh_token_typed_as_an_access_token_gets_no_user_bucket(self):
        """Only access keys name a bucket, so a refresh token cannot pass by forging its ``typ``."""
        token = _token(_claims(), key=core_jwt_keys.REFRESH_SIGNING_KEYS[0])

        assert core_rate_limit._verified_subject(token) is None

    def test_no_auth_header_returns_ip(self):
        assert core_rate_limit._get_rate_limit_key(_request(ip="10.0.0.1")) == "10.0.0.1"

    def test_non_bearer_auth_returns_ip(self):
        assert core_rate_limit._get_rate_limit_key(_request("Basic dXNlcjpwYXNz", ip="10.0.0.2")) == "10.0.0.2"


def _limited_app(limit: str, *, limiter=None) -> tuple[TestClient, object]:
    """An application with one limited route, wired as ``main.create_app`` wires the limiter."""
    limiter = limiter or core_rate_limit.build_limiter(storage_uri="memory://", enabled=True)
    app = FastAPI()
    app.state.limiter = limiter
    core_exceptions.register_sync_handler(app, RateLimitExceeded, core_rate_limit.rate_limit_exceeded_handler)
    app.add_middleware(core_rate_limit.RateLimitMiddleware)

    @app.get("/limited")
    @limiter.limit(limit)
    def limited(request: Request) -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app), limiter


@pytest.fixture
def app_log(caplog):
    """Capture the application's logger, which does not propagate to the root logger."""
    logger = logging.getLogger(core_logger.ROOT_LOGGER_NAME)
    level = logger.level
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.DEBUG)
    yield caplog
    logger.setLevel(level)
    logger.removeHandler(caplog.handler)


class TestRateLimitExceededHandler:
    """The 429 a caller past its limit is answered with."""

    def test_the_answer_is_a_problem_document_with_the_back_off_headers_of_the_breached_limit(self):
        client, _ = _limited_app("2/minute")
        for _ in range(2):
            client.get("/limited")

        response = client.get("/limited")

        assert response.status_code == 429
        assert response.headers["content-type"].startswith("application/problem+json")
        problem = response.json()
        assert problem["type"] == "urn:endurain:error:too-many-requests"
        assert problem["scope"] == "requests"
        assert 1 <= int(response.headers["Retry-After"]) <= 60
        assert response.headers["X-RateLimit-Limit"] == "2"
        assert response.headers["X-RateLimit-Remaining"] == "0"

    def test_the_breach_is_logged_once_with_the_caller_the_method_and_the_path(self, app_log):
        client, _ = _limited_app("1/minute")
        client.get("/limited")

        client.get("/limited")

        records = {
            id(r): r
            for r in app_log.records
            if r.name.endswith("core.rate_limit") and r.getMessage() == "Rate limit exceeded"
        }.values()
        (record,) = records
        assert record.levelname == "WARNING"
        fields = record.__dict__
        assert fields["caller"] == "testclient"
        assert (fields["method"], fields["path"]) == ("GET", "/limited")


class TestHandlerWithoutAWindowRecord:
    """A refusal that carries no record of the counter it hit still tells the caller how long to wait."""

    @staticmethod
    def _limit():
        from limits import parse
        from slowapi.wrappers import Limit

        return Limit(
            limit=parse("30/minute"),
            key_func=lambda request: "10.0.0.1",
            scope=None,
            per_method=False,
            methods=None,
            error_message=None,
            exempt_when=None,
            cost=1,
            override_defaults=False,
        )

    def test_the_whole_window_is_the_wait_when_the_request_names_no_counter(self):
        response = core_rate_limit.rate_limit_exceeded_handler(_request(), RateLimitExceeded(self._limit()))

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"

    def test_a_refusal_that_names_no_limit_carries_no_back_off_headers(self):
        from starlette.exceptions import HTTPException

        class Unlimited(RateLimitExceeded):
            def __init__(self) -> None:
                HTTPException.__init__(self, status_code=429)

        response = core_rate_limit.rate_limit_exceeded_handler(_request(), Unlimited())

        assert response.status_code == 429
        assert "Retry-After" not in response.headers
        assert "X-RateLimit-Limit" not in response.headers


class TestRetryAfterIsTheTimeLeftInTheWindow:
    """``Retry-After`` counts down with the window instead of repeating its whole length."""

    def test_a_caller_late_in_the_window_is_told_the_seconds_that_remain(self, monkeypatch):
        client, _ = _limited_app("2/minute")
        assert [client.get("/limited").status_code for _ in range(2)] == [200, 200]
        started = time.time()
        monkeypatch.setattr(core_rate_limit, "time", SimpleNamespace(time=lambda: started + 40))

        response = client.get("/limited")

        assert response.status_code == 429
        assert 19 <= int(response.headers["Retry-After"]) <= 21


def _store_down(monkeypatch, limiter) -> None:
    """Make the shared counter store refuse every hit, as an unreachable Redis does."""

    def down(*args, **kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(limiter._limiter, "hit", down)


class TestStorageOutageFallback:
    """A state backend outage degrades the limiter to per-process counters instead of failing requests."""

    @staticmethod
    def _client(limit: str):
        return _limited_app(limit)

    def test_a_failing_storage_does_not_fail_the_request(self, monkeypatch, app_log):
        client, limiter = self._client("5/minute")
        _store_down(monkeypatch, limiter)

        response = client.get("/limited")

        assert response.status_code == 200
        assert "falling back to in-memory storage" in app_log.text

    def test_the_limit_still_applies_per_process_during_the_outage(self, monkeypatch):
        client, limiter = self._client("2/minute")
        _store_down(monkeypatch, limiter)

        statuses = [client.get("/limited").status_code for _ in range(4)]

        assert statuses == [200, 200, 429, 429]


class TestRateLimitMiddleware:
    """The default-limit check runs off the event loop, with unchanged limiting behaviour."""

    @staticmethod
    def _app(monkeypatch, default: str = "2/minute"):
        import threading

        from fastapi import APIRouter

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
        core_exceptions.register_sync_handler(app, RateLimitExceeded, core_rate_limit.rate_limit_exceeded_handler)
        app.add_middleware(core_rate_limit.RateLimitMiddleware)

        # Routes live on an included router, as in the real application, where ``app.routes`` holds the router
        # wrapper rather than its routes.
        router = APIRouter()

        @router.get("/open")
        async def open_route() -> dict[str, str]:
            threads["loop"].add(threading.get_ident())
            return {"ok": "yes"}

        @router.get("/{rest:path}")
        async def catch_all(rest: str) -> dict[str, str]:
            return {"rest": rest}

        app.include_router(router)

        return app, limiter, threads

    def test_the_check_does_not_run_on_the_event_loop_thread(self, monkeypatch):
        app, _, threads = self._app(monkeypatch)
        assert TestClient(app).get("/open").status_code == 200

        assert threads["check"]
        assert threads["loop"]
        assert threads["check"].isdisjoint(threads["loop"])

    def test_the_default_limit_still_answers_429_with_retry_after(self, monkeypatch):
        app, _, _ = self._app(monkeypatch)
        client = TestClient(app)
        responses = [client.get("/open") for _ in range(3)]

        assert [r.status_code for r in responses] == [200, 200, 429]
        assert responses[2].headers["Retry-After"]
        assert responses[2].json()["title"] == "Too Many Requests"

    def test_a_failing_store_falls_back_to_memory_and_keeps_limiting(self, monkeypatch):
        app, limiter, _ = self._app(monkeypatch)
        client = TestClient(app)
        _store_down(monkeypatch, limiter)
        statuses = [client.get("/open").status_code for _ in range(3)]

        assert statuses == [200, 200, 429]

    def test_a_redis_store_fails_fast_instead_of_waiting_forever(self):
        limiter = core_rate_limit.build_limiter(storage_uri="redis://localhost:6399/0", enabled=True)
        kwargs = limiter._storage.storage.connection_pool.connection_kwargs

        assert kwargs["socket_connect_timeout"] == core_rate_limit.STORE_TIMEOUT_SECONDS
        assert kwargs["socket_timeout"] == core_rate_limit.STORE_TIMEOUT_SECONDS

    @pytest.mark.parametrize(
        "uri",
        ["rediss://:secret@cache.example:6380/1?ssl_cert_reqs=none", "unix:///run/redis.sock?db=2"],
        ids=["rediss", "unix"],
    )
    def test_every_redis_scheme_carries_the_store_timeouts(self, uri):
        query = parse_qs(urlsplit(core_rate_limit.with_store_timeouts(uri)).query)

        assert (
            query["socket_connect_timeout"] == query["socket_timeout"] == [str(core_rate_limit.STORE_TIMEOUT_SECONDS)]
        )

    def test_the_rest_of_a_redis_uri_is_kept(self):
        uri = core_rate_limit.with_store_timeouts("rediss://:secret@cache.example:6380/1?ssl_cert_reqs=none")

        assert uri.startswith("rediss://:secret@cache.example:6380/1?ssl_cert_reqs=none&")

    def test_a_timeout_the_operator_set_wins(self):
        query = parse_qs(urlsplit(core_rate_limit.with_store_timeouts("redis://cache:6379/0?socket_timeout=5")).query)

        assert query["socket_timeout"] == ["5"]
        assert query["socket_connect_timeout"] == [str(core_rate_limit.STORE_TIMEOUT_SECONDS)]

    def test_an_in_memory_store_is_left_as_it_is(self):
        assert core_rate_limit.with_store_timeouts("memory://") == "memory://"
