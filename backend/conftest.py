"""Root test bootstrap.

Pytest imports this before test modules and ``tests/conftest.py``.
It loads ``.env.test`` before app imports that read settings at import
time. ``pythonpath = ["app"]`` in ``pyproject.toml`` exposes the app
packages without per-file ``sys.path`` mutation.
"""

from pathlib import Path

from dotenv import load_dotenv

# Load test environment variables before any app module is imported.
load_dotenv(dotenv_path=Path(__file__).parent / ".env.test")

# Point the application's database settings at this process's test database before ``core.database`` builds its
# engine from them. The controller starts a PostgreSQL container when ``TEST_DATABASE_URL`` is unset.
from tests._helpers import database as _test_database  # noqa: E402  (must follow the dotenv load)

_test_database.bootstrap()

# Disable HTTP rate limiting for the whole test run so rate-limited routes can be
# exercised directly and via TestClient without tripping slowapi's per-bucket
# caps. slowapi short-circuits on ``limiter.enabled``, so this turns every
# ``@limiter.limit`` decorator into a pass-through. The limiter key function and
# the 429 handler are unit-tested separately in ``tests/core/test_rate_limit.py``.
import core.rate_limit as _core_rate_limit  # noqa: E402  (import must follow the dotenv load)

_core_rate_limit.limiter.enabled = False

# Direct unit tests do not run an application entrypoint, so install the same
# deterministic contributor set the API and durable worker configure at startup.
import module_registry as _module_registry  # noqa: E402

_module_registry.configure_activity_contributors()


def pytest_unconfigure(config):
    """Drop the template and stop the container once the whole run is over (the controller, or the only process)."""
    if hasattr(config, "workerinput"):
        return
    try:
        if _test_database.is_available():
            _test_database.drop_template()
    finally:
        _test_database.stop_container()
