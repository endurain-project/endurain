"""Tests for infra.container.build_platform."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import infra.providers as platform_providers
from infra.backends.clock_system import SystemClock
from infra.backends.events_inprocess import InProcessEventBus
from infra.backends.lock_noop import NoopLock
from infra.backends.route_map_static import StaticRouteMapRenderer
from infra.backends.state_memory import MemoryState
from infra.backends.storage_local import LocalStorage
from infra.container import build_platform
from infra.profile import DeploymentProfile


def _settings(
    profile,
    data_dir="unused-data-dir",
    state_uri="memory://",
    storage_uri="local://",
    events_uri="memory://",
    lock_uri="noop://",
    event_log_enabled=False,
    reverse_geo_provider="disabled",
):
    return SimpleNamespace(
        DEPLOYMENT_PROFILE=profile,
        DATA_DIR=data_dir,
        resolved_state_uri=state_uri,
        resolved_storage_uri=storage_uri,
        resolved_events_uri=events_uri,
        resolved_lock_uri=lock_uri,
        EVENT_LOG_ENABLED=event_log_enabled,
        # Geocoding defaults to disabled here so the container tests never touch
        # DNS; the backend selection itself is covered in test_platform_geocoding.
        REVERSE_GEO_PROVIDER=reverse_geo_provider,
        REVERSE_GEO_RATE_LIMIT=1.0,
        NOMINATIM_API_HOST="nominatim.openstreetmap.org",
        NOMINATIM_API_USE_HTTPS=True,
        PHOTON_API_HOST="photon.komoot.io",
        PHOTON_API_USE_HTTPS=True,
        GEOCODES_MAPS_API="changeme",
    )


class TestBuildPlatformLocal:
    def test_wires_local_backends(self, tmp_path):
        platform = build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path)))
        assert platform.profile is DeploymentProfile.LOCAL
        assert isinstance(platform.state, MemoryState)
        assert isinstance(platform.storage, LocalStorage)
        assert isinstance(platform.events, InProcessEventBus)
        assert isinstance(platform.lock, NoopLock)
        assert isinstance(platform.clock, SystemClock)

    def test_all_providers_satisfied(self, tmp_path):
        platform = build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path)))
        assert isinstance(platform.state, platform_providers.StateProvider)
        assert isinstance(platform.storage, platform_providers.StorageProvider)
        assert isinstance(platform.events, platform_providers.EventBusProvider)
        assert isinstance(platform.lock, platform_providers.LockProvider)
        assert isinstance(platform.clock, platform_providers.ClockProvider)
        assert isinstance(platform.geocoding, platform_providers.GeocodingProvider)
        assert isinstance(platform.route_map_renderer, platform_providers.RouteMapRendererProvider)
        assert isinstance(platform.route_map_renderer, StaticRouteMapRenderer)

    def test_storage_uses_data_dir_root(self, tmp_path):
        platform = build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path)))
        platform.storage.save("activity_thumbnails", "x.webp", b"d")
        assert (tmp_path / "activity_thumbnails" / "x.webp").is_file()

    def test_platform_is_frozen(self, tmp_path):
        platform = build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path)))
        assert platform.__dataclass_params__.frozen is True


class TestBuildPlatformState:
    def test_memory_scheme_builds_memory_backend(self, tmp_path):
        platform = build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path), state_uri="memory://"))
        assert isinstance(platform.state, MemoryState)

    def test_redis_scheme_builds_redis_backend(self, tmp_path):
        from infra.backends import state_redis
        from infra.backends.state_redis import RedisState

        with patch.object(state_redis.platform_redis, "get_shared_client"):
            platform = build_platform(
                _settings(DeploymentProfile.DISTRIBUTED, str(tmp_path), state_uri="redis://localhost:6379/0")
            )
        assert isinstance(platform.state, RedisState)
        assert isinstance(platform.state, platform_providers.StateProvider)

    def test_unsupported_scheme_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported STATE_URI"):
            build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path), state_uri="kafka://broker"))


class TestBuildPlatformAllModes:
    """Every profile boots; the profile only shapes the default backends."""

    @pytest.mark.parametrize(
        "profile",
        [DeploymentProfile.LOCAL, DeploymentProfile.DISTRIBUTED, DeploymentProfile.CUSTOM],
    )
    def test_every_profile_builds_all_providers(self, profile, tmp_path):
        platform = build_platform(_settings(profile, str(tmp_path)))
        assert isinstance(platform.state, platform_providers.StateProvider)
        assert isinstance(platform.storage, platform_providers.StorageProvider)
        assert isinstance(platform.events, platform_providers.EventBusProvider)
        assert isinstance(platform.lock, platform_providers.LockProvider)
        assert isinstance(platform.clock, platform_providers.ClockProvider)

    def test_distributed_wires_distributed_backends(self, tmp_path):
        from infra.backends import events_redis, state_redis, storage_s3
        from infra.backends.events_redis import RedisStreamEventBus
        from infra.backends.lock_pg import PgAdvisoryLock
        from infra.backends.state_redis import RedisState

        settings = _settings(
            DeploymentProfile.DISTRIBUTED,
            str(tmp_path),
            state_uri="redis://r/0",
            storage_uri="s3://bucket/thumbs",
            events_uri="redis://r/0",
            lock_uri="postgres-advisory://",
        )
        with (
            patch.object(state_redis.platform_redis, "get_shared_client"),
            patch.object(events_redis.platform_redis, "get_shared_client"),
            patch.object(storage_s3.boto3, "client"),
        ):
            platform = build_platform(settings)
        assert isinstance(platform.state, RedisState)
        assert isinstance(platform.storage, storage_s3.S3Storage)
        assert isinstance(platform.events, RedisStreamEventBus)
        assert isinstance(platform.lock, PgAdvisoryLock)


class TestBuildPlatformStorage:
    def test_s3_scheme_builds_s3_backend(self, tmp_path):
        from infra.backends import storage_s3

        with patch.object(storage_s3.boto3, "client") as mock_client:
            platform = build_platform(
                _settings(DeploymentProfile.LOCAL, str(tmp_path), storage_uri="s3://bucket/thumbs")
            )
        assert isinstance(platform.storage, storage_s3.S3Storage)
        assert isinstance(platform.storage, platform_providers.StorageProvider)
        mock_client.assert_called_once()

    def test_unsupported_scheme_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported STORAGE_URI"):
            build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path), storage_uri="memory://"))


class TestBuildPlatformEvents:
    def test_memory_scheme_builds_in_process_bus(self, tmp_path):
        platform = build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path), events_uri="memory://"))
        assert isinstance(platform.events, InProcessEventBus)

    def test_redis_scheme_builds_redis_event_bus(self, tmp_path):
        from infra.backends import events_redis
        from infra.backends.events_redis import RedisStreamEventBus

        with patch.object(events_redis.platform_redis, "get_shared_client"):
            platform = build_platform(
                _settings(DeploymentProfile.LOCAL, str(tmp_path), events_uri="redis://localhost:6379/0")
            )
        assert isinstance(platform.events, RedisStreamEventBus)
        assert isinstance(platform.events, platform_providers.EventBusProvider)

    def test_unsupported_scheme_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported EVENTS_URI"):
            build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path), events_uri="kafka://broker"))

    def test_event_log_enabled_attaches_recorder(self, tmp_path):
        from infra.event_log.recorder import EventLogRecorder

        platform = build_platform(
            _settings(DeploymentProfile.LOCAL, str(tmp_path), events_uri="memory://", event_log_enabled=True)
        )
        assert isinstance(platform.events, InProcessEventBus)
        assert isinstance(platform.events._recorder, EventLogRecorder)
        # The same recorder is shared onto the platform for the durable path.
        assert isinstance(platform.recorder, EventLogRecorder)

    def test_event_log_disabled_leaves_no_recorder(self, tmp_path):
        platform = build_platform(
            _settings(DeploymentProfile.LOCAL, str(tmp_path), events_uri="memory://", event_log_enabled=False)
        )
        assert platform.events._recorder is None
        assert platform.recorder is None


class TestBuildPlatformLock:
    def test_noop_scheme_builds_noop_lock(self, tmp_path):
        platform = build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path), lock_uri="noop://"))
        assert isinstance(platform.lock, NoopLock)

    def test_postgres_advisory_scheme_builds_pg_lock(self, tmp_path):
        from infra.backends.lock_pg import PgAdvisoryLock

        platform = build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path), lock_uri="postgres-advisory://"))
        assert isinstance(platform.lock, PgAdvisoryLock)
        assert isinstance(platform.lock, platform_providers.LockProvider)

    def test_unsupported_scheme_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported LOCK_URI"):
            build_platform(_settings(DeploymentProfile.LOCAL, str(tmp_path), lock_uri="etcd://cluster"))
