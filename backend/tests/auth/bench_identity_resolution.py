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
from unittest.mock import MagicMock

import pytest

import auth._internal.password_hasher as auth_password_hasher
import auth._internal.token_manager as auth_token_manager
import users.users.schema as users_schema
from auth.identity_service import DefaultIdentityService
from auth.principal import AccessTokenCred

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
def service_with_mocked_db(
    token_manager: auth_token_manager.TokenManager,
    mock_user_orm: MagicMock,
) -> DefaultIdentityService:
    """DefaultIdentityService whose DB lookups are mocked.

    Isolates pure resolution logic from real DB latency
    so the benchmark measures the code path, not I/O.

    Args:
        token_manager: Real JWT token manager.
        mock_user_orm: Mock ORM user row.

    Returns:
        DefaultIdentityService: Service under test.
    """
    from unittest.mock import patch

    mock_db = MagicMock()
    password_hasher = auth_password_hasher.get_password_hasher()
    svc = DefaultIdentityService(
        db=mock_db,
        token_manager=token_manager,
        password_hasher=password_hasher,
    )

    # Patch DB utility used inside resolve_from_access_token
    import users.users.utils as users_utils

    users_utils_patcher = patch.object(
        users_utils,
        "get_user_by_id_or_404",
        return_value=mock_user_orm,
    )
    check_patcher = patch.object(
        users_utils,
        "check_user_is_active",
        return_value=None,
    )
    users_utils_patcher.start()
    check_patcher.start()

    yield svc

    users_utils_patcher.stop()
    check_patcher.stop()


# ---------------------------------------------------------------------------
# Benchmark: wall-clock latency
# ---------------------------------------------------------------------------


class TestResolveFromAccessTokenBenchmark:
    """Performance gate for resolve_from_access_token."""

    def test_sequential_latency_under_limit(
        self,
        service_with_mocked_db: DefaultIdentityService,
        token_manager: auth_token_manager.TokenManager,
        sample_user_read: users_schema.UsersRead,
    ):
        """100 sequential resolutions complete within WALL_CLOCK_LIMIT_S.

        Baseline (2026-05-25, mocked DB):
            100 calls < 0.05 s (WALL_CLOCK_LIMIT_S = 1.0)

        This gate confirms that routing through IdentityService
        does not introduce unexpected overhead on the hot path.
        """
        _, access_token = token_manager.create_token(
            "bench-session",
            sample_user_read,
            auth_token_manager.TokenType.ACCESS,
        )

        start = time.perf_counter()
        for _ in range(ITERATIONS):
            principal = service_with_mocked_db.resolve_from_access_token(access_token)
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

        import users.users.utils as users_utils

        mock_db = MagicMock()
        password_hasher = auth_password_hasher.get_password_hasher()
        svc = DefaultIdentityService(
            db=mock_db,
            token_manager=token_manager,
            password_hasher=password_hasher,
        )

        _, access_token = token_manager.create_token(
            "bench-session",
            sample_user_read,
            auth_token_manager.TokenType.ACCESS,
        )

        with (
            patch.object(
                users_utils,
                "get_user_by_id_or_404",
                return_value=mock_user_orm,
            ) as mock_get_user,
            patch.object(
                users_utils,
                "check_user_is_active",
                return_value=None,
            ),
        ):
            svc.resolve_from_access_token(access_token)
            svc.resolve_from_access_token(access_token)

        # 2 calls → 2 DB roundtrips (caching is at the
        # request-state level, not the service level)
        assert mock_get_user.call_count == 2, f"Expected 2 DB calls (one per resolve), got {mock_get_user.call_count}"
