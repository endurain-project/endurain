"""Tests for the Endurain settings -> JasilSettings translation."""

import jasil.profile as jasil_profile

import core.config as core_config
from core.platform_settings import build_jasil_settings


def _distributed(**overrides):
    """A minimally valid distributed configuration."""
    return core_config.Settings(
        _env_file=None,
        ENVIRONMENT="production",
        DEPLOYMENT_PROFILE="distributed",
        REDIS_URL="redis://shared:6379/0",
        STORAGE_URI="s3://bucket/thumbs",
        **overrides,
    )


class TestDeploymentShape:
    def test_local_defaults_leave_uris_unset(self):
        # Unset URIs must reach JASIL as None so its own profile defaults apply;
        # resolving them here would disable the distributed refuse-to-guess check.
        result = build_jasil_settings(core_config.Settings(_env_file=None))

        assert result.profile is jasil_profile.DeploymentProfile.LOCAL
        assert result.state_uri is None
        assert result.storage_uri is None
        assert result.events_uri is None
        assert result.lock_uri is None

    def test_profile_and_worker_count_carried_over(self):
        result = build_jasil_settings(_distributed(WEB_WORKERS=4))

        assert result.profile is jasil_profile.DeploymentProfile.DISTRIBUTED
        assert result.web_workers == 4

    def test_data_dir_carried_over(self):
        result = build_jasil_settings(core_config.Settings(_env_file=None, DATA_DIR="/srv/endurain"))

        assert result.data_dir == "/srv/endurain"

    def test_consistency_enforcement_stays_on(self):
        result = build_jasil_settings(core_config.Settings(_env_file=None))

        assert result.enforce_deployment_consistency is True


class TestCapabilityUris:
    def test_redis_url_feeds_state_and_events(self):
        result = build_jasil_settings(_distributed())

        assert result.state_uri == "redis://shared:6379/0"
        assert result.events_uri == "redis://shared:6379/0"

    def test_explicit_uris_win_over_redis_url(self):
        result = build_jasil_settings(
            _distributed(
                STATE_URI="redis://state:6379/1",
                EVENTS_URI="redis://events:6379/2",
            )
        )

        assert result.state_uri == "redis://state:6379/1"
        assert result.events_uri == "redis://events:6379/2"

    def test_storage_uri_carried_over(self):
        result = build_jasil_settings(_distributed())

        assert result.storage_uri == "s3://bucket/thumbs"


class TestLockUri:
    def test_explicit_lock_uri_wins(self):
        result = build_jasil_settings(_distributed(LOCK_URI="postgres-advisory://custom"))

        assert result.lock_uri == "postgres-advisory://custom"

    def test_distributed_defaults_to_advisory_lock(self):
        result = build_jasil_settings(_distributed())

        assert result.lock_uri == "postgres-advisory://"

    def test_multi_worker_local_defaults_to_advisory_lock(self):
        # JASIL would default the whole local profile to noop:// and then reject
        # it for a multi-worker topology; Endurain resolves it instead so a
        # multi-worker deployment needs no extra configuration.
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="production",
            WEB_WORKERS=2,
            REDIS_URL="redis://shared:6379/0",
        )

        result = build_jasil_settings(settings)

        assert result.profile is jasil_profile.DeploymentProfile.LOCAL
        assert result.lock_uri == "postgres-advisory://"

    def test_single_process_local_leaves_lock_to_jasil(self):
        result = build_jasil_settings(core_config.Settings(_env_file=None))

        assert result.lock_uri is None


class TestJobSettings:
    def test_defaults_mapped(self):
        result = build_jasil_settings(core_config.Settings(_env_file=None)).jobs

        assert result.enabled is False
        assert result.lease_seconds == 300
        assert result.batch_size == 10
        assert result.poll_interval_seconds == 2.0
        assert result.max_attempts == 5
        assert result.retention_days == 90

    def test_overrides_mapped(self):
        settings = core_config.Settings(
            _env_file=None,
            JOBS_ENABLED=True,
            JOBS_LEASE_SECONDS=120,
            JOBS_BATCH_SIZE=25,
            JOBS_MAX_ATTEMPTS=8,
            JOBS_POLL_INTERVAL_SECONDS=0.5,
            JOBS_RETENTION_DAYS=14,
        )

        result = build_jasil_settings(settings).jobs

        assert result.enabled is True
        assert result.lease_seconds == 120
        assert result.batch_size == 25
        assert result.max_attempts == 8
        assert result.poll_interval_seconds == 0.5
        assert result.retention_days == 14

    def test_backoff_bounds_narrowed_to_whole_seconds(self):
        settings = core_config.Settings(
            _env_file=None,
            JOBS_BACKOFF_BASE_SECONDS=7.9,
            JOBS_BACKOFF_MAX_SECONDS=1800.5,
        )

        result = build_jasil_settings(settings).jobs

        assert result.backoff_base_seconds == 7
        assert result.backoff_max_seconds == 1800


class TestEventLogSettings:
    def test_defaults_mapped(self):
        result = build_jasil_settings(core_config.Settings(_env_file=None)).event_log

        assert result.enabled is True
        assert result.retention_days == 90

    def test_overrides_mapped(self):
        settings = core_config.Settings(
            _env_file=None,
            EVENT_LOG_ENABLED=False,
            EVENT_LOG_RETENTION_DAYS=0,
        )

        result = build_jasil_settings(settings).event_log

        assert result.enabled is False
        assert result.retention_days == 0


class TestGeocodingSettings:
    def test_hosts_and_provider_mapped(self):
        settings = core_config.Settings(
            _env_file=None,
            REVERSE_GEO_PROVIDER="photon",
            REVERSE_GEO_RATE_LIMIT=2.5,
            NOMINATIM_API_HOST="nominatim.example.org",
            NOMINATIM_API_USE_HTTPS=False,
            PHOTON_API_HOST="photon.example.com",
            PHOTON_API_USE_HTTPS=True,
        )

        result = build_jasil_settings(settings).geocoding

        assert result.provider == "photon"
        assert result.rate_limit == 2.5
        assert result.nominatim_host == "nominatim.example.org"
        assert result.nominatim_use_https is False
        assert result.photon_host == "photon.example.com"
        assert result.photon_use_https is True

    def test_placeholder_api_key_becomes_unset(self):
        # 'changeme' is the shipped placeholder; JASIL disables the capability
        # for a falsy key, which is what the previous container did for it.
        result = build_jasil_settings(core_config.Settings(_env_file=None)).geocoding

        assert result.api_key is None

    def test_real_api_key_carried_over(self):
        settings = core_config.Settings(_env_file=None, GEOCODES_MAPS_API="a-real-key")

        result = build_jasil_settings(settings).geocoding

        assert result.api_key == "a-real-key"

    def test_user_agent_identifies_endurain(self):
        result = build_jasil_settings(core_config.Settings(_env_file=None)).geocoding

        assert result.user_agent == f"Endurain/{core_config.API_VERSION} (ReverseGeocoding)"


class TestNetworkSettings:
    def test_ssrf_allowlist_mapped_as_tuple(self):
        settings = core_config.Settings(
            _env_file=None,
            SSRF_ALLOWED_HOSTS="auth.example.com,10.1.0.0/16",
        )

        result = build_jasil_settings(settings).network

        assert result.ssrf_allowed_hosts == tuple(settings.SSRF_ALLOWED_HOSTS)

    def test_empty_allowlist_is_empty_tuple(self):
        result = build_jasil_settings(core_config.Settings(_env_file=None)).network

        assert result.ssrf_allowed_hosts == ()
