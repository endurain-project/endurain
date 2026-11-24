"""Tests that the OpenAPI schema is served only where the documentation pages are."""

import pytest
from fastapi.testclient import TestClient

import core.config as core_config


@pytest.fixture
def client_for(app, monkeypatch):
    """Return a function that builds the production application for an environment."""
    import main as main_module

    def build(environment: str) -> TestClient:
        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", environment)
        return TestClient(main_module.create_app())

    return build


@pytest.mark.parametrize("environment", ["development", "demo"])
def test_schema_is_served_in_development_and_demo(client_for, environment):
    response = client_for(environment).get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Endurain"


@pytest.mark.parametrize("path", ["/openapi.json", f"{core_config.ROOT_PATH}/openapi.json"])
def test_schema_is_not_served_in_production(client_for, path):
    response = client_for("production").get(path)

    assert response.status_code == 404
    assert "<html" not in response.text.lower()
