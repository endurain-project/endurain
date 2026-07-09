"""Tests for core.platform.capabilities."""

import core.platform.capabilities as platform_capabilities
import core.platform.profile as platform_profile


class TestStateSource:
    """Tests for the StateSource helper."""

    def test_backend_reflects_uri(self):
        source = platform_capabilities.StateSource("STATE_URI", "redis://localhost:6379/0")
        assert source.backend is platform_profile.StateBackendKind.REDIS

    def test_applies_defaults_true(self):
        source = platform_capabilities.StateSource("X", "memory://")
        assert source.applies is True
        assert source.backend is platform_profile.StateBackendKind.MEMORY


class TestBuildCapabilityReport:
    """Tests for build_capability_report() and CapabilityReport.render()."""

    def _report(self, profile, workers, uri, storage_backend="local", events_backend="in-process", lock_backend="none"):
        return platform_capabilities.build_capability_report(
            profile=profile,
            web_workers=workers,
            primary_state=platform_capabilities.StateSource("STATE_URI", uri),
            storage_backend=storage_backend,
            storage_source="ACTIVITY_THUMBNAILS_DIR",
            events_backend=events_backend,
            events_source="EVENTS_URI",
            lock_backend=lock_backend,
            lock_source="LOCK_URI",
        )

    def test_rows_cover_all_capabilities(self):
        report = self._report(platform_profile.DeploymentProfile.LOCAL, 1, "memory://")
        names = [row.name for row in report.rows]
        assert names == ["state", "storage", "events", "lock", "clock"]

    def test_state_row_reflects_primary_state(self):
        report = self._report(platform_profile.DeploymentProfile.DISTRIBUTED, 4, "redis://localhost:6379/0")
        state_row = next(row for row in report.rows if row.name == "state")
        assert state_row.backend == "redis"
        assert state_row.source == "STATE_URI"

    def test_storage_row_uses_source(self):
        report = self._report(platform_profile.DeploymentProfile.LOCAL, 1, "memory://")
        storage_row = next(row for row in report.rows if row.name == "storage")
        assert storage_row.backend == "local"
        assert storage_row.source == "ACTIVITY_THUMBNAILS_DIR"

    def test_storage_row_reflects_backend(self):
        report = self._report(platform_profile.DeploymentProfile.LOCAL, 1, "memory://", storage_backend="s3")
        storage_row = next(row for row in report.rows if row.name == "storage")
        assert storage_row.backend == "s3"

    def test_events_row_reflects_backend(self):
        report = self._report(platform_profile.DeploymentProfile.LOCAL, 1, "memory://", events_backend="redis")
        events_row = next(row for row in report.rows if row.name == "events")
        assert events_row.backend == "redis"

    def test_lock_row_reflects_backend(self):
        report = self._report(platform_profile.DeploymentProfile.LOCAL, 1, "memory://", lock_backend="pg")
        lock_row = next(row for row in report.rows if row.name == "lock")
        assert lock_row.backend == "pg"

    def test_render_contains_header_and_rows(self):
        report = self._report(platform_profile.DeploymentProfile.LOCAL, 1, "memory://")
        rendered = report.render()
        assert "Deployment profile: local" in rendered
        assert "WEB_WORKERS=1" in rendered
        assert "requires_shared_state=False" in rendered
        assert "state" in rendered
        assert "memory" in rendered
        assert "ACTIVITY_THUMBNAILS_DIR" in rendered
        # header + five capability rows
        assert len(rendered.splitlines()) == 6

    def test_render_reports_shared_state_for_distributed(self):
        report = self._report(platform_profile.DeploymentProfile.DISTRIBUTED, 1, "redis://localhost:6379/0")
        assert "requires_shared_state=True" in report.render()


class TestCheckStateConsistency:
    """Tests for check_state_consistency()."""

    def _check(self, *, profile, workers, environment, sources):
        return platform_capabilities.check_state_consistency(
            profile=profile,
            web_workers=workers,
            environment=environment,
            state_sources=sources,
        )

    def test_development_never_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=4,
            environment="development",
            sources=[platform_capabilities.StateSource("STATE_URI", "memory://")],
        )
        assert issues == []

    def test_custom_profile_never_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.CUSTOM,
            workers=4,
            environment="production",
            sources=[platform_capabilities.StateSource("STATE_URI", "memory://")],
        )
        assert issues == []

    def test_local_single_worker_memory_is_ok(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.LOCAL,
            workers=1,
            environment="production",
            sources=[platform_capabilities.StateSource("STATE_URI", "memory://")],
        )
        assert issues == []

    def test_distributed_memory_is_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=1,
            environment="production",
            sources=[platform_capabilities.StateSource("STATE_URI", "memory://")],
        )
        assert len(issues) == 1
        assert "STATE_URI" in issues[0]
        assert "process-local memory" in issues[0]

    def test_multi_worker_memory_is_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.LOCAL,
            workers=2,
            environment="production",
            sources=[platform_capabilities.StateSource("STATE_URI", "memory://")],
        )
        assert len(issues) == 1

    def test_distributed_redis_is_ok(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=4,
            environment="production",
            sources=[platform_capabilities.StateSource("STATE_URI", "redis://localhost:6379/0")],
        )
        assert issues == []

    def test_inapplicable_memory_source_is_ignored(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=1,
            environment="production",
            sources=[platform_capabilities.StateSource("STATE_URI", "memory://", applies=False)],
        )
        assert issues == []

    def test_only_memory_sources_flagged_when_mixed(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=1,
            environment="production",
            sources=[
                platform_capabilities.StateSource("REDIS_URL", "redis://localhost:6379/0"),
                platform_capabilities.StateSource("STATE_URI", "memory://"),
            ],
        )
        assert len(issues) == 1
        assert "STATE_URI" in issues[0]

    def test_unrecognized_scheme_is_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=1,
            environment="production",
            sources=[platform_capabilities.StateSource("STATE_URI", "postgres://x")],
        )
        assert len(issues) == 1
        assert "unrecognized storage scheme" in issues[0]

    def test_event_bus_memory_source_flagged(self):
        # The event bus shares the memory/redis vocabulary, so a memory-backed
        # EVENTS_URI is flagged exactly like a state store.
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=1,
            environment="production",
            sources=[
                platform_capabilities.StateSource("REDIS_URL", "redis://localhost:6379/0"),
                platform_capabilities.StateSource("EVENTS_URI", "memory://"),
            ],
        )
        assert len(issues) == 1
        assert "EVENTS_URI" in issues[0]
        assert "process-local memory" in issues[0]


class TestCheckStorageConsistency:
    """Tests for check_storage_consistency()."""

    def _check(self, *, profile, environment, storage_uri):
        return platform_capabilities.check_storage_consistency(
            profile=profile,
            environment=environment,
            storage_uri=storage_uri,
            storage_label="STORAGE_URI",
        )

    def test_distributed_local_storage_is_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            environment="production",
            storage_uri="local://",
        )
        assert len(issues) == 1
        assert "STORAGE_URI" in issues[0]
        assert "local filesystem" in issues[0]

    def test_distributed_s3_storage_is_ok(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            environment="production",
            storage_uri="s3://bucket/thumbs",
        )
        assert issues == []

    def test_local_profile_local_storage_is_ok(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.LOCAL,
            environment="production",
            storage_uri="local://",
        )
        assert issues == []

    def test_development_never_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            environment="development",
            storage_uri="local://",
        )
        assert issues == []

    def test_custom_profile_never_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.CUSTOM,
            environment="production",
            storage_uri="local://",
        )
        assert issues == []


class TestCheckLockConsistency:
    """Tests for check_lock_consistency()."""

    def _check(self, *, profile, workers, environment, lock_uri):
        return platform_capabilities.check_lock_consistency(
            profile=profile,
            web_workers=workers,
            environment=environment,
            lock_uri=lock_uri,
            lock_label="LOCK_URI",
        )

    def test_distributed_noop_is_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=1,
            environment="production",
            lock_uri="noop://",
        )
        assert len(issues) == 1
        assert "LOCK_URI" in issues[0]
        assert "no-op lock" in issues[0]

    def test_multi_worker_noop_is_fatal(self):
        # A multi-worker local deployment runs the scheduler in every worker
        # process, so an in-process noop lock cannot make jobs single-runner.
        issues = self._check(
            profile=platform_profile.DeploymentProfile.LOCAL,
            workers=2,
            environment="production",
            lock_uri="noop://",
        )
        assert len(issues) == 1
        assert "LOCK_URI" in issues[0]

    def test_distributed_pg_is_ok(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=4,
            environment="production",
            lock_uri="postgres-advisory://",
        )
        assert issues == []

    def test_local_single_worker_noop_is_ok(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.LOCAL,
            workers=1,
            environment="production",
            lock_uri="noop://",
        )
        assert issues == []

    def test_development_never_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.DISTRIBUTED,
            workers=4,
            environment="development",
            lock_uri="noop://",
        )
        assert issues == []

    def test_custom_profile_never_fatal(self):
        issues = self._check(
            profile=platform_profile.DeploymentProfile.CUSTOM,
            workers=4,
            environment="production",
            lock_uri="noop://",
        )
        assert issues == []
