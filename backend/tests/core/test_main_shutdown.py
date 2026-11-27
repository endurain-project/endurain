"""Tests for the order the backend stops its parts in on shutdown."""

from unittest.mock import MagicMock, patch

import pytest

import core.config as core_config
import core.logger as core_logger


@pytest.fixture
def main():
    """Import the application module under the patches that skip its start-up pre-flight checks."""
    with (
        patch.object(core_config, "check_deprecated_env_vars"),
        patch.object(core_config, "check_required_env_vars"),
        patch.object(core_config, "warn_unsafe_settings"),
        patch.object(core_config, "check_required_dirs"),
        patch.object(core_logger, "setup_main_logger"),
    ):
        import main as main_module

    return main_module


def test_shutdown_stops_what_uses_the_platform_before_the_platform(main):
    """Scheduler and pool jobs call into the platform, so it must outlive them; the scheduler goes first."""
    order = MagicMock()
    with (
        patch.object(main.core_scheduler, "stop_scheduler", order.stop_scheduler),
        patch.object(main.runtime_module_registry, "shutdown_module_pools", order.shutdown_module_pools),
        patch.object(main.core_network, "shutdown_ssrf_dns_executor", order.shutdown_ssrf_dns_executor),
        patch.object(main.jasil_lifecycle, "shutdown", order.platform_shutdown),
        patch.object(main.core_async_bridge, "set_main_loop", order.set_main_loop),
        patch.object(main.core_db_engine, "dispose", order.dispose),
    ):
        main.shutdown_event(MagicMock())

    names = [c[0] for c in order.mock_calls]
    assert names[0] == "stop_scheduler"
    assert names.index("shutdown_module_pools") < names.index("platform_shutdown")
    assert names.index("shutdown_ssrf_dns_executor") < names.index("platform_shutdown")
    assert names.index("platform_shutdown") < names.index("dispose")
