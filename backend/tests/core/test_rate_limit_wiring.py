"""End-to-end coverage for the rate-limit wiring.

``backend/conftest.py`` turns the limiter off for the whole run so rate-limited
routes can be exercised directly. That leaves one thing unproven: whether the
tiers are actually attached to the endpoints that need them. A decorator on the
wrong function, at the wrong tier, or missing entirely would pass every other
test in the suite and only be discovered in production.

So this module asserts three things:

* the *manifest* — each sensitive endpoint carries the tier it is supposed to,
  read from the limiter's own registry rather than from the source text;
* the *completeness* of that manifest — every decorated endpoint in the tree is
  listed, so the list cannot silently fall behind the code; and
* the *behaviour* — a route decorated at a tier really does answer ``429`` with
  the RFC 9457 problem document once the cap is passed, with the limiter enabled
  exactly as the application enables it.
"""

import ast
import pathlib
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from limits import parse as parse_limit
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

import core.rate_limit as core_rate_limit
import modules.activities.activity.router as activity_router
import modules.activities.activity_ingestion.router as ingestion_router
import modules.activities.activity_media.router as activity_media_router
import modules.auth.identity_providers.public_router as idp_public_router
import modules.auth.password_reset_tokens.router as password_reset_router
import modules.auth.router as auth_router
import modules.auth.sign_up_tokens.router as sign_up_tokens_router
import modules.followers.router as followers_router
import modules.users.users_profile.router as users_profile_router


def _registered_limits(func) -> list[str]:
    """Return the limit strings slowapi recorded for an endpoint.

    slowapi keys its registry by ``module.qualname``, so this reads the same
    entry the middleware consults at request time rather than re-deriving it. The
    stored form is the parsed one (``"10 per 1 minute"``), which is why the
    expected tier is parsed too rather than string-compared.

    Args:
        func: The decorated endpoint function.

    Returns:
        The configured limit strings, empty when the endpoint carries no tier.
    """
    name = f"{func.__module__}.{func.__name__}"
    return [str(limit.limit) for limit in core_rate_limit.limiter._route_limits.get(name, [])]


# Every endpoint carrying a tier, with the tier it must carry. This is not an
# opt-in list: ``test_every_decorated_endpoint_is_in_the_manifest`` walks the
# source tree and fails when a decorated route is missing from it, so a new
# sensitive endpoint cannot be added without also being asserted here.
_TIERED_ENDPOINTS = [
    pytest.param(auth_router.login_for_access_token, core_rate_limit.SENSITIVE, id="login"),
    pytest.param(auth_router.verify_mfa_and_login, core_rate_limit.SENSITIVE, id="mfa-verify"),
    pytest.param(auth_router.refresh_token, core_rate_limit.WRITE, id="token-refresh"),
    pytest.param(auth_router.logout, core_rate_limit.WRITE, id="logout"),
    pytest.param(sign_up_tokens_router.signup, core_rate_limit.SENSITIVE, id="signup"),
    pytest.param(sign_up_tokens_router.verify_email, core_rate_limit.SENSITIVE, id="verify-email"),
    pytest.param(
        password_reset_router.request_password_reset,
        core_rate_limit.SENSITIVE,
        id="password-reset-request",
    ),
    pytest.param(
        password_reset_router.confirm_password_reset,
        core_rate_limit.SENSITIVE,
        id="password-reset-confirm",
    ),
    pytest.param(idp_public_router.initiate_login, core_rate_limit.SENSITIVE, id="oidc-initiate"),
    pytest.param(idp_public_router.handle_callback, core_rate_limit.SENSITIVE, id="oidc-callback"),
    pytest.param(
        idp_public_router.exchange_tokens_for_session,
        core_rate_limit.SENSITIVE,
        id="oidc-token-exchange",
    ),
    pytest.param(
        users_profile_router.generate_link_token,
        core_rate_limit.SENSITIVE,
        id="sso-link-token",
    ),
    pytest.param(
        users_profile_router.generate_mfa_backup_codes,
        core_rate_limit.SENSITIVE,
        id="mfa-backup-codes",
    ),
    pytest.param(
        users_profile_router.delete_my_identity_provider,
        core_rate_limit.SENSITIVE,
        id="sso-unlink",
    ),
    pytest.param(
        ingestion_router.create_activity_with_uploaded_file,
        core_rate_limit.UPLOAD,
        id="activity-upload",
    ),
    pytest.param(
        ingestion_router.create_activity_with_bulk_import,
        core_rate_limit.UPLOAD,
        id="activity-bulk-import",
    ),
    pytest.param(ingestion_router.refresh_activities, core_rate_limit.PROVIDER_SYNC, id="provider-refresh"),
    pytest.param(activity_media_router.upload_media, core_rate_limit.UPLOAD, id="media-upload"),
    pytest.param(activity_media_router.delete_activity_media, core_rate_limit.WRITE, id="media-delete"),
    pytest.param(activity_router.edit_activity, core_rate_limit.WRITE, id="activity-edit"),
    pytest.param(activity_router.edit_activities, core_rate_limit.WRITE, id="activity-bulk-edit"),
    pytest.param(activity_router.delete_activity, core_rate_limit.WRITE, id="activity-delete"),
    pytest.param(followers_router.follow_user, core_rate_limit.WRITE, id="follow-user"),
    pytest.param(followers_router.accept_follow_request, core_rate_limit.WRITE, id="accept-follow-request"),
    pytest.param(followers_router.reject_follow_request, core_rate_limit.WRITE, id="reject-follow-request"),
    pytest.param(followers_router.delete_follow_relationship, core_rate_limit.WRITE, id="unfollow"),
]


@pytest.mark.parametrize(("endpoint", "expected_tier"), _TIERED_ENDPOINTS)
def test_the_endpoint_carries_its_tier(endpoint, expected_tier):
    """A missing or mistyped decorator is invisible to every other test."""
    assert str(parse_limit(expected_tier)) in _registered_limits(endpoint)


_APP_ROOT = pathlib.Path("app")


def _decorated_endpoints() -> set[str]:
    """Return every endpoint decorated with a rate-limit tier, from the source.

    Read off the AST rather than the limiter registry: the registry only holds
    what the current test session happened to import, so a decorated route in an
    unimported module would look like it does not exist. The filesystem cannot
    be under-imported.

    Returns:
        Dotted ``module.function`` names, keyed the way slowapi keys its registry.
    """
    found: set[str] = set()
    for path in sorted(_APP_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = ".".join(path.relative_to(_APP_ROOT).with_suffix("").parts)
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and ast.unparse(decorator.func).endswith("limiter.limit"):
                    found.add(f"{module}.{node.name}")
    return found


def test_every_decorated_endpoint_is_in_the_manifest():
    """The manifest cannot fall behind the code.

    A hand-maintained list of sensitive routes is only as good as the last person
    who remembered to append to it, and this one had already drifted: ``signup``,
    ``verify_email`` and the MFA backup-code route were all rate-limited in the
    application and absent here, so deleting their decorators would have broken
    no test. Deriving the expected set from the source makes the omission the
    failure instead of the silence.
    """
    listed = {f"{param.values[0].__module__}.{param.values[0].__name__}" for param in _TIERED_ENDPOINTS}

    assert _decorated_endpoints() - listed == set(), (
        "Rate-limited endpoint(s) missing from _TIERED_ENDPOINTS. Add each one "
        "with the tier it must carry, so removing its decorator fails a test."
    )


@pytest.fixture
def enabled_limiter() -> Iterator[None]:
    """Re-enable the limiter (and clear its buckets) for one test."""
    core_rate_limit.limiter.enabled = True
    core_rate_limit.limiter.reset()
    try:
        yield
    finally:
        core_rate_limit.limiter.reset()
        core_rate_limit.limiter.enabled = False


def _app_with(tier: str, probe_name: str) -> FastAPI:
    """Build a one-route app wired exactly as ``main.create_app`` wires the limiter.

    Args:
        tier: The tier constant to decorate the probe route with.
        probe_name: A name unique to this app. slowapi keys its registry by
            ``module.funcname``, so two probes sharing a name would stack their
            limits and the tightest one would silently win.

    Returns:
        The configured app.
    """
    app = FastAPI()
    app.state.limiter = core_rate_limit.limiter
    app.add_exception_handler(
        RateLimitExceeded,
        core_rate_limit.rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )
    app.add_middleware(SlowAPIMiddleware)

    def probe(request: Request) -> dict[str, bool]:
        return {"ok": True}

    probe.__name__ = probe_name
    app.post("/probe")(core_rate_limit.limiter.limit(tier)(probe))
    return app


def _burst(client: TestClient, token: str, count: int) -> list[int]:
    return [client.post("/probe", headers={"Authorization": f"Bearer {token}"}).status_code for _ in range(count)]


@pytest.mark.parametrize(
    ("tier", "cap"),
    [
        (core_rate_limit.SENSITIVE, 10),
        (core_rate_limit.UPLOAD, 20),
        (core_rate_limit.PROVIDER_SYNC, 6),
    ],
    ids=["sensitive", "upload", "provider-sync"],
)
def test_a_tier_actually_refuses_past_its_cap(enabled_limiter, tier, cap):
    """Proves the tier constants bound real traffic, not just that they parse."""
    client = TestClient(_app_with(tier, f"probe_cap_{cap}"))

    statuses = _burst(client, f"token-cap-{cap}", cap + 1)

    assert statuses[:cap] == [200] * cap
    assert statuses[cap] == 429


def test_the_refusal_is_a_problem_document_with_retry_after(enabled_limiter):
    """Clients back off on ``Retry-After``; a bare 429 body would not tell them how long."""
    client = TestClient(_app_with(core_rate_limit.PROVIDER_SYNC, "probe_problem_doc"))

    statuses = _burst(client, "token-problem-doc", 7)
    assert statuses[-1] == 429

    refused = client.post("/probe", headers={"Authorization": "Bearer token-problem-doc"})
    assert refused.status_code == 429
    assert refused.headers["content-type"].startswith("application/problem+json")
    assert refused.json()["title"] == "Too Many Requests"
    assert "Retry-After" in refused.headers


def test_buckets_are_per_caller_not_global(enabled_limiter):
    """One user exhausting a tier must not lock everyone else out."""
    client = TestClient(_app_with(core_rate_limit.PROVIDER_SYNC, "probe_per_caller"))

    assert _burst(client, "noisy-caller", 7)[-1] == 429
    assert _burst(client, "quiet-caller", 1) == [200]
