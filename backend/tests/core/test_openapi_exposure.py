"""Tests that the OpenAPI schema is served only where the documentation pages are."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import core.config as core_config
import core.logger as core_logger


def _client(environment: str) -> TestClient:
    """Build the real application for an environment, skipping the startup pre-flight checks."""
    with (
        patch.object(core_config.settings, "ENVIRONMENT", environment),
        patch.object(core_config, "check_deprecated_env_vars"),
        patch.object(core_config, "check_required_env_vars"),
        patch.object(core_config, "warn_unsafe_settings"),
        patch.object(core_config, "check_required_dirs"),
        patch.object(core_logger, "setup_main_logger"),
    ):
        # main builds an app at import time, so it is imported under the same patches.
        import main as main_module

        return TestClient(main_module.create_app())


@pytest.mark.parametrize("environment", ["development", "demo"])
def test_schema_is_served_in_development_and_demo(environment):
    response = _client(environment).get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Endurain"


@pytest.mark.parametrize("path", ["/openapi.json", f"{core_config.ROOT_PATH}/openapi.json"])
def test_schema_is_not_served_in_production(path):
    response = _client("production").get(path)

    assert response.status_code == 404
    assert "<html" not in response.text.lower()
