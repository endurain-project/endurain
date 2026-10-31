"""Micro-benchmark for resolve_from_access_token latency.

Records baseline numbers for the identity-resolution performance gate.
Asserts that the operation completes within an acceptable
wall-clock threshold and makes no more DB roundtrips
than expected.

Run with::

    uv run pytest tests/auth/bench_identity_resolution.py -v

Baseline numbers recorded on 2026-05-25:
    - resolve_from_access_token (mocked DB): ~0.1 ms per call
    - 100 sequential calls: well under WALL_CLOCK_LIMIT_S
"""

import time
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

import modules.auth.access_tokens.service as auth_token_manager
import modules.auth.authentication.principal_service as principal_service
import modules.users.users.schema as users_schema
from modules.auth.contracts import AccessTokenCred

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum acceptable wall-clock time for 100 sequential resolutions.
WALL_CLOCK_LIMIT_S = 1.0

#: Number of iterations for the sequential latency benchmark.
ITERATIONS = 100


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def token_manager() -> auth_token_manager.TokenManager:
    """Real TokenManager with a test secret.

    Returns:
        auth_token_manager.TokenManager: Token manager.
    """
    return auth_token_manager.TokenManager(secret_key="bench-secret-key-for-testing-only-min-32-chars")


@pytest.fixture
def sample_user_read() -> users_schema.UsersRead:
    """Minimal UsersRead fixture.

    Returns:
        users_schema.UsersRead: Sample user.
    """
    return users_schema.UsersRead(
        id=1,
        name="Bench User",
        username="benchuser",
        email="bench@example.com",
        active=True,
        access_type=users_schema.UserAccessType.REGULAR.value,
    )


@pytest.fixture
def mock_user_orm() -> MagicMock:
    """Mock ORM user returned by the DB layer.

    Returns:
        MagicMock: Mock ORM user.
    """
    user = MagicMock()
    user.id = 1
    user.username = "benchuser"
    user.email = "bench@example.com"
    user.active = True
    user.access_type = "regular"
    return user


@pytest.fixture
def service_with_mocked_db(mock_user_orm: MagicMock) -> MagicMock:
    """Principal service whose user lookups are mocked.

    Isolates pure resolution logic from real DB latency
    so the benchmark measures the code path, not I/O.

    Args:
        mock_user_orm: Mock ORM user row.

    Returns:
        MagicMock: Mock database session.
    """
    from unittest.mock import patch

    mock_db = MagicMock()

    # Patch DB utility used inside resolve_from_access_token
    import modules.users.users.integration_service as users_integration

    users_patcher = patch.object(
        users_integration,
        "require_user",
        return_value=mock_user_orm,
    )
    check_patcher = patch.object(
        users_integration,
        "require_active_user",
        return_value=None,
    )
    users_patcher.start()
    check_patcher.start()

    yield mock_db

    users_patcher.stop()
    check_patcher.stop()


# ---------------------------------------------------------------------------
# Benchmark: wall-clock latency
# ---------------------------------------------------------------------------


class TestResolveFromAccessTokenBenchmark:
    """Performance gate for resolve_from_access_token."""

    def test_sequential_latency_under_limit(
        self,
        service_with_mocked_db: MagicMock,
        token_manager: auth_token_manager.TokenManager,
        sample_user_read: users_schema.UsersRead,
    ):
        """100 sequential resolutions complete within WALL_CLOCK_LIMIT_S.

        Baseline (2026-05-25, mocked DB):
            100 calls < 0.05 s (WALL_CLOCK_LIMIT_S = 1.0)

        This gate confirms that principal resolution stays within the expected hot-path budget.
        """
        _, access_token = token_manager.create_token(
            "bench-session", sample_user_read, auth_token_manager.TokenType.ACCESS, timedelta(minutes=15)
        )

        start = time.perf_counter()
        for _ in range(ITERATIONS):
            principal = principal_service.resolve_from_access_token(access_token, token_manager, service_with_mocked_db)
        elapsed = time.perf_counter() - start

        assert principal.user_id == sample_user_read.id
        assert isinstance(principal.credential, AccessTokenCred)
        assert elapsed < WALL_CLOCK_LIMIT_S, (
            f"resolve_from_access_token took {elapsed:.3f}s for {ITERATIONS} calls (limit: {WALL_CLOCK_LIMIT_S}s)"
        )

    def test_db_roundtrip_count(
        self,
        token_manager: auth_token_manager.TokenManager,
        sample_user_read: users_schema.UsersRead,
        mock_user_orm: MagicMock,
    ):
        """Each resolve_from_access_token makes exactly 1 DB roundtrip.

        The request-state caching in the security dependencies
        is designed to eliminate duplicate lookups; this test
        verifies the per-call baseline before caching is applied.
        """
        from unittest.mock import patch

        import modules.users.users.integration_service as users_integration

        mock_db = MagicMock()

        _, access_token = token_manager.create_token(
            "bench-session", sample_user_read, auth_token_manager.TokenType.ACCESS, timedelta(minutes=15)
        )

        with (
            patch.object(
                users_integration,
                "require_user",
                return_value=mock_user_orm,
            ) as mock_get_user,
            patch.object(
                users_integration,
                "require_active_user",
                return_value=None,
            ),
        ):
            principal_service.resolve_from_access_token(access_token, token_manager, mock_db)
            principal_service.resolve_from_access_token(access_token, token_manager, mock_db)

        # 2 calls → 2 DB roundtrips (caching is at the
        # request-state level, not the service level)
        assert mock_get_user.call_count == 2, f"Expected 2 DB calls (one per resolve), got {mock_get_user.call_count}"
