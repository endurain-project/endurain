"""Tests for core.platform.deps."""

from types import SimpleNamespace

import core.platform.deps as platform_deps
from core.platform.container import build_platform
from core.platform.profile import DeploymentProfile


def _request_with_platform(platform):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(platform=platform)))


class TestPlatformDeps:
    def _platform(self, tmp_path):
        settings = SimpleNamespace(
            DEPLOYMENT_PROFILE=DeploymentProfile.LOCAL,
            DATA_DIR=str(tmp_path),
            resolved_state_uri="memory://",
            resolved_storage_uri="local://",
            resolved_events_uri="memory://",
            resolved_lock_uri="noop://",
            EVENT_LOG_ENABLED=False,
        )
        return build_platform(settings)

    def test_get_platform(self, tmp_path):
        platform = self._platform(tmp_path)
        request = _request_with_platform(platform)
        assert platform_deps.get_platform(request) is platform

    def test_get_each_port(self, tmp_path):
        platform = self._platform(tmp_path)
        request = _request_with_platform(platform)
        assert platform_deps.get_state(request) is platform.state
        assert platform_deps.get_storage(request) is platform.storage
        assert platform_deps.get_events(request) is platform.events
        assert platform_deps.get_lock(request) is platform.lock
        assert platform_deps.get_clock(request) is platform.clock
