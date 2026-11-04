"""A broad ``except`` that swallows the error is a bug waiting to be hidden, and this test keeps new ones out.

``except Exception`` (or ``BaseException``, or a bare ``except:``) that never raises turns any fault inside the
``try`` into a quiet fallback. Two recent ones hid an identity-provider refresh token that was never stored and a
broken database session. A broad handler is fine when it re-raises, raises a converted domain error or cleans up and
re-raises; one that does none of these *swallows*. Ruff ``BLE001`` cannot enforce this, because it accepts a
handler that logs with ``exc_info=err``, which is the project's standard way to log a failure.

Existing swallowing handlers are counted per file in ``_SWALLOWING_BROAD_EXCEPTS``. The counts must match exactly,
so the register shrinks as handlers are narrowed.
"""

import ast
import pathlib

from tests._helpers.handlers import own_nodes

_APP = pathlib.Path("app")

#: Directories out of scope: the data migrations log a record they cannot convert, mark the run incomplete and
#: carry on, and ``alembic`` holds the schema revisions.
_EXEMPT_DIRS = frozenset({"migrations", "alembic"})

#: Files that swallow a broad exception, as ``{path relative to app/: number of swallowing handlers}``. Each is
#: either a boundary that must outlive any failure (the comment says why) or known debt (see
#: ``docs/developer-guide/module-structure.md`` -> Known debt -> broad exception handling). Narrow a handler to the
#: exceptions the code really raises and lower its count; a correct new boundary is added here in review.
_SWALLOWING_BROAD_EXCEPTS: dict[str, int] = {
    "core/middleware.py": 1,  # detached tile-domain refresh task nothing awaits
    "main.py": 3,  # best-effort startup tasks (_safe_run, _safe_run_async) and engine dispose at shutdown
    "modules/activities/activity_ingestion/bulk_import_service.py": 2,  # folder-feed job records any failure; per-file
    "modules/activities/activity_ingestion/refresh_entry_service.py": 1,  # per provider; re-raises the first failure
    "modules/activities/activity_ingestion/window_service.py": 1,  # per activity; re-raises the first failure
    "modules/auth/identity_providers/callback_service.py": 2,  # browser callbacks always redirect to the failure page
    "modules/garmin/link_service.py": 1,  # link thread must always record a terminal state
    "modules/garmin/sync_service.py": 1,  # one user's health pull must not stop the rest
    "modules/strava/link_service.py": 1,  # link thread must always record a terminal state
    "modules/users/users/deletion_job_service.py": 1,  # one stalled deletion must not stop the sweep
    "modules/users/users_profile/export_media_service.py": 5,  # known debt: name the storage errors each writer expects
    "modules/users/users_profile/utils.py": 2,  # known debt: name the psutil errors memory detection expects
}


def _is_broad(handler: ast.ExceptHandler) -> bool:
    """Return whether a handler is a bare ``except:`` or catches ``Exception`` or ``BaseException``."""
    caught = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(t is None or (isinstance(t, ast.Name) and t.id in {"Exception", "BaseException"}) for t in caught)


def _swallowing_counts() -> dict[str, int]:
    """Return the number of swallowing broad handlers per file, as a path relative to ``app/``."""
    counts: dict[str, int] = {}
    for path in sorted(_APP.rglob("*.py")):
        if "__pycache__" in path.parts or set(path.parts) & _EXEMPT_DIRS:
            continue
        swallowing = sum(
            1
            for handler in ast.walk(ast.parse(path.read_text()))
            if isinstance(handler, ast.ExceptHandler)
            and _is_broad(handler)
            and not any(isinstance(node, ast.Raise) for node in own_nodes(handler))
        )
        if swallowing:
            counts[path.relative_to(_APP).as_posix()] = swallowing
    return counts


class TestBroadExcept:
    def test_a_broad_except_re_raises_unless_registered(self):
        """A broad handler without a ``raise`` is allowed only where ``_SWALLOWING_BROAD_EXCEPTS`` counts it."""
        actual = _swallowing_counts()
        mismatches = [
            f"{name}: {actual.get(name, 0)} swallowing handler(s), registered {_SWALLOWING_BROAD_EXCEPTS.get(name, 0)}"
            for name in sorted(actual.keys() | _SWALLOWING_BROAD_EXCEPTS.keys())
            if actual.get(name, 0) != _SWALLOWING_BROAD_EXCEPTS.get(name, 0)
        ]

        assert not mismatches, (
            "A broad `except` (bare, Exception or BaseException) must re-raise. Narrow it to the exceptions the "
            "code really raises, or re-raise; when a baselined handler is narrowed, lower its count in "
            "_SWALLOWING_BROAD_EXCEPTS:\n  " + "\n  ".join(mismatches)
        )
