"""Tests for application configuration validation."""

from unittest.mock import patch

import jasil.profile as platform_profile
import pytest
from pydantic import ValidationError

import core.config as core_config


class TestDeploymentProfileEnforcement:
    """DEPLOYMENT_PROFILE / WEB_WORKERS parsing, resolved_state_uri, and shared-state fail-fast."""

    def test_defaults_to_local_single_worker(self):
        settings = core_config.Settings(_env_file=None)
        assert settings.DEPLOYMENT_PROFILE is platform_profile.DeploymentProfile.LOCAL
        assert settings.WEB_WORKERS == 1
        assert settings.resolved_deployment_topology.requires_shared_state is False
        assert settings.resolved_state_uri == "memory://"

    def test_storage_uri_defaults_to_local(self):
        settings = core_config.Settings(_env_file=None)
        assert settings.resolved_storage_uri == "local://"

    def test_storage_uri_explicit_value_used(self):
        settings = core_config.Settings(_env_file=None, STORAGE_URI="s3://bucket/thumbs")
        assert settings.resolved_storage_uri == "s3://bucket/thumbs"

    def test_events_uri_defaults_to_memory(self):
        settings = core_config.Settings(_env_file=None)
        assert settings.resolved_events_uri == "memory://"

    def test_events_uri_prefers_explicit_over_redis_url(self):
        settings = core_config.Settings(
            _env_file=None,
            EVENTS_URI="redis://events:6379/1",
            REDIS_URL="redis://shared:6379/0",
        )
        assert settings.resolved_events_uri == "redis://events:6379/1"

    def test_events_uri_falls_back_to_redis_url(self):
        settings = core_config.Settings(_env_file=None, REDIS_URL="redis://shared:6379/0")
        assert settings.resolved_events_uri == "redis://shared:6379/0"

    def test_event_log_enabled_defaults_true(self):
        settings = core_config.Settings(_env_file=None)
        assert settings.EVENT_LOG_ENABLED is True

    def test_event_log_can_be_disabled(self):
        settings = core_config.Settings(_env_file=None, EVENT_LOG_ENABLED=False)
        assert settings.EVENT_LOG_ENABLED is False

    def test_lock_uri_defaults_to_noop_locally(self):
        settings = core_config.Settings(_env_file=None)
        assert settings.resolved_lock_uri == "noop://"

    def test_lock_uri_defaults_to_pg_for_distributed(self):
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DEPLOYMENT_PROFILE="distributed",
            REDIS_URL="redis://shared:6379/0",
            STORAGE_URI="s3://bucket/thumbs",
        )
        assert settings.resolved_lock_uri == "postgres-advisory://"

    def test_lock_uri_explicit_value_used(self):
        settings = core_config.Settings(_env_file=None, LOCK_URI="postgres-advisory://custom")
        assert settings.resolved_lock_uri == "postgres-advisory://custom"

    def test_lock_uri_defaults_to_pg_for_multi_worker(self):
        # A multi-worker local deployment runs more than one process, so the lock
        # default must coordinate via the shared database, not an in-process noop.
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="production",
            WEB_WORKERS=2,
            REDIS_URL="redis://shared:6379/0",
        )
        assert settings.resolved_lock_uri == "postgres-advisory://"

    def test_state_uri_precedence_over_redis_url(self):
        settings = core_config.Settings(
            _env_file=None,
            STATE_URI="memory://",
            REDIS_URL="redis://localhost:6379/0",
        )
        assert settings.resolved_state_uri == "memory://"

    def test_redis_url_used_when_state_uri_unset(self):
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DEPLOYMENT_PROFILE="distributed",
            REDIS_URL="redis://localhost:6379/0",
            STORAGE_URI="s3://bucket/thumbs",
        )
        assert settings.resolved_state_uri == "redis://localhost:6379/0"

    def test_profile_parsed_from_env_value(self):
        # development bypasses the topology fail-fast, isolating profile parsing.
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="development",
            DEPLOYMENT_PROFILE=" Distributed ",
        )
        assert settings.DEPLOYMENT_PROFILE is platform_profile.DeploymentProfile.DISTRIBUTED

    def test_invalid_profile_rejected(self):
        with pytest.raises(ValidationError):
            core_config.Settings(_env_file=None, DEPLOYMENT_PROFILE="distributd")

    def test_distributed_memory_state_fails_fast(self):
        with pytest.raises(ValidationError) as exc_info:
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="production",
                DEPLOYMENT_PROFILE="distributed",
                STATE_URI="memory://",
            )
        assert "process-local memory" in str(exc_info.value)

    def test_distributed_without_state_config_fails_fast(self):
        with pytest.raises(ValidationError):
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="production",
                DEPLOYMENT_PROFILE="distributed",
            )

    def test_multi_worker_memory_state_fails_fast(self):
        with pytest.raises(ValidationError):
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="production",
                WEB_WORKERS=2,
                STATE_URI="memory://",
            )

    def test_unrecognized_state_scheme_fails_fast(self):
        with pytest.raises(ValidationError) as exc_info:
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="production",
                DEPLOYMENT_PROFILE="distributed",
                STATE_URI="postgres://x",
            )
        assert "unrecognized storage scheme" in str(exc_info.value)

    def test_distributed_all_shared_backends_ok(self):
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DEPLOYMENT_PROFILE="distributed",
            REDIS_URL="redis://localhost:6379/0",
            STORAGE_URI="s3://bucket/thumbs",
        )
        assert settings.resolved_deployment_topology.requires_shared_state is True
        assert settings.resolved_state_uri == "redis://localhost:6379/0"
        assert settings.resolved_events_uri == "redis://localhost:6379/0"
        assert settings.resolved_storage_uri == "s3://bucket/thumbs"

    def test_distributed_memory_events_fails_fast(self):
        # State and storage are shared; the event bus falls back to in-process
        # memory (no EVENTS_URI/REDIS_URL) — fatal under the distributed profile.
        with pytest.raises(ValidationError) as exc_info:
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="production",
                DEPLOYMENT_PROFILE="distributed",
                STATE_URI="redis://localhost:6379/0",
                STORAGE_URI="s3://bucket/thumbs",
            )
        assert "EVENTS_URI" in str(exc_info.value)
        assert "process-local memory" in str(exc_info.value)

    def test_distributed_local_storage_fails_fast(self):
        # State and events are shared via REDIS_URL; storage falls back to the
        # local filesystem (no STORAGE_URI) — fatal under the distributed profile.
        with pytest.raises(ValidationError) as exc_info:
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="production",
                DEPLOYMENT_PROFILE="distributed",
                REDIS_URL="redis://localhost:6379/0",
            )
        assert "STORAGE_URI" in str(exc_info.value)
        assert "local filesystem" in str(exc_info.value)

    def test_multi_worker_local_storage_stays_local(self):
        # Multiple workers on one host share the disk, so local storage is fine;
        # only the cross-process backends (state, events) must be shared.
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="production",
            WEB_WORKERS=2,
            REDIS_URL="redis://localhost:6379/0",
        )
        assert settings.resolved_storage_uri == "local://"
        assert settings.resolved_state_uri == "redis://localhost:6379/0"
        assert settings.resolved_events_uri == "redis://localhost:6379/0"

    def test_distributed_noop_lock_fails_fast(self):
        # State, events, and storage are all shared; an explicit noop lock is the
        # remaining misconfiguration — fatal because replicas would each run jobs.
        with pytest.raises(ValidationError) as exc_info:
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="production",
                DEPLOYMENT_PROFILE="distributed",
                REDIS_URL="redis://localhost:6379/0",
                STORAGE_URI="s3://bucket/thumbs",
                LOCK_URI="noop://",
            )
        assert "LOCK_URI" in str(exc_info.value)
        assert "no-op lock" in str(exc_info.value)

    def test_multi_worker_noop_lock_fails_fast(self):
        # Multi-worker local shares state/events via Redis, but an explicit noop
        # lock still cannot coordinate the scheduler across the worker processes.
        with pytest.raises(ValidationError) as exc_info:
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="production",
                WEB_WORKERS=2,
                REDIS_URL="redis://localhost:6379/0",
                LOCK_URI="noop://",
            )
        assert "LOCK_URI" in str(exc_info.value)

    def test_local_single_worker_memory_ok_in_production(self):
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="production",
            STATE_URI="memory://",
        )
        assert settings.DEPLOYMENT_PROFILE is platform_profile.DeploymentProfile.LOCAL

    def test_development_distributed_memory_not_fatal(self):
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="development",
            DEPLOYMENT_PROFILE="distributed",
            STATE_URI="memory://",
        )
        assert settings.DEPLOYMENT_PROFILE is platform_profile.DeploymentProfile.DISTRIBUTED

    def test_development_multi_worker_warns(self):
        with patch("core.config.logger") as mock_logger:
            core_config.Settings(_env_file=None, ENVIRONMENT="development", WEB_WORKERS=3)

        assert "WEB_WORKERS>1 or a non-local deployment profile" in str(mock_logger.warning.call_args)

    def test_development_distributed_warns(self):
        with patch("core.config.logger") as mock_logger:
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="development",
                DEPLOYMENT_PROFILE="distributed",
            )

        assert "WEB_WORKERS>1 or a non-local deployment profile" in str(mock_logger.warning.call_args)

    def test_development_custom_warns(self):
        with patch("core.config.logger") as mock_logger:
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="development",
                DEPLOYMENT_PROFILE="custom",
                STATE_URI="memory://",
                EVENTS_URI="memory://",
                STORAGE_URI="local://",
                LOCK_URI="noop://",
            )

        assert "WEB_WORKERS>1 or a non-local deployment profile" in str(mock_logger.warning.call_args)

    def test_development_local_single_worker_is_silent(self):
        with patch("core.config.logger") as mock_logger:
            core_config.Settings(_env_file=None, ENVIRONMENT="development")

        mock_logger.warning.assert_not_called()

    def test_custom_profile_memory_not_fatal(self):
        # 'custom' promises no defaults, so nothing can contradict one and the
        # consistency rules are waived - but it must still name every capability.
        settings = core_config.Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DEPLOYMENT_PROFILE="custom",
            WEB_WORKERS=4,
            STATE_URI="memory://",
            EVENTS_URI="memory://",
            STORAGE_URI="local://",
            LOCK_URI="noop://",
        )
        assert settings.WEB_WORKERS == 4

    def test_custom_profile_must_name_every_capability(self):
        # Only 'local' carries capability defaults; the substrate refuses to
        # guess for any other profile, so this has to fail here first.
        with pytest.raises(ValidationError) as exc_info:
            core_config.Settings(
                _env_file=None,
                ENVIRONMENT="production",
                DEPLOYMENT_PROFILE="custom",
                STATE_URI="memory://",
            )
        assert "STORAGE_URI must be set explicitly" in str(exc_info.value)

    def test_web_workers_invalid_defaults_to_one(self):
        settings = core_config.Settings(_env_file=None, WEB_WORKERS="not-a-number")
        assert settings.WEB_WORKERS == 1

    def test_web_workers_clamped_to_at_least_one(self):
        settings = core_config.Settings(_env_file=None, WEB_WORKERS=0)
        assert settings.WEB_WORKERS == 1
