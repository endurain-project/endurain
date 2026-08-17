"""The logging rule from ``.github/instructions/python.instructions.md``, enforced.

A convention that only exists in prose drifts: before this, CRUD modules narrated
every successful read and write at DEBUG — duplicating what the service already
reported, at query volume — while four services logged nothing at all. These
assertions are what keep the layers saying one kind of thing each.
"""

import pathlib
import re

#: Modules the logging rule has been applied to. ``activities`` and ``followers``
#: are the template pair; every other module still predates the convention and is
#: converted alongside its own refactor. Add a package here when you convert it —
#: the list is deliberately an opt-in, so an unconverted module is visibly
#: outstanding rather than silently exempt.
_CONVERTED = (
    pathlib.Path("app/modules/activities"),
    pathlib.Path("app/modules/followers"),
)

# Layers whose logging level set is fixed by the rule.
_ALLOWED: dict[str, set[str]] = {
    # Persistence reports only what it swallows: a failure it cannot complete,
    # or an anomaly it absorbs behind a normal-looking return.
    "crud": {"warning", "error"},
    # Detached from any request, so a skip must say why and a failure must shout.
    "subscribers": {"debug", "error", "warning"},
    # No decisions, no failures of their own.
    "query": set(),
    "serializers": set(),
    "signing": set(),
    "models": set(),
    "schema": set(),
    "contracts": set(),
}

# Routers log nothing — with one exception: a rejected capability token on an
# unauthenticated blob route is an authentication failure with no service
# beneath it to report it.
_ROUTER_TOKEN_EXCEPTIONS = {
    "app/modules/activities/activity_thumbnail/router.py",
    "app/modules/activities/activity_media/public_router.py",
}

# Services that make no decision of their own: they declare what their child
# collection is and hand the read to ``activity/child_collection``, which logs
# the one decision there is (a refusal). A log line here would either duplicate
# that or narrate a delegation.
_DELEGATING_SERVICES = [
    "app/modules/activities/activity_laps/service.py",
    "app/modules/activities/activity_sets/service.py",
    "app/modules/activities/activity_workout_steps/service.py",
]


def _log_calls(path: pathlib.Path) -> list[str]:
    """Return the log levels used in a module."""
    return re.findall(r"logger\.(debug|info|warning|error)\(", path.read_text())


def _modules_named(stem: str) -> list[pathlib.Path]:
    """Return every converted module with the given file stem."""
    return sorted(p for root in _CONVERTED for p in root.rglob(f"{stem}.py") if "__pycache__" not in str(p))


class TestLoggingRule:
    def test_crud_never_narrates_success(self):
        """The service already said what happened; repeating it here is noise."""
        offenders = [
            f"{p}: {sorted(set(_log_calls(p)) - _ALLOWED['crud'])}"
            for p in _modules_named("crud")
            if set(_log_calls(p)) - _ALLOWED["crud"]
        ]

        assert offenders == []

    def test_routers_delegate_their_logging_too(self):
        offenders = [
            str(p)
            for stem in ("router", "public_router")
            for p in _modules_named(stem)
            if _log_calls(p) and str(p) not in _ROUTER_TOKEN_EXCEPTIONS
        ]

        assert offenders == []

    def test_the_router_exceptions_only_log_rejected_tokens(self):
        """The carve-out is for auth failures, not general router logging."""
        for path in sorted(_ROUTER_TOKEN_EXCEPTIONS):
            p = pathlib.Path(path)
            if not p.exists():  # the route was removed; the exception is stale
                raise AssertionError(f"stale router logging exception: {path}")
            assert set(_log_calls(p)) <= {"warning"}

    def test_pure_layers_do_not_log(self):
        offenders = [
            f"{p}: {sorted(set(_log_calls(p)))}"
            for stem in ("query", "serializers", "signing", "models", "schema", "contracts")
            for p in _modules_named(stem)
            if _log_calls(p)
        ]

        assert offenders == []

    def test_every_service_reports_something(self):
        """A silent service is one whose decisions are invisible in production."""
        silent = [str(p) for p in _modules_named("service") if not _log_calls(p)]

        assert silent == _DELEGATING_SERVICES
