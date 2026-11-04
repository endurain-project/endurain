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

#: Files that still swallow a broad exception, as ``{path relative to app/: number of swallowing handlers}``. This
#: is known debt (see ``docs/developer-guide/module-structure.md`` -> Known debt -> broad exception handling):
#: narrow a handler to the exceptions the code really raises and lower its count; a correct new boundary is added
#: here in review.
_SWALLOWING_BROAD_EXCEPTS: dict[str, int] = {
    "core/blob_sweep.py": 1,
    "core/config.py": 1,
    "core/middleware.py": 1,
    "core/router.py": 1,
    "core/scheduler.py": 2,
    "main.py": 4,
    "modules/activities/activity_ingestion/bulk_import_service.py": 4,
    "modules/activities/activity_ingestion/provider_entry_service.py": 1,
    "modules/activities/activity_ingestion/refresh_entry_service.py": 1,
    "modules/activities/activity_ingestion/service.py": 2,
    "modules/activities/activity_ingestion/upload_entry_service.py": 1,
    "modules/activities/activity_ingestion/window_service.py": 1,
    "modules/activities/activity_media/service.py": 5,
    "modules/activities/activity_thumbnail/service.py": 1,
    "modules/auth/identity_providers/callback_service.py": 3,
    "modules/auth/identity_providers/icon_service.py": 1,
    "modules/auth/identity_providers/oidc_client_service.py": 3,
    "modules/auth/identity_providers/token_service.py": 2,
    "modules/garmin/activity_service.py": 2,
    "modules/garmin/link_service.py": 1,
    "modules/garmin/service.py": 1,
    "modules/garmin/sync_service.py": 2,
    "modules/server_settings/login_photo_service.py": 1,
    "modules/strava/bulk_import_service.py": 2,
    "modules/strava/client_service.py": 1,
    "modules/strava/link_service.py": 1,
    "modules/strava/service.py": 1,
    "modules/users/users/deletion_job_service.py": 1,
    "modules/users/users/photo_service.py": 1,
    "modules/users/users_profile/export_job_service.py": 1,
    "modules/users/users_profile/export_service.py": 5,
    "modules/users/users_profile/import_job_service.py": 2,
    "modules/users/users_profile/utils.py": 2,
    "modules/websocket/manager.py": 1,
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
