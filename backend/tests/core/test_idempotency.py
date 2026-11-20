"""Tests for ``core.idempotency``: the key grammar, the claim and result records, the dependency and the middleware."""

import asyncio
import base64
import dataclasses
import json
import threading
import time
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import jasil.runtime as platform_runtime
import pytest
from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from jasil.providers import StateBackendUnavailableError
from pydantic import BaseModel

import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.idempotency as core_idempotency

_USER = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
_OTHER_USER = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
_KEY = '"3f2b1c9e-0000-4000-8000-000000000001"'
_RAW_KEY = "3f2b1c9e-0000-4000-8000-000000000001"
_HEADERS = {"Idempotency-Key": _KEY}
_BODY = {"name": "Road bike"}


class _Thing(BaseModel):
    name: str


def _fingerprint(body: dict | None = None, path: str = "/things", query: str = "") -> str:
    return core_idempotency.request_fingerprint("POST", path, query, json.dumps(body or _BODY).encode())


def _state():
    return platform_runtime.get_state()


# ---------------------------------------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------------------------------------


class TestParseKey:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('"abc"', "abc"),
            ('"with space"', "with space"),
            ('"a\\"b"', 'a"b'),
            ('"a\\\\b"', "a\\b"),
            ('"' + "x" * 255 + '"', "x" * 255),
        ],
    )
    def test_a_quoted_string_is_accepted(self, raw, expected):
        assert core_idempotency.parse_key(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "abc",
            "3f2b1c9e-0000-4000-8000-000000000001",
            "",
            '""',
            '"' + "x" * 256 + '"',
            '"café"',
            '"a\tb"',
            '"a\x7fb"',
            '"a\\nb"',
            '"a\\"',
            '"abc',
            'abc"',
            '"abc" "def"',
            '"abc", "def"',
            '"abc";p=1',
            "?1",
            "1",
            ":YWJj:",
        ],
    )
    def test_anything_but_one_quoted_printable_string_is_refused(self, raw):
        with pytest.raises(core_exceptions.IdempotencyKeyInvalidError):
            core_idempotency.parse_key(raw)


class TestFingerprint:
    def test_key_order_and_whitespace_of_a_json_body_do_not_matter(self):
        one = core_idempotency.request_fingerprint("POST", "/things", "", b'{"a": 1, "b": [1, 2]}')
        other = core_idempotency.request_fingerprint("POST", "/things", "", b'{"b":[1,2],"a":1}')

        assert one == other

    def test_the_order_of_query_parameters_does_not_matter(self):
        one = core_idempotency.request_fingerprint("POST", "/things", "a=1&b=2", b"")
        other = core_idempotency.request_fingerprint("POST", "/things", "b=2&a=1", b"")

        assert one == other

    @pytest.mark.parametrize(
        "other",
        [
            ("PUT", "/things", "", b'{"a":1}'),
            ("POST", "/other", "", b'{"a":1}'),
            ("POST", "/things", "a=1", b'{"a":1}'),
            ("POST", "/things", "", b'{"a":2}'),
            ("POST", "/things", "", b""),
        ],
    )
    def test_a_different_method_path_query_or_body_changes_it(self, other):
        base = core_idempotency.request_fingerprint("POST", "/things", "", b'{"a":1}')

        assert core_idempotency.request_fingerprint(*other) != base

    def test_a_body_that_is_not_json_is_hashed_as_it_is(self):
        one = core_idempotency.request_fingerprint("POST", "/things", "", b"not json")
        other = core_idempotency.request_fingerprint("POST", "/things", "", b"not json!")

        assert one != other


# ---------------------------------------------------------------------------------------------------------------------
# The claim and result records
# ---------------------------------------------------------------------------------------------------------------------


class TestBegin:
    def test_the_first_request_wins_the_claim_and_a_later_one_is_in_flight(self):
        state = _state()
        fingerprint = _fingerprint()

        claim = core_idempotency.begin(state, _USER, _RAW_KEY, fingerprint)

        assert isinstance(claim, core_idempotency.Claim)
        with pytest.raises(core_exceptions.IdempotencyInFlightError) as error:
            core_idempotency.begin(state, _USER, _RAW_KEY, fingerprint)
        assert error.value.headers is not None
        assert error.value.headers["Retry-After"] == str(core_idempotency.IN_FLIGHT_RETRY_AFTER_SECONDS)

    def test_a_request_with_other_content_is_refused_while_the_first_is_in_flight(self):
        state = _state()
        core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())

        with pytest.raises(core_exceptions.IdempotencyKeyReusedError):
            core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint({"name": "Other"}))

    def test_only_one_of_many_concurrent_requests_wins(self):
        state = _state()
        fingerprint = _fingerprint()
        barrier = threading.Barrier(8)
        outcomes: list[object] = []

        def attempt() -> None:
            barrier.wait()
            try:
                outcomes.append(core_idempotency.begin(state, _USER, _RAW_KEY, fingerprint))
            except core_exceptions.IdempotencyInFlightError as error:
                outcomes.append(error)

        threads = [threading.Thread(target=attempt) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sum(isinstance(outcome, core_idempotency.Claim) for outcome in outcomes) == 1
        assert sum(isinstance(outcome, core_exceptions.IdempotencyInFlightError) for outcome in outcomes) == 7

    def test_an_expired_claim_lets_the_key_be_claimed_again(self, monkeypatch):
        monkeypatch.setattr(core_idempotency, "CLAIM_TTL_SECONDS", 1)
        state = _state()
        core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())

        time.sleep(1.2)

        assert isinstance(core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint()), core_idempotency.Claim)

    def test_a_claim_is_released_only_by_its_holder(self):
        state = _state()
        claim = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())

        core_idempotency.release(state, dataclasses.replace(claim, value=b"another|holder"))
        with pytest.raises(core_exceptions.IdempotencyInFlightError):
            core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())

        core_idempotency.release(state, claim)
        assert isinstance(core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint()), core_idempotency.Claim)

    def test_another_user_with_the_same_key_is_independent(self):
        state = _state()

        first = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())
        second = core_idempotency.begin(state, _OTHER_USER, _RAW_KEY, _fingerprint())

        assert isinstance(first, core_idempotency.Claim)
        assert isinstance(second, core_idempotency.Claim)

    def test_neither_a_key_nor_a_value_of_the_state_holds_the_raw_key(self):
        state = _state()
        claim = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())
        core_idempotency.complete(state, claim, 201, [("content-type", "application/json")], b"{}")

        keys = list(state.iter_keys("endurain:idempotency:"))

        assert len(keys) == 1
        for key in keys:
            assert _RAW_KEY not in key
            assert _RAW_KEY.encode() not in (state.get(key) or b"")
        assert keys[0].startswith(f"endurain:idempotency:result:{_USER}:")

    def test_a_stored_result_is_replayed_for_the_same_request_and_refused_for_another(self):
        state = _state()
        claim = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())
        core_idempotency.complete(
            state,
            claim,
            201,
            [("content-type", "application/json"), ("location", "/things/1"), ("x-secret", "no")],
            b'{"id":1}',
        )

        replay = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())

        assert isinstance(replay, core_idempotency.StoredResult)
        assert replay.status_code == 201
        assert replay.body == b'{"id":1}'
        assert dict(replay.headers) == {"content-type": "application/json", "location": "/things/1"}
        with pytest.raises(core_exceptions.IdempotencyKeyReusedError):
            core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint({"name": "Other"}))

    def test_the_first_completion_wins_and_the_claim_is_released(self):
        state = _state()
        claim = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())
        core_idempotency.complete(state, claim, 201, [], b"first")
        core_idempotency.complete(state, claim, 201, [], b"second")

        replay = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())

        assert isinstance(replay, core_idempotency.StoredResult)
        assert replay.body == b"first"
        assert state.get(claim.claim_key) is None

    def test_a_result_is_kept_for_a_day_and_a_claim_for_two_minutes(self):
        assert core_idempotency.RESULT_TTL_SECONDS == 24 * 3600
        assert core_idempotency.CLAIM_TTL_SECONDS == 120
        assert core_idempotency.MAX_STORED_BODY == 256 * 1024
        state = MagicMock(wraps=_state())

        claim = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())
        core_idempotency.complete(state, claim, 201, [], b"{}")

        ttls = {call.args[0].split(":")[2]: call.args[2] for call in state.set_if_absent.call_args_list}
        assert ttls == {"claim": 120, "result": 24 * 3600}

    def test_a_claim_that_expires_between_the_two_reads_is_looked_up_once_more(self):
        state = MagicMock()
        state.get.return_value = None
        state.set_if_absent.side_effect = [False, True]

        claim = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())

        assert isinstance(claim, core_idempotency.Claim)


# ---------------------------------------------------------------------------------------------------------------------
# The dependency and the middleware, through HTTP
# ---------------------------------------------------------------------------------------------------------------------


class _Probe:
    """What the test routes did, so a test can tell a replayed request from an executed one."""

    def __init__(self) -> None:
        self.calls = 0
        self.fail_first = False


def _build_app(probe: _Probe) -> FastAPI:
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    def sign_in(request: Request, x_test_user: str = Header(default=str(_USER))) -> None:
        request.state.principal = SimpleNamespace(user_id=uuid.UUID(x_test_user))

    @app.post("/things", status_code=201, dependencies=[Depends(sign_in), core_idempotency.Idempotent])
    def create_thing(thing: _Thing, response: Response) -> dict:
        probe.calls += 1
        if probe.fail_first and probe.calls == 1:
            raise core_exceptions.ConflictError("not this time")
        response.headers["Location"] = f"/things/{probe.calls}"
        response.headers["ETag"] = '"1"'
        response.headers["X-Secret"] = "not stored"
        return {"id": probe.calls, "name": thing.name}

    @app.post("/big", status_code=201, dependencies=[Depends(sign_in), core_idempotency.Idempotent])
    def create_big(thing: _Thing) -> dict:
        probe.calls += 1
        return {"id": probe.calls, "padding": "x" * 2000}

    @app.post("/stream", dependencies=[Depends(sign_in)])
    def stream() -> StreamingResponse:
        probe.calls += 1
        return StreamingResponse(iter([b"one", b"two"]), media_type="text/plain")

    app.add_middleware(core_idempotency.IdempotencyMiddleware)
    return app


@pytest.fixture
def probe() -> _Probe:
    return _Probe()


@pytest.fixture
def client(probe) -> TestClient:
    return TestClient(_build_app(probe))


class TestReplay:
    def test_a_retry_with_the_same_key_replays_the_first_response_without_running_the_route(self, client, probe):
        first = client.post("/things", json=_BODY, headers=_HEADERS)
        second = client.post("/things", json=_BODY, headers=_HEADERS)

        assert probe.calls == 1
        assert first.status_code == second.status_code == 201
        assert second.content == first.content
        assert second.headers["Location"] == first.headers["Location"] == "/things/1"
        assert second.headers["ETag"] == first.headers["ETag"]
        assert second.headers["Content-Type"] == first.headers["Content-Type"]

    def test_a_replay_carries_only_the_stored_headers_and_no_marker_of_its_own(self, client):
        first = client.post("/things", json=_BODY, headers=_HEADERS)
        second = client.post("/things", json=_BODY, headers=_HEADERS)

        assert first.headers["X-Secret"] == "not stored"
        assert "X-Secret" not in second.headers
        assert not [name for name in second.headers if "idempoten" in name.lower() or "replay" in name.lower()]

    def test_the_body_is_replayed_byte_for_byte(self, client):
        first = client.post(
            "/things", content=b'{ "name" :"Road bike" }', headers={**_HEADERS, "content-type": "application/json"}
        )
        second = client.post("/things", json=_BODY, headers=_HEADERS)

        assert second.content == first.content

    def test_a_replay_is_logged_without_the_key(self, client, caplog):
        client.post("/things", json=_BODY, headers=_HEADERS)

        with caplog.at_level("INFO"):
            client.post("/things", json=_BODY, headers=_HEADERS)

        replays = [record for record in caplog.records if "replay" in record.getMessage().lower()]
        assert replays
        assert all(_RAW_KEY not in record.getMessage() for record in caplog.records)

    def test_a_request_with_no_key_always_runs(self, client, probe):
        client.post("/things", json=_BODY)
        client.post("/things", json=_BODY)

        assert probe.calls == 2

    def test_another_user_with_the_same_key_runs_the_route(self, client, probe):
        client.post("/things", json=_BODY, headers=_HEADERS)
        client.post("/things", json=_BODY, headers={**_HEADERS, "X-Test-User": str(_OTHER_USER)})

        assert probe.calls == 2

    @pytest.mark.parametrize("header", ["abc", '""', "", '"' + "x" * 256 + '"'])
    def test_a_malformed_key_is_a_400_problem_before_the_route_runs(self, client, probe, header):
        response = client.post("/things", json=_BODY, headers={"Idempotency-Key": header})

        assert response.status_code == 400
        assert response.json()["type"] == "urn:endurain:error:idempotency-key-invalid"
        assert response.headers["Link"].endswith('; rel="describedby"')
        assert probe.calls == 0


class TestConflicts:
    def test_the_same_key_with_another_body_is_422(self, client, probe):
        client.post("/things", json=_BODY, headers=_HEADERS)

        response = client.post("/things", json={"name": "Other"}, headers=_HEADERS)

        assert response.status_code == 422
        assert response.json()["type"] == "urn:endurain:error:idempotency-key-reused"
        assert response.headers["Link"].endswith('; rel="describedby"')
        assert probe.calls == 1

    def test_the_same_key_on_another_path_is_422(self, client):
        client.post("/things", json=_BODY, headers=_HEADERS)

        response = client.post("/big", json=_BODY, headers=_HEADERS)

        assert response.status_code == 422

    def test_a_request_that_repeats_one_still_running_is_409_with_retry_after(self, client, probe):
        core_idempotency.begin(_state(), _USER, _RAW_KEY, _fingerprint())

        response = client.post("/things", json=_BODY, headers=_HEADERS)

        assert response.status_code == 409
        assert response.json()["type"] == "urn:endurain:error:idempotency-key-in-flight"
        assert int(response.headers["Retry-After"]) >= 1
        assert response.headers["Link"].endswith('; rel="describedby"')
        assert probe.calls == 0

    def test_a_request_with_other_content_while_one_is_running_is_422(self, client, probe):
        core_idempotency.begin(_state(), _USER, _RAW_KEY, _fingerprint({"name": "Other"}))

        response = client.post("/things", json=_BODY, headers=_HEADERS)

        assert response.status_code == 422
        assert probe.calls == 0


class TestWhatIsStored:
    def test_a_refusal_releases_the_claim_so_the_retry_runs(self, client, probe):
        probe.fail_first = True

        first = client.post("/things", json=_BODY, headers=_HEADERS)
        second = client.post("/things", json=_BODY, headers=_HEADERS)

        assert first.status_code == 409
        assert second.status_code == 201
        assert probe.calls == 2
        assert list(_state().iter_keys("endurain:idempotency:claim:")) == []

    def test_a_response_over_the_cap_is_sent_unstored_and_the_claim_released(self, client, probe, monkeypatch):
        monkeypatch.setattr(core_idempotency, "MAX_STORED_BODY", 1000)

        first = client.post("/big", json=_BODY, headers=_HEADERS)
        second = client.post("/big", json=_BODY, headers=_HEADERS)

        assert first.status_code == second.status_code == 201
        assert len(first.content) > 1000
        assert probe.calls == 2
        assert list(_state().iter_keys("endurain:idempotency:")) == []

    def test_a_stored_body_is_base64_of_the_bytes_sent(self, client):
        first = client.post("/things", json=_BODY, headers=_HEADERS)

        (result_key,) = _state().iter_keys("endurain:idempotency:result:")
        record = json.loads(_state().get(result_key) or b"")

        assert base64.b64decode(record["body"]) == first.content
        assert record["status"] == 201
        assert set(record) == {"fingerprint", "status", "headers", "body"}


class TestStateOutage:
    @staticmethod
    def _down():
        state = MagicMock()
        for name in ("get", "set", "set_if_absent", "delete_if_equals"):
            getattr(state, name).side_effect = StateBackendUnavailableError("down")
        return state

    def test_a_request_with_a_key_fails_closed_with_503_and_retry_after(self, probe):
        app = _build_app(probe)
        app.dependency_overrides[core_dependencies.get_platform_state] = self._down

        response = TestClient(app).post("/things", json=_BODY, headers=_HEADERS)

        assert response.status_code == 503
        assert "Retry-After" in response.headers
        assert probe.calls == 0

    def test_a_request_without_a_key_never_touches_the_state(self, probe):
        state = self._down()
        app = _build_app(probe)
        app.dependency_overrides[core_dependencies.get_platform_state] = lambda: state

        response = TestClient(app).post("/things", json=_BODY)

        assert response.status_code == 201
        assert state.mock_calls == []


class TestMiddleware:
    @staticmethod
    def _scope(claim=None) -> dict:
        state = {} if claim is None else {core_idempotency.CLAIM_STATE_KEY: claim}
        return {"type": "http", "method": "POST", "path": "/x", "headers": [], "state": state}

    @staticmethod
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    def test_a_request_without_a_claim_is_forwarded_as_it_is_produced(self):
        async def scenario() -> None:
            first_chunk_seen = asyncio.Event()

            async def app(scope, receive, send) -> None:
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"one", "more_body": True})
                # A middleware that buffered the response would never let the first chunk out.
                await asyncio.wait_for(first_chunk_seen.wait(), timeout=2)
                await send({"type": "http.response.body", "body": b"two", "more_body": False})

            async def send(message) -> None:
                if message["type"] == "http.response.body" and message["body"] == b"one":
                    first_chunk_seen.set()

            await core_idempotency.IdempotencyMiddleware(app)(self._scope(), self._receive, send)

        asyncio.run(scenario())

    def test_a_file_route_under_a_key_is_untouched_without_a_claim(self, client, probe):
        response = client.post("/stream", headers=_HEADERS)

        assert response.content == b"onetwo"
        assert list(_state().iter_keys("endurain:idempotency:")) == []

    def test_the_result_is_stored_before_the_last_chunk_is_forwarded(self):
        state = _state()
        claim = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())
        seen_at_last_chunk: list[bytes | None] = []

        async def app(scope, receive, send) -> None:
            await send({"type": "http.response.start", "status": 201, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"{", "more_body": True})
            await send({"type": "http.response.body", "body": b"}", "more_body": False})

        sent: list[dict] = []

        async def send(message) -> None:
            sent.append(message)
            if message["type"] == "http.response.body" and not message.get("more_body"):
                seen_at_last_chunk.append(state.get(claim.result_key))

        asyncio.run(core_idempotency.IdempotencyMiddleware(app)(self._scope(claim), self._receive, send))

        assert seen_at_last_chunk[0] is not None
        assert b"".join(m["body"] for m in sent if m["type"] == "http.response.body") == b"{}"
        assert sent[0]["status"] == 201
        assert state.get(claim.claim_key) is None

    def test_an_exception_releases_the_claim(self):
        state = _state()
        claim = core_idempotency.begin(state, _USER, _RAW_KEY, _fingerprint())

        async def app(scope, receive, send) -> None:
            raise RuntimeError("boom")

        async def send(message) -> None:
            return None

        with pytest.raises(RuntimeError):
            asyncio.run(core_idempotency.IdempotencyMiddleware(app)(self._scope(claim), self._receive, send))

        assert state.get(claim.claim_key) is None

    def test_a_websocket_or_lifespan_scope_passes_through(self):
        calls: list[str] = []

        async def app(scope, receive, send) -> None:
            calls.append(scope["type"])

        for scope_type in ("websocket", "lifespan"):
            asyncio.run(core_idempotency.IdempotencyMiddleware(app)({"type": scope_type}, self._receive, MagicMock()))

        assert calls == ["websocket", "lifespan"]


class TestParseOnlyKey:
    """The routes that keep their own job-row idempotency read the key through the same strict parser."""

    @staticmethod
    def _client() -> TestClient:
        app = FastAPI()
        core_exceptions.register_exception_handlers(app)

        @app.post("/echo")
        def echo(key: core_idempotency.IdempotencyKey) -> dict:
            return {"key": key}

        return TestClient(app)

    def test_a_quoted_key_is_handed_over_unquoted(self):
        assert self._client().post("/echo", headers=_HEADERS).json() == {"key": _RAW_KEY}

    def test_no_header_is_none(self):
        assert self._client().post("/echo").json() == {"key": None}

    def test_a_bare_key_is_a_400_problem(self):
        response = self._client().post("/echo", headers={"Idempotency-Key": _RAW_KEY})

        assert response.status_code == 400
        assert response.json()["type"] == "urn:endurain:error:idempotency-key-invalid"
