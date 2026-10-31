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
