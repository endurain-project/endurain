"""The admin server-settings routes on the production application: read, edit, step-up, secrets and the tile source."""

import threading

import jasil.runtime as jasil_runtime
import pytest
import sqlalchemy as sa
from jasil.audit.models import AuditLog

import modules.server_settings.change_utils as server_settings_change_utils
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.events as server_settings_events
import modules.server_settings.models as server_settings_models
from tests._factories.server_settings import edit_server_settings
from tests.server_settings.conftest import INTERNAL_HOST, SETTINGS_URL, STEP_UP, editable_settings, put_settings

#: A value that differs from the seeded one, for each setting whose change needs the administrator's step-up.
_SECURITY_CHANGES: dict[str, object] = {
    "signup_enabled": True,
    "signup_sso_enabled": True,
    "signup_require_admin_approval": True,
    "signup_require_email_verification": True,
    "sso_enabled": True,
    "sso_auto_redirect": True,
    "local_login_enabled": False,
    "password_length_regular_users": 12,
    "password_length_admin_users": 16,
    "password_breach_check_enabled": True,
    "require_mfa": "administrators",
    "session_idle_timeout_enabled": False,
    "session_idle_timeout_hours": 4,
    "session_absolute_timeout_hours": 100,
    "access_token_expire_minutes": 30,
    "refresh_token_expire_days": 14,
    "api_key_max_lifetime_days": 30,
    "public_shareable_links_user_info": True,
    "geocoding_service": "photon",
    "geocoding_host": "photon.example.org",
    "geocoding_use_https": False,
    "tileserver_url": "https://tiles.example.org/{z}/{x}/{y}.png",
}


def _stored(committed_sessions):
    with committed_sessions() as db:
        stored = server_settings_crud.get_server_settings(db)
    assert stored is not None
    return stored


def _audit_rows(committed_sessions, action_id: str) -> list[AuditLog]:
    with committed_sessions() as db:
        rows = list(db.scalars(sa.select(AuditLog).where(AuditLog.action_id == action_id)))
        db.expunge_all()
    return rows


@pytest.fixture
def tile_events() -> list[dict]:
    """The payloads of the tile-settings events the bus delivers during the test."""
    payloads: list[dict] = []
    jasil_runtime.get_active_platform().events.subscribe(
        server_settings_events.TILE_SETTINGS_CHANGED, lambda event: payloads.append(event.payload)
    )
    return payloads


class TestReadServerSettings:
    def test_the_admin_read_carries_the_version_as_its_etag_and_no_api_key(self, admin_client):
        response = admin_client.get(SETTINGS_URL)

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        body = response.json()
        assert body["version"] == 1
        assert "tileserver_api_key" not in body
        assert "geocoding_api_key" not in body
        assert (body["tileserver_api_key_set"], body["geocoding_api_key_set"]) == (False, False)

    def test_the_read_lists_the_settings_that_need_the_step_up(self, admin_client):
        body = admin_client.get(SETTINGS_URL).json()

        assert body["step_up_fields"] == sorted(server_settings_constants.SECURITY_FIELDS)
        assert body["logs_viewer_enabled"] is True

    def test_a_stored_api_key_shows_only_as_a_flag(self, admin_client, committed_sessions):
        with committed_sessions() as db:
            edit_server_settings(db, tileserver_api_key="tile-key", geocoding_api_key="geo-key")
            db.commit()

        response = admin_client.get(SETTINGS_URL)

        body = response.json()
        assert (body["tileserver_api_key_set"], body["geocoding_api_key_set"]) == (True, True)
        assert "tile-key" not in response.text
        assert "geo-key" not in response.text

    def test_a_missing_settings_row_is_a_service_error_not_a_missing_resource(self, admin_client, committed_sessions):
        with committed_sessions() as db:
            db.execute(sa.delete(server_settings_models.ServerSettings))
            db.commit()

        response = admin_client.get(SETTINGS_URL)

        assert response.status_code == 503


class TestEditServerSettings:
    def test_a_change_that_needs_no_step_up_is_saved_with_a_new_version(self, admin_client, committed_sessions):
        response = put_settings(admin_client, num_records_per_page=50, currency="dollar")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        assert (response.json()["num_records_per_page"], response.json()["version"]) == (50, 2)
        stored = _stored(committed_sessions)
        assert (stored.num_records_per_page, stored.currency, stored.version) == (50, "dollar", 2)
        assert admin_client.get(SETTINGS_URL).json() == response.json()

    def test_a_saved_change_is_audited_by_field_name_only(self, admin_client, committed_sessions):
        put_settings(admin_client, num_records_per_page=50, units="imperial")

        (row,) = _audit_rows(committed_sessions, "server_settings.settings.update")
        assert row.details == {"changed_fields": ["num_records_per_page", "units"]}

    def test_resending_the_stored_settings_changes_and_audits_nothing(self, admin_client, committed_sessions):
        response = put_settings(admin_client)

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert _stored(committed_sessions).version == 1
        assert _audit_rows(committed_sessions, "server_settings.settings.update") == []

    def test_a_stale_tag_is_refused_and_writes_nothing(self, admin_client, committed_sessions):
        put_settings(admin_client, num_records_per_page=50)

        response = put_settings(admin_client, at=1, num_records_per_page=75)

        assert response.status_code == 412
        assert _stored(committed_sessions).num_records_per_page == 50

    def test_a_stale_tag_is_refused_before_the_step_up_is_checked(self, admin_client, committed_sessions):
        put_settings(admin_client, num_records_per_page=50)

        response = put_settings(admin_client, at=1, signup_enabled=True, step_up={"current_password": "wrong"})

        assert response.status_code == 412

    @pytest.mark.parametrize("field", ["id", "version", "login_photo_set", "step_up_fields", "tileserver_api_key_set"])
    def test_a_field_the_server_owns_is_a_422(self, admin_client, field):
        response = put_settings(admin_client, **{field: 7})

        assert response.status_code == 422

    def test_an_access_token_lifetime_not_below_the_enforced_idle_timeout_is_a_422_naming_the_rule(
        self, admin_client, committed_sessions
    ):
        response = put_settings(
            admin_client,
            session_idle_timeout_enabled=True,
            session_idle_timeout_hours=1,
            access_token_expire_minutes=60,
            step_up=STEP_UP,
        )

        assert response.status_code == 422
        assert "idle timeout" in response.text.lower()
        assert _stored(committed_sessions).version == 1

    def test_an_unknown_mfa_requirement_is_a_422(self, admin_client):
        response = put_settings(admin_client, require_mfa="sometimes", step_up=STEP_UP)

        assert response.status_code == 422

    def test_the_mfa_requirement_is_saved_and_read_back(self, admin_client, committed_sessions):
        response = put_settings(admin_client, require_mfa="everyone", step_up=STEP_UP)

        assert response.status_code == 200
        assert response.json()["require_mfa"] == "everyone"
        assert _stored(committed_sessions).require_mfa == "everyone"

    def test_two_saves_holding_the_same_tag_apply_one_and_refuse_the_other(self, admin_client, committed_sessions):
        bodies = [editable_settings(admin_client, num_records_per_page=n) for n in (31, 32)]
        barrier = threading.Barrier(2)
        statuses: list[int] = []

        def save(body: dict) -> None:
            barrier.wait()
            statuses.append(admin_client.put(SETTINGS_URL, json=body, headers={"If-Match": '"1"'}).status_code)

        threads = [threading.Thread(target=save, args=(body,)) for body in bodies]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        stored = _stored(committed_sessions)
        assert sorted(statuses) == [200, 412]
        assert stored.version == 2
        assert stored.num_records_per_page in (31, 32)


class TestStepUp:
    @pytest.mark.parametrize("field", sorted(_SECURITY_CHANGES))
    def test_changing_a_security_setting_without_a_step_up_is_refused_and_writes_nothing(
        self, admin_client, committed_sessions, dns, field
    ):
        response = put_settings(admin_client, **{field: _SECURITY_CHANGES[field]})

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"
        assert _stored(committed_sessions).version == 1

    @pytest.mark.parametrize("field", sorted(_SECURITY_CHANGES))
    def test_changing_a_security_setting_with_the_step_up_is_saved(self, admin_client, committed_sessions, dns, field):
        response = put_settings(admin_client, step_up=STEP_UP, **{field: _SECURITY_CHANGES[field]})

        assert response.status_code == 200
        assert response.json()[field] == _SECURITY_CHANGES[field]
        assert getattr(_stored(committed_sessions), field) == _SECURITY_CHANGES[field]

    def test_the_security_changes_cover_every_setting_that_needs_a_step_up(self):
        assert set(_SECURITY_CHANGES) == server_settings_constants.SECURITY_FIELDS

    def test_a_wrong_password_is_refused_and_writes_nothing(self, admin_client, committed_sessions):
        response = put_settings(admin_client, signup_enabled=True, step_up={"current_password": "not-my-password"})

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"
        assert _stored(committed_sessions).signup_enabled is False

    def test_re_sending_the_stored_security_values_needs_no_step_up(self, admin_client):
        response = put_settings(admin_client, num_records_per_page=50)

        assert response.status_code == 200

    def test_a_non_security_change_needs_no_step_up_even_when_one_is_sent(self, admin_client, committed_sessions):
        response = put_settings(admin_client, num_records_per_page=50, step_up=STEP_UP)

        assert response.status_code == 200
        assert _stored(committed_sessions).num_records_per_page == 50


class TestApiKeys:
    def test_a_new_api_key_is_stored_encrypted_and_never_returned(self, admin_client, committed_sessions):
        response = put_settings(admin_client, tileserver_api_key="tile-key")

        assert response.status_code == 200
        assert response.json()["tileserver_api_key_set"] is True
        assert "tile-key" not in response.text
        stored_token = _stored(committed_sessions).tileserver_api_key
        assert stored_token not in (None, "tile-key")
        assert server_settings_change_utils.decrypt_secret(stored_token, "key") == "tile-key"

    def test_a_key_audit_row_names_the_field_and_never_the_key(self, admin_client, committed_sessions):
        put_settings(admin_client, geocoding_api_key="geo-key")

        (row,) = _audit_rows(committed_sessions, "server_settings.settings.update")
        assert row.details == {"changed_fields": ["geocoding_api_key"]}

    def test_a_save_that_omits_the_key_keeps_the_stored_token(self, admin_client, committed_sessions):
        put_settings(admin_client, tileserver_api_key="tile-key")
        token = _stored(committed_sessions).tileserver_api_key

        response = put_settings(admin_client, at=2, num_records_per_page=50)

        assert response.status_code == 200
        assert _stored(committed_sessions).tileserver_api_key == token

    def test_re_sending_the_same_key_keeps_the_token_and_the_version(self, admin_client, committed_sessions):
        put_settings(admin_client, tileserver_api_key="tile-key")
        token = _stored(committed_sessions).tileserver_api_key

        response = put_settings(admin_client, at=2, tileserver_api_key="tile-key")

        assert response.headers["ETag"] == '"2"'
        assert _stored(committed_sessions).tileserver_api_key == token

    @pytest.mark.parametrize("cleared", [None, ""])
    def test_clearing_the_key_removes_it(self, admin_client, committed_sessions, cleared):
        put_settings(admin_client, tileserver_api_key="tile-key")

        response = put_settings(admin_client, at=2, tileserver_api_key=cleared)

        assert response.status_code == 200
        assert response.json()["tileserver_api_key_set"] is False
        assert _stored(committed_sessions).tileserver_api_key is None

    def test_a_stored_key_that_cannot_be_decrypted_can_be_replaced(self, admin_client, committed_sessions):
        with committed_sessions() as db:
            db.execute(sa.update(server_settings_models.ServerSettings).values(tileserver_api_key="not-a-token"))
            db.commit()

        response = put_settings(admin_client, at=1, tileserver_api_key="fresh-key")

        assert response.status_code == 200
        token = _stored(committed_sessions).tileserver_api_key
        assert server_settings_change_utils.decrypt_secret(token, "key") == "fresh-key"

    def test_the_two_keys_are_independent(self, admin_client, committed_sessions):
        put_settings(admin_client, tileserver_api_key="tile-key", geocoding_api_key="geo-key")
        geocoding_token = _stored(committed_sessions).geocoding_api_key

        put_settings(admin_client, at=2, tileserver_api_key=None)

        stored = _stored(committed_sessions)
        assert stored.tileserver_api_key is None
        assert stored.geocoding_api_key == geocoding_token


class TestTileServer:
    def test_a_url_resolving_to_a_private_address_is_refused_and_writes_nothing(
        self, admin_client, committed_sessions, dns
    ):
        response = put_settings(
            admin_client, step_up=STEP_UP, tileserver_url=f"https://{INTERNAL_HOST}/{{z}}/{{x}}/{{y}}.png"
        )

        assert response.status_code == 400
        assert _stored(committed_sessions).version == 1

    def test_a_url_with_a_placeholder_that_cannot_be_filled_is_a_422(self, admin_client, committed_sessions, dns):
        response = put_settings(
            admin_client, step_up=STEP_UP, tileserver_url="https://tiles.example.org/{z}/{x}/{q}.png"
        )

        assert response.status_code == 422
        assert _stored(committed_sessions).version == 1

    @pytest.mark.parametrize("template_id", sorted(server_settings_constants.TILE_MAPS_TEMPLATES))
    def test_every_built_in_template_can_be_saved(self, admin_client, committed_sessions, dns, template_id):
        template = server_settings_constants.TILE_MAPS_TEMPLATES[template_id]

        response = put_settings(
            admin_client,
            step_up=STEP_UP,
            tileserver_url=template["url_template"],
            tileserver_attribution=template["attribution"],
            map_background_color=template["map_background_color"],
        )

        assert response.status_code == 200
        assert _stored(committed_sessions).tileserver_url == template["url_template"]

    def test_a_tile_change_publishes_one_event_naming_only_the_changed_map_fields(self, admin_client, tile_events, dns):
        put_settings(admin_client, step_up=STEP_UP, tileserver_url="https://tiles.example.org/{z}/{x}/{y}.png")

        (payload,) = tile_events
        assert payload["changed_fields"] == ["tileserver_url"]
        assert payload["regenerate_thumbnails"] is False

    def test_the_event_asks_for_new_thumbnails_when_the_setting_says_so(self, admin_client, tile_events):
        put_settings(admin_client, tileserver_regenerate_thumbnails_on_change=True)

        put_settings(admin_client, at=2, map_background_color="#101010")

        (payload,) = tile_events
        assert payload["changed_fields"] == ["map_background_color"]
        assert payload["regenerate_thumbnails"] is True

    def test_a_change_outside_the_tile_source_publishes_nothing(self, admin_client, tile_events):
        put_settings(admin_client, num_records_per_page=50)

        assert tile_events == []

    def test_the_new_tile_domain_is_allowed_at_once_in_this_process(self, admin_client, app, dns):
        put_settings(admin_client, step_up=STEP_UP, tileserver_url="https://tiles.example.org/{z}/{x}/{y}.png")

        assert "https://tiles.example.org" in app.state.allowed_tile_domains

    def test_the_dns_check_does_not_hold_the_settings_row_lock(self, admin_client, committed_sessions, dns):
        locked: list[bool] = []

        def try_to_lock(_name: str) -> None:
            with committed_sessions() as other:
                try:
                    other.execute(sa.text("SELECT 1 FROM server_settings WHERE id = 1 FOR UPDATE NOWAIT"))
                    locked.append(True)
                except sa.exc.OperationalError:
                    locked.append(False)

        dns.on_lookup = try_to_lock

        response = put_settings(
            admin_client, step_up=STEP_UP, tileserver_url="https://tiles.example.org/{z}/{x}/{y}.png"
        )

        assert response.status_code == 200
        assert locked == [True]


class TestGeocoding:
    def test_a_save_that_leaves_geocoding_alone_does_no_lookup(self, admin_client, dns):
        response = put_settings(admin_client, num_records_per_page=50)

        assert response.status_code == 200
        assert dns.names == []

    def test_the_default_host_is_checked_when_none_is_set(self, admin_client, dns):
        response = put_settings(admin_client, step_up=STEP_UP, geocoding_service="photon", geocoding_host=None)

        assert response.status_code == 200
        assert dns.names == ["photon.komoot.io"]

    def test_a_custom_host_is_checked_and_saved(self, admin_client, committed_sessions, dns):
        response = put_settings(
            admin_client, step_up=STEP_UP, geocoding_service="nominatim", geocoding_host="geo.example.org"
        )

        assert response.status_code == 200
        assert dns.names == ["geo.example.org"]
        assert _stored(committed_sessions).geocoding_host == "geo.example.org"

    def test_a_host_resolving_to_a_private_address_is_refused_and_writes_nothing(
        self, admin_client, committed_sessions, dns
    ):
        response = put_settings(
            admin_client, step_up=STEP_UP, geocoding_service="nominatim", geocoding_host=INTERNAL_HOST
        )

        assert response.status_code == 400
        assert "SSRF_ALLOWED_HOSTS" in response.text
        assert _stored(committed_sessions).version == 1

    def test_geocode_maps_co_without_an_api_key_is_refused(self, admin_client, committed_sessions, dns):
        response = put_settings(admin_client, step_up=STEP_UP, geocoding_service="geocode", geocoding_host=None)

        assert response.status_code == 400
        assert "API key" in response.text
        assert _stored(committed_sessions).version == 1

    def test_geocode_maps_co_with_a_new_key_is_saved_and_the_key_stored_encrypted(
        self, admin_client, committed_sessions, dns
    ):
        response = put_settings(
            admin_client, step_up=STEP_UP, geocoding_service="geocode", geocoding_host=None, geocoding_api_key="geo-key"
        )

        assert response.status_code == 200
        token = _stored(committed_sessions).geocoding_api_key
        assert server_settings_change_utils.decrypt_secret(token, "key") == "geo-key"
        assert dns.names == []

    def test_geocode_maps_co_with_a_stored_key_and_none_sent_is_saved(self, admin_client, committed_sessions, dns):
        with committed_sessions() as db:
            edit_server_settings(db, geocoding_api_key="geo-key")
            db.commit()

        response = put_settings(admin_client, at=2, step_up=STEP_UP, geocoding_service="geocode", geocoding_host=None)

        assert response.status_code == 200
        assert _stored(committed_sessions).geocoding_service == "geocode"

    def test_geocode_maps_co_with_the_key_cleared_is_refused(self, admin_client, committed_sessions, dns):
        with committed_sessions() as db:
            edit_server_settings(db, geocoding_api_key="geo-key")
            db.commit()

        response = put_settings(
            admin_client,
            at=2,
            step_up=STEP_UP,
            geocoding_service="geocode",
            geocoding_host=None,
            geocoding_api_key=None,
        )

        assert response.status_code == 400
