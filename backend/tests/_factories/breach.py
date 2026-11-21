"""The Have I Been Pwned range API, faked at the HTTP boundary, for tests of the breached-password check."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx2
import pytest

import modules.auth.credentials.password_policy as credentials_password_policy


@dataclass
class RangeApi:
    """The faked range API and the requests it received.

    Attributes:
        requests: Every request sent to the API, oldest first.
        options: The transport options (``timeout``, ``follow_redirects``) of each request.
    """

    requests: list[httpx2.Request] = field(default_factory=list)
    options: list[dict[str, object]] = field(default_factory=list)
    _breached: set[str] = field(default_factory=set)
    _failure: Callable[[httpx2.Request], httpx2.Response] | None = None
    _on_request: Callable[[], None] | None = None

    def breach(self, *passwords: str) -> None:
        """List the passwords in the breach corpus, with padding entries around them."""
        self._breached.update(passwords)

    def fail_with(self, failure: Callable[[httpx2.Request], httpx2.Response]) -> None:
        """Make every request fail: ``failure`` returns the response or raises the transport error."""
        self._failure = failure

    def on_request(self, hook: Callable[[], None]) -> None:
        """Run ``hook`` when a request arrives, before the API answers."""
        self._on_request = hook

    def _respond(self, request: httpx2.Request) -> httpx2.Response:
        if self._on_request is not None:
            self._on_request()
        if self._failure is not None:
            return self._failure(request)
        prefix = request.url.path.rsplit("/", 1)[-1]
        lines = ["0018A45C4D1DEF81644B54AB7F969B88D65:3", "00D4F6E8FA6EECAD2A3AA415EEC418D38EC:0"]
        for password in self._breached:
            digest = _sha1(password)
            if digest.startswith(prefix):
                lines.append(f"{digest[5:]}:42")
        return httpx2.Response(200, text="\r\n".join(lines), request=request)


def _sha1(password: str) -> str:
    form = credentials_password_policy.hash_form(password).encode("utf-8")
    return hashlib.sha1(form, usedforsecurity=False).hexdigest().upper()


def fake_range_api(monkeypatch: pytest.MonkeyPatch) -> RangeApi:
    """Replace ``httpx2.get`` with a range API that lists no password as breached until told to.

    Args:
        monkeypatch: The test's monkeypatch, which undoes the replacement.

    Returns:
        The fake, to list breached passwords on and to read the requests from.
    """
    api = RangeApi()

    def get(url: str, *_args: object, headers: dict[str, str] | None = None, **options: object) -> httpx2.Response:
        request = httpx2.Request("GET", url, headers=headers)
        api.requests.append(request)
        api.options.append(options)
        return api._respond(request)

    monkeypatch.setattr(httpx2, "get", get)
    return api
