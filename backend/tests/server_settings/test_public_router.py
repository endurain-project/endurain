"""The unauthenticated server-settings routes on the production application."""

from sqlalchemy import delete

import core.config as core_config
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.models as server_settings_models
from tests._factories.server_settings import edit_server_settings

_PUBLIC_URL = f"{core_config.ROOT_PATH}/public/server-settings"
_ADMIN_ONLY = (
    "signup_require_admin_approval",
    "signup_sso_enabled",
    "password_breach_check_enabled",
    "require_mfa",
    "tileserver_api_key",
    "geocoding_api_key",
    "session_idle_timeout_hours",
    "access_token_expire_minutes",
    "version",
    "id",
)


class TestReadPublicServerSettings:
    def test_an_anonymous_client_reads_the_settings_the_sign_in_page_needs(self, client, committed_sessions):
        with committed_sessions() as db:
            edit_server_settings(db, signup_enabled=True, sso_enabled=True, units="imperial")
            db.commit()

        response = client.get(_PUBLIC_URL)

        assert response.status_code == 200
        body = response.json()
        assert (body["signup_enabled"], body["sso_enabled"], body["units"]) == (True, True, "imperial")
        assert body["login_photo_set"] is False
        assert body["allowed_redirect_uris"] == sorted(core_config.settings.ALLOWED_REDIRECT_URIS)

    def test_no_admin_only_setting_or_secret_is_exposed(self, client, committed_sessions):
        with committed_sessions() as db:
            edit_server_settings(db, tileserver_api_key="tile-key", geocoding_api_key="geo-key", require_mfa="everyone")
            db.commit()

        response = client.get(_PUBLIC_URL)

        for field in _ADMIN_ONLY:
            assert field not in response.json()
        assert "tile-key" not in response.text
        assert "geo-key" not in response.text

    def test_a_missing_settings_row_is_a_503(self, client, committed_sessions):
        with committed_sessions() as db:
            db.execute(delete(server_settings_models.ServerSettings))
            db.commit()

        assert client.get(_PUBLIC_URL).status_code == 503


class TestListTileMapsTemplates:
    def test_an_anonymous_client_lists_every_built_in_template(self, client):
        response = client.get(f"{_PUBLIC_URL}/tile-maps-templates")

        assert response.status_code == 200
        templates = response.json()
        assert {template["template_id"] for template in templates} == set(server_settings_constants.TILE_MAPS_TEMPLATES)
        openstreetmap = next(template for template in templates if template["template_id"] == "openstreetmap")
        assert openstreetmap["url_template"] == server_settings_constants.DEFAULT_TILE_URL
