"""Tests for the server-settings write path.

The service is where the tile-URL network policy is enforced: the schema is also
what deserializes settings on every *read*, so a validator there would put a DNS
lookup on the read path of the whole app.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest

import core.exceptions as core_exceptions
import core.geocoding as core_geocoding
import core.mail as core_mail
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service


def _stored(**overrides) -> server_settings_schema.ServerSettingsRead:
    """Settings as the crud layer returns them (the tile API key still encrypted)."""
    values = dict(
        id=1,
        version=1,
        units="metric",
        public_shareable_links=False,
        public_shareable_links_user_info=False,
        login_photo_set=False,
        currency="euro",
        num_records_per_page=25,
        signup_enabled=False,
        signup_require_admin_approval=True,
        signup_require_email_verification=True,
        sso_enabled=False,
        local_login_enabled=True,
        sso_auto_redirect=False,
        tileserver_url="https://tiles.example.com/{z}/{x}/{y}.png",
        tileserver_attribution="Test",
        map_background_color="#dddddd",
        password_type="strict",
        tileserver_regenerate_thumbnails_on_change=False,
        password_length_regular_users=8,
        password_length_admin_users=12,
        tileserver_api_key="enc-old",
        geocoding_service="nominatim",
        geocoding_host=None,
        geocoding_use_https=True,
        geocoding_rate_limit=1.0,
        session_idle_timeout_enabled=False,
        session_idle_timeout_hours=1,
        session_absolute_timeout_hours=24,
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        read_notification_retention_days=90,
        geocoding_api_key=None,
    )
    values.update(overrides)
    return server_settings_schema.ServerSettingsRead(**values)


def _full_edit(stored: server_settings_schema.ServerSettingsRead, **overrides):
    """The whole record, the way the frontend sends it on every save (key in plain text)."""
    body = stored.model_dump(exclude={"id", "login_photo_set", "version"})
    body["tileserver_api_key"] = "plain-old"
    body.update(overrides)
    return server_settings_schema.ServerSettingsEdit(**body)


_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


@pytest.fixture
def edit_env():
    """Patch the collaborators of edit_server_settings and expose them."""
    stored = _stored()
    with (
        patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=stored),
        patch.object(
            server_settings_service.server_settings_crud,
            "edit_server_settings",
            side_effect=lambda attrs, db: stored.model_copy(update=attrs.model_dump(exclude_unset=True)),
        ) as write,
        patch.object(server_settings_service.server_settings_publishers, "publish_tile_settings_changed") as publish,
        patch.object(server_settings_service.core_network, "url_rejection_reason_bounded", return_value=None) as dns,
        patch.object(
            server_settings_service.core_cryptography,
            "decrypt_token_fernet",
            side_effect=lambda token: {"enc-old": "plain-old", "enc-new": "plain-new"}[token],
        ),
        patch.object(server_settings_service.core_cryptography, "encrypt_token_fernet", return_value="enc-new"),
    ):
        yield MagicMock(stored=stored, write=write, publish=publish, dns=dns)


class TestTileServerUrlIsCheckedOnWrite:
    def test_a_url_targeting_a_non_public_address_is_refused(self, edit_env):
        """The renderer refuses it too, but only later, in a background job.

        By then the admin has seen no error and the bad value is already stored.
        """
        db = MagicMock()
        edit_env.dns.return_value = "URL resolves to a non-public address"

        with pytest.raises(core_exceptions.InvalidInputError):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_url="https://internal.example.com/{z}/{x}/{y}.png"), db
            )

        edit_env.write.assert_not_called()
        db.commit.assert_not_called()

    def test_the_placeholders_are_filled_before_the_check(self, edit_env):
        """``{z}/{x}/{y}`` is not a parseable URL; the host is what matters."""
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_url="https://other.example.com/{z}/{x}/{y}.png"), MagicMock()
        )

        assert edit_env.dns.call_args.args[0] == "https://other.example.com/0/0/0.png"

    @pytest.mark.parametrize(
        "template", [t["url_template"] for t in server_settings_constants.TILE_MAPS_TEMPLATES.values()]
    )
    def test_every_builtin_template_can_be_saved(self, edit_env, template):
        """``{r}`` (Stadia retina) is dropped by the renderer, so it must not be a 400."""
        server_settings_service.edit_server_settings(_full_edit(edit_env.stored, tileserver_url=template), MagicMock())

        assert "{" not in edit_env.dns.call_args.args[0]

    def test_an_unfillable_placeholder_is_a_400_not_a_background_500(self, edit_env):
        """The renderer resolves the same template before every tile fetch."""
        with pytest.raises(core_exceptions.InvalidInputError):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_url="https://tiles.example.com/{}/{z}/{x}/{y}.png"), MagicMock()
            )

        edit_env.write.assert_not_called()


class TestOnlyRealChangesCount:
    def test_resending_the_unchanged_record_does_nothing(self, edit_env):
        """The frontend sends every field on every save; that must not look like a tile change."""
        db = MagicMock()

        result = server_settings_service.edit_server_settings(_full_edit(edit_env.stored), db)

        edit_env.dns.assert_not_called()
        edit_env.write.assert_not_called()
        edit_env.publish.assert_not_called()
        db.commit.assert_not_called()
        assert result.tileserver_api_key_set is True
        assert not hasattr(result, "tileserver_api_key")

    def test_a_non_tile_change_commits_without_publishing(self, edit_env):
        db = MagicMock()

        server_settings_service.edit_server_settings(_full_edit(edit_env.stored, currency="dollar"), db)

        edit_env.dns.assert_not_called()
        edit_env.publish.assert_not_called()
        db.commit.assert_called_once()

    def test_a_tile_change_publishes_only_the_changed_map_fields(self, edit_env):
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, map_background_color="#000000"), MagicMock()
        )

        assert edit_env.publish.call_args.args[0] == {"map_background_color"}
        edit_env.dns.assert_not_called()

    def test_an_unchanged_api_key_keeps_its_stored_token(self, edit_env):
        server_settings_service.edit_server_settings(_full_edit(edit_env.stored, currency="dollar"), MagicMock())

        written = edit_env.write.call_args.args[0]
        assert written.tileserver_api_key == "enc-old"

    def test_a_changed_api_key_is_encrypted_and_never_returned(self, edit_env):
        result = server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_api_key="plain-new"), MagicMock()
        )

        assert edit_env.write.call_args.args[0].tileserver_api_key == "enc-new"
        assert result.tileserver_api_key_set is True
        assert "plain-new" not in result.model_dump_json()
        assert edit_env.publish.call_args.args[0] == {"tileserver_api_key"}

    def test_clearing_the_api_key_stores_none(self, edit_env):
        result = server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_api_key=None), MagicMock()
        )

        assert edit_env.write.call_args.args[0].tileserver_api_key is None
        assert result.tileserver_api_key_set is False

    def test_an_undecryptable_stored_key_can_be_replaced(self, edit_env):
        """After the encryption key changes, re-entering the key must still work."""
        with patch.object(
            server_settings_service.core_cryptography,
            "decrypt_token_fernet",
            side_effect=core_exceptions.UndecryptableError(),
        ):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_api_key="plain-new"), MagicMock()
            )

        assert edit_env.write.call_args.args[0].tileserver_api_key == "enc-new"

    def test_the_row_is_locked_for_the_edit(self, edit_env):
        db = MagicMock()
        with patch.object(
            server_settings_service.server_settings_crud, "get_server_settings", return_value=edit_env.stored
        ) as read:
            server_settings_service.edit_server_settings(_full_edit(edit_env.stored, currency="dollar"), db)

        assert [call.kwargs for call in read.call_args_list] == [{"for_update": False}, {"for_update": True}]

    def test_the_dns_check_runs_before_the_row_is_locked(self, edit_env):
        """A slow resolver must not hold the settings lock."""
        order = []
        edit_env.dns.side_effect = lambda *a, **k: order.append("dns")

        def read(db, for_update=False):
            order.append("lock" if for_update else "read")
            return edit_env.stored

        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", side_effect=read):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_url="https://other.example.com/{z}/{x}/{y}.png"), MagicMock()
            )

        assert order == ["read", "dns", "lock"]

    def test_a_stale_if_match_is_refused_and_writes_nothing(self, edit_env):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, currency="dollar"), MagicMock(), if_match='"99"'
            )

        edit_env.write.assert_not_called()

    def test_the_current_if_match_is_accepted(self, edit_env):
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, currency="dollar"), MagicMock(), if_match='"1"'
        )

        edit_env.write.assert_called_once()


class TestGeocodingSettingsOnWrite:
    @pytest.fixture
    def geo_env(self, edit_env):
        with (
            patch.object(server_settings_service, "server_settings_env_managed", return_value={}) as managed,
            patch.object(
                server_settings_service.core_network, "url_rejection_reason_bounded", return_value=None
            ) as dns,
        ):
            edit_env.managed = managed
            edit_env.geo_dns = dns
            yield edit_env

    def test_a_save_that_leaves_geocoding_alone_does_no_lookup(self, geo_env):
        geo_env.geo_dns.reset_mock()

        server_settings_service.edit_server_settings(_full_edit(geo_env.stored, currency="dollar"), MagicMock())

        geo_env.geo_dns.assert_not_called()

    def test_the_default_host_is_checked_when_none_is_set(self, geo_env):
        server_settings_service.edit_server_settings(
            _full_edit(geo_env.stored, geocoding_service="photon"), MagicMock()
        )

        assert geo_env.geo_dns.call_args.args[0] == "https://photon.komoot.io/reverse"

    def test_a_custom_host_and_scheme_are_checked(self, geo_env):
        server_settings_service.edit_server_settings(
            _full_edit(geo_env.stored, geocoding_host="nominatim.lan:8080", geocoding_use_https=False), MagicMock()
        )

        assert geo_env.geo_dns.call_args.args[0] == "http://nominatim.lan:8080/reverse"

    def test_a_refused_host_is_a_400_and_writes_nothing(self, geo_env):
        geo_env.geo_dns.return_value = "URL resolves to a private address"

        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            server_settings_service.edit_server_settings(
                _full_edit(geo_env.stored, geocoding_host="10.0.0.5"), MagicMock()
            )

        assert "SSRF_ALLOWED_HOSTS" in exc_info.value.detail
        geo_env.write.assert_not_called()

    def test_geocode_without_a_key_is_refused(self, geo_env):
        body = _full_edit(geo_env.stored, geocoding_service="geocode")
        body = body.model_copy(update={"geocoding_api_key": None})

        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            server_settings_service.edit_server_settings(body, MagicMock())

        assert "API key" in exc_info.value.detail
        geo_env.geo_dns.assert_not_called()

    def test_geocode_with_a_new_key_is_accepted_and_the_key_encrypted(self, geo_env):
        result = server_settings_service.edit_server_settings(
            _full_edit(geo_env.stored, geocoding_service="geocode", geocoding_api_key="plain-new"), MagicMock()
        )

        assert geo_env.write.call_args.args[0].geocoding_api_key == "enc-new"
        assert result.geocoding_api_key_set is True
        assert "plain-new" not in result.model_dump_json()

    def test_geocode_with_a_stored_key_and_none_sent_is_accepted(self, geo_env):
        geo_env.stored = geo_env.stored.model_copy(update={"geocoding_api_key": "enc-old"})
        with patch.object(
            server_settings_service.server_settings_crud, "get_server_settings", return_value=geo_env.stored
        ):
            server_settings_service.edit_server_settings(
                _full_edit(geo_env.stored, geocoding_service="geocode"), MagicMock()
            )

        geo_env.write.assert_called_once()

    def test_the_two_keys_are_independent(self, geo_env):
        server_settings_service.edit_server_settings(
            _full_edit(geo_env.stored, geocoding_api_key="plain-new"), MagicMock()
        )

        written = geo_env.write.call_args.args[0]
        assert written.geocoding_api_key == "enc-new"
        assert written.tileserver_api_key == "enc-old"


class TestServerSettingsEnvManaged:
    def test_nothing_is_managed_without_a_geocoding_variable(self):
        with patch.object(server_settings_service, "_env_var_is_set", return_value=False):
            assert server_settings_service.server_settings_env_managed() == {}

    def test_one_variable_manages_every_geocoding_field(self):
        with (
            patch.object(
                server_settings_service, "_env_var_is_set", side_effect=lambda n: n == "REVERSE_GEO_RATE_LIMIT"
            ),
            patch.object(server_settings_service.core_config, "settings", MagicMock(REVERSE_GEO_PROVIDER="nominatim")),
        ):
            managed = server_settings_service.server_settings_env_managed()

        assert managed == {
            "geocoding_service": "REVERSE_GEO_PROVIDER",
            "geocoding_host": "NOMINATIM_API_HOST",
            "geocoding_use_https": "NOMINATIM_API_USE_HTTPS",
            "geocoding_rate_limit": "REVERSE_GEO_RATE_LIMIT",
            "geocoding_api_key": "GEOCODES_MAPS_API",
        }

    def test_photon_names_its_own_host_variables(self):
        with (
            patch.object(server_settings_service, "_env_var_is_set", return_value=True),
            patch.object(server_settings_service.core_config, "settings", MagicMock(REVERSE_GEO_PROVIDER="photon")),
        ):
            managed = server_settings_service.server_settings_env_managed()

        assert managed["geocoding_host"] == "PHOTON_API_HOST"
        assert managed["geocoding_use_https"] == "PHOTON_API_USE_HTTPS"

    def test_a_change_to_an_env_managed_field_is_refused(self, edit_env):
        with (
            patch.object(
                server_settings_service,
                "server_settings_env_managed",
                return_value={"geocoding_rate_limit": "REVERSE_GEO_RATE_LIMIT"},
            ),
            pytest.raises(core_exceptions.ConflictError) as exc_info,
        ):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, geocoding_rate_limit=2.0), MagicMock()
            )

        assert "REVERSE_GEO_RATE_LIMIT" in exc_info.value.detail
        edit_env.write.assert_not_called()

    def test_a_change_to_another_field_succeeds_while_geocoding_is_managed(self, edit_env):
        with patch.object(
            server_settings_service,
            "server_settings_env_managed",
            return_value={"geocoding_rate_limit": "REVERSE_GEO_RATE_LIMIT"},
        ):
            result = server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, currency="dollar"), MagicMock()
            )

        assert result.currency == "dollar"
        assert result.env_managed == {"geocoding_rate_limit": "REVERSE_GEO_RATE_LIMIT"}


class TestGetGeocodingConfig:
    def test_decrypts_the_key(self, edit_env):
        stored = edit_env.stored.model_copy(update={"geocoding_api_key": "enc-old", "geocoding_host": "h.example.com"})
        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=stored):
            config = server_settings_service.get_geocoding_config(MagicMock())

        assert config.api_key == "plain-old"
        assert config.host == "h.example.com"
        assert config.service == core_geocoding.GeocodingService.NOMINATIM

    def test_a_missing_row_means_geocoding_is_unavailable(self):
        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=None):
            assert server_settings_service.get_geocoding_config(MagicMock()) is None


def _geo_env_settings(**overrides):
    values = dict(
        REVERSE_GEO_PROVIDER="nominatim",
        NOMINATIM_API_HOST="nominatim.openstreetmap.org",
        NOMINATIM_API_USE_HTTPS=True,
        PHOTON_API_HOST="photon.komoot.io",
        PHOTON_API_USE_HTTPS=True,
        GEOCODES_MAPS_API="changeme",
        REVERSE_GEO_RATE_LIMIT=1.0,
    )
    values.update(overrides)
    return MagicMock(**values)


@pytest.fixture
def import_geo(edit_env):
    """Pretend the given geocoding variables are set; yield the knobs."""
    state = MagicMock(set_vars={"REVERSE_GEO_PROVIDER"}, settings=_geo_env_settings(), stored=edit_env.stored)
    with (
        patch.object(server_settings_service, "_env_var_is_set", side_effect=lambda n: n in state.set_vars),
        patch.object(server_settings_service.core_config, "settings", state.settings),
        patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=state.stored),
    ):
        state.write = edit_env.write
        yield state


class TestImportGeocodingEnv:
    def test_nothing_happens_without_a_geocoding_variable(self, import_geo):
        import_geo.set_vars = set()

        assert server_settings_service._import_geocoding_env(MagicMock()) == []
        import_geo.write.assert_not_called()

    def test_values_equal_to_the_stored_ones_write_nothing(self, import_geo):
        names = server_settings_service._import_geocoding_env(MagicMock())

        assert names == ["REVERSE_GEO_PROVIDER"]
        import_geo.write.assert_not_called()

    def test_only_the_differing_fields_are_written(self, import_geo):
        import_geo.set_vars = {"REVERSE_GEO_PROVIDER", "REVERSE_GEO_RATE_LIMIT"}
        import_geo.settings.REVERSE_GEO_RATE_LIMIT = 2.5

        server_settings_service._import_geocoding_env(MagicMock())

        assert import_geo.write.call_args.args[0].model_dump(exclude_unset=True) == {"geocoding_rate_limit": 2.5}

    def test_photon_reads_its_own_host_only_when_set(self, import_geo):
        import_geo.settings.REVERSE_GEO_PROVIDER = "photon"
        import_geo.set_vars = {"REVERSE_GEO_PROVIDER", "PHOTON_API_HOST"}
        import_geo.settings.PHOTON_API_HOST = "photon.example.com"
        import_geo.settings.NOMINATIM_API_HOST = "ignored.example.com"

        server_settings_service._import_geocoding_env(MagicMock())

        written = import_geo.write.call_args.args[0].model_dump(exclude_unset=True)
        assert written == {"geocoding_service": "photon", "geocoding_host": "photon.example.com"}

    def test_an_unset_host_variable_means_the_default_host(self, import_geo):
        import_geo.stored = import_geo.stored.model_copy(update={"geocoding_host": "old.example.com"})
        with patch.object(
            server_settings_service.server_settings_crud, "get_server_settings", return_value=import_geo.stored
        ):
            server_settings_service._import_geocoding_env(MagicMock())

        assert import_geo.write.call_args.args[0].model_dump(exclude_unset=True) == {"geocoding_host": None}

    def test_the_changeme_placeholder_is_no_key(self, import_geo):
        import_geo.set_vars = {"GEOCODES_MAPS_API"}
        import_geo.settings.GEOCODES_MAPS_API = "changeme"

        server_settings_service._import_geocoding_env(MagicMock())

        import_geo.write.assert_not_called()

    def test_a_real_key_is_encrypted_and_written(self, import_geo):
        import_geo.set_vars = {"REVERSE_GEO_PROVIDER", "GEOCODES_MAPS_API"}
        import_geo.settings.REVERSE_GEO_PROVIDER = "geocode"
        import_geo.settings.GEOCODES_MAPS_API = "a-real-key"

        server_settings_service._import_geocoding_env(MagicMock())

        written = import_geo.write.call_args.args[0].model_dump(exclude_unset=True)
        assert written["geocoding_api_key"] == "enc-new"
        assert written["geocoding_service"] == "geocode"
        assert "a-real-key" not in str(written)

    def test_an_unknown_provider_leaves_the_stored_settings_and_does_not_raise(self, import_geo):
        import_geo.settings.REVERSE_GEO_PROVIDER = "bing"

        names = server_settings_service._import_geocoding_env(MagicMock())

        assert names == ["REVERSE_GEO_PROVIDER"]
        import_geo.write.assert_not_called()


class TestImportDeprecatedNamesBothBlocks:
    def test_the_warning_names_mail_and_geocoding_variables(self):
        with (
            patch.object(server_settings_service, "_import_mail_env", return_value=["SMTP_HOST"]),
            patch.object(server_settings_service, "_import_geocoding_env", return_value=["REVERSE_GEO_PROVIDER"]),
            patch.object(server_settings_service.logger, "warning") as warn,
        ):
            server_settings_service.import_deprecated_env_settings(MagicMock())

        warn.assert_called_once()
        assert "SMTP_HOST, REVERSE_GEO_PROVIDER" in warn.call_args.args[0]


class TestGetSessionPolicy:
    def test_timeouts_enabled(self, edit_env):
        stored = edit_env.stored.model_copy(
            update={
                "session_idle_timeout_enabled": True,
                "session_idle_timeout_hours": 2,
                "session_absolute_timeout_hours": 48,
                "access_token_expire_minutes": 30,
                "refresh_token_expire_days": 14,
            }
        )
        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=stored):
            policy = server_settings_service.get_session_policy(MagicMock())

        assert policy.access_token_ttl == timedelta(minutes=30)
        assert policy.refresh_token_ttl == timedelta(days=14)
        assert policy.idle_timeout == timedelta(hours=2)
        assert policy.absolute_timeout == timedelta(hours=48)

    def test_disabled_timeouts_are_none_but_lifetimes_stay(self, edit_env):
        policy = server_settings_service.get_session_policy(MagicMock())

        assert policy.idle_timeout is None
        assert policy.absolute_timeout is None
        assert policy.access_token_ttl == timedelta(minutes=15)
        assert policy.refresh_token_ttl == timedelta(days=7)

    def test_a_missing_row_raises(self):
        with (
            patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=None),
            pytest.raises(core_exceptions.ServiceUnavailableError),
        ):
            server_settings_service.get_session_policy(MagicMock())


class TestSessionEnvManaged:
    def test_each_variable_manages_only_its_own_field(self):
        with patch.object(
            server_settings_service, "_env_var_is_set", side_effect=lambda n: n == "REFRESH_TOKEN_EXPIRE_DAYS"
        ):
            assert server_settings_service.server_settings_env_managed() == {
                "refresh_token_expire_days": "REFRESH_TOKEN_EXPIRE_DAYS"
            }

    def test_a_change_to_a_managed_session_field_is_refused(self, edit_env):
        with (
            patch.object(
                server_settings_service,
                "server_settings_env_managed",
                return_value={"access_token_expire_minutes": "ACCESS_TOKEN_EXPIRE_MINUTES"},
            ),
            pytest.raises(core_exceptions.ConflictError) as exc_info,
        ):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, access_token_expire_minutes=30), MagicMock()
            )

        assert "ACCESS_TOKEN_EXPIRE_MINUTES" in exc_info.value.detail
        edit_env.write.assert_not_called()


def _session_env_settings(**overrides):
    values = dict(
        ACCESS_TOKEN_EXPIRE_MINUTES=15,
        REFRESH_TOKEN_EXPIRE_DAYS=7,
        SESSION_IDLE_TIMEOUT_ENABLED=False,
        SESSION_IDLE_TIMEOUT_HOURS=1,
        SESSION_ABSOLUTE_TIMEOUT_HOURS=24,
    )
    values.update(overrides)
    return MagicMock(**values)


@pytest.fixture
def import_session(edit_env):
    state = MagicMock(set_vars=set(), settings=_session_env_settings(), stored=edit_env.stored, write=edit_env.write)
    with (
        patch.object(server_settings_service, "_env_var_is_set", side_effect=lambda n: n in state.set_vars),
        patch.object(server_settings_service.core_config, "settings", state.settings),
        patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=state.stored),
    ):
        yield state


class TestImportSessionEnv:
    def test_nothing_happens_without_a_session_variable(self, import_session):
        assert server_settings_service._import_session_env(MagicMock()) == []
        import_session.write.assert_not_called()

    def test_values_equal_to_the_stored_ones_write_nothing(self, import_session):
        import_session.set_vars = {"ACCESS_TOKEN_EXPIRE_MINUTES"}

        assert server_settings_service._import_session_env(MagicMock()) == ["ACCESS_TOKEN_EXPIRE_MINUTES"]
        import_session.write.assert_not_called()

    def test_only_the_set_variables_are_imported_and_only_when_different(self, import_session):
        import_session.set_vars = {"ACCESS_TOKEN_EXPIRE_MINUTES", "REFRESH_TOKEN_EXPIRE_DAYS"}
        import_session.settings.ACCESS_TOKEN_EXPIRE_MINUTES = 60
        # Not set in the environment, so it must not be touched even though it differs from the stored value.
        import_session.settings.SESSION_IDLE_TIMEOUT_HOURS = 5

        server_settings_service._import_session_env(MagicMock())

        written = import_session.write.call_args.args[0].model_dump(exclude_unset=True)
        assert written == {"access_token_expire_minutes": 60}

    def test_the_enabled_flag_is_imported(self, import_session):
        import_session.set_vars = {"SESSION_IDLE_TIMEOUT_ENABLED"}
        import_session.settings.SESSION_IDLE_TIMEOUT_ENABLED = True

        server_settings_service._import_session_env(MagicMock())

        assert import_session.write.call_args.args[0].model_dump(exclude_unset=True) == {
            "session_idle_timeout_enabled": True
        }

    def test_an_absolute_timeout_below_the_idle_timeout_stops_the_start(self, import_session):
        import_session.set_vars = {"SESSION_IDLE_TIMEOUT_HOURS", "SESSION_ABSOLUTE_TIMEOUT_HOURS"}
        import_session.settings.SESSION_IDLE_TIMEOUT_HOURS = 48
        import_session.settings.SESSION_ABSOLUTE_TIMEOUT_HOURS = 24

        with pytest.raises(ValueError, match="SESSION_ABSOLUTE_TIMEOUT_HOURS"):
            server_settings_service._import_session_env(MagicMock())

        import_session.write.assert_not_called()

    def test_a_lone_idle_timeout_is_checked_against_the_stored_absolute_one(self, import_session):
        import_session.set_vars = {"SESSION_IDLE_TIMEOUT_HOURS"}
        import_session.settings.SESSION_IDLE_TIMEOUT_HOURS = 100

        with pytest.raises(ValueError):
            server_settings_service._import_session_env(MagicMock())


class TestRetention:
    def test_the_stored_value_is_returned_by_the_integration_read(self, edit_env):
        from modules.server_settings import integration_service

        stored = edit_env.stored.model_copy(update={"read_notification_retention_days": 30})
        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=stored):
            assert integration_service.get_read_notification_retention_days(MagicMock()) == 30

    def test_the_variable_manages_only_its_own_field(self):
        with patch.object(
            server_settings_service, "_env_var_is_set", side_effect=lambda n: n == "READ_NOTIFICATION_RETENTION_DAYS"
        ):
            assert server_settings_service.server_settings_env_managed() == {
                "read_notification_retention_days": "READ_NOTIFICATION_RETENTION_DAYS"
            }

    def test_a_change_to_the_managed_field_is_refused(self, edit_env):
        with (
            patch.object(
                server_settings_service,
                "server_settings_env_managed",
                return_value={"read_notification_retention_days": "READ_NOTIFICATION_RETENTION_DAYS"},
            ),
            pytest.raises(core_exceptions.ConflictError) as exc_info,
        ):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, read_notification_retention_days=30), MagicMock()
            )

        assert "READ_NOTIFICATION_RETENTION_DAYS" in exc_info.value.detail
        edit_env.write.assert_not_called()

    @pytest.fixture
    def import_env(self, edit_env):
        state = MagicMock(is_set=True, settings=MagicMock(READ_NOTIFICATION_RETENTION_DAYS=90), write=edit_env.write)
        with (
            patch.object(server_settings_service, "_env_var_is_set", side_effect=lambda n: state.is_set),
            patch.object(server_settings_service.core_config, "settings", state.settings),
            patch.object(
                server_settings_service.server_settings_crud, "get_server_settings", return_value=edit_env.stored
            ),
        ):
            yield state

    def test_nothing_happens_without_the_variable(self, import_env):
        import_env.is_set = False

        assert server_settings_service._import_retention_env(MagicMock()) == []
        import_env.write.assert_not_called()

    def test_an_equal_value_writes_nothing(self, import_env):
        assert server_settings_service._import_retention_env(MagicMock()) == ["READ_NOTIFICATION_RETENTION_DAYS"]
        import_env.write.assert_not_called()

    def test_a_different_value_is_written(self, import_env):
        import_env.settings.READ_NOTIFICATION_RETENTION_DAYS = 7

        server_settings_service._import_retention_env(MagicMock())

        assert import_env.write.call_args.args[0].model_dump(exclude_unset=True) == {
            "read_notification_retention_days": 7
        }

    def test_zero_is_imported(self, import_env):
        import_env.settings.READ_NOTIFICATION_RETENTION_DAYS = 0

        server_settings_service._import_retention_env(MagicMock())

        assert import_env.write.call_args.args[0].read_notification_retention_days == 0


class TestLoginPhoto:
    def test_upload_writes_the_blob_before_committing_the_flag(self):
        calls = []
        storage = MagicMock()
        storage.save.side_effect = lambda *a: calls.append("save")
        db = MagicMock()
        db.commit.side_effect = lambda: calls.append("commit")
        file = MagicMock(content_type="text/plain")

        with (
            patch.object(server_settings_service.core_file_uploads, "read_validated_upload_sync", return_value=_PNG),
            patch.object(server_settings_service.server_settings_crud, "set_login_photo"),
        ):
            server_settings_service.upload_login_photo(file, storage, db)

        assert calls == ["save", "commit"]
        # The type is detected from the bytes, not taken from the client's claim.
        storage.save.assert_called_once_with("server_images", "login.png", _PNG, "image/png")

    def test_upload_rejects_a_photo_over_the_login_cap(self):
        big = _PNG + b"0" * server_settings_constants.LOGIN_PHOTO_MAX_BYTES
        storage = MagicMock()

        with (
            patch.object(server_settings_service.core_file_uploads, "read_validated_upload_sync", return_value=big),
            pytest.raises(core_exceptions.PayloadTooLargeError),
        ):
            server_settings_service.upload_login_photo(MagicMock(), storage, MagicMock())

        storage.save.assert_not_called()

    def test_upload_rejects_an_unrecognised_format(self):
        storage = MagicMock()

        with (
            patch.object(
                server_settings_service.core_file_uploads, "read_validated_upload_sync", return_value=b"not an image"
            ),
            pytest.raises(core_exceptions.UnsupportedMediaTypeError),
        ):
            server_settings_service.upload_login_photo(MagicMock(), storage, MagicMock())

        storage.save.assert_not_called()

    def test_delete_clears_the_flag_before_removing_the_blob(self):
        calls = []
        storage = MagicMock()
        storage.delete.side_effect = lambda *a: calls.append("delete")
        db = MagicMock()
        db.commit.side_effect = lambda: calls.append("commit")

        with patch.object(server_settings_service.server_settings_crud, "set_login_photo"):
            server_settings_service.delete_login_photo(storage, db)

        assert calls == ["commit", "delete"]
        storage.delete.assert_called_once_with("server_images", "login.png")

    def test_delete_survives_a_storage_failure(self):
        storage = MagicMock()
        storage.delete.side_effect = RuntimeError("storage down")
        db = MagicMock()

        with patch.object(server_settings_service.server_settings_crud, "set_login_photo"):
            server_settings_service.delete_login_photo(storage, db)

        db.commit.assert_called_once()

    def test_version_is_none_when_no_photo_is_set(self):
        with patch.object(
            server_settings_service, "get_server_settings", return_value=MagicMock(login_photo_set=False, version=5)
        ):
            assert server_settings_service.get_login_photo_version(MagicMock()) is None

    def test_version_is_the_settings_version_when_a_photo_is_set(self):
        with patch.object(
            server_settings_service, "get_server_settings", return_value=MagicMock(login_photo_set=True, version=5)
        ):
            assert server_settings_service.get_login_photo_version(MagicMock()) == 5

    def test_read_returns_none_when_missing(self):
        storage = MagicMock()
        storage.get.return_value = None

        assert server_settings_service.read_login_photo(storage) is None

    @pytest.mark.parametrize(
        "data,media_type",
        [(_PNG, "image/png"), (b"\xff\xd8\xff\xe0", "image/jpeg"), (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp")],
    )
    def test_read_returns_the_detected_type(self, data, media_type):
        storage = MagicMock()
        storage.get.return_value = data

        assert server_settings_service.read_login_photo(storage) == (data, media_type)


def _mail_row(**overrides) -> server_settings_schema.MailSettingsRead:
    """Mail settings as the crud layer returns them (the password still encrypted)."""
    values = dict(
        id=1,
        host="mail.example.com",
        port=587,
        security="starttls",
        username="me@example.com",
        from_address=None,
        password="enc-old",
    )
    values.update(overrides)
    return server_settings_schema.MailSettingsRead(**values)


def _mail_edit(stored: server_settings_schema.MailSettingsRead, **overrides):
    """The whole mail record, the way the frontend sends it (password omitted unless given)."""
    body = stored.model_dump(exclude={"id", "password", "version"})
    body.update(overrides)
    return server_settings_schema.MailSettingsEdit(**body)


@pytest.fixture
def mail_env():
    """Patch the collaborators of the mail service functions and expose them."""
    stored = _mail_row()
    with (
        patch.object(server_settings_service.server_settings_crud, "get_mail_settings", return_value=stored) as read,
        patch.object(
            server_settings_service.server_settings_crud,
            "edit_mail_settings",
            side_effect=lambda attrs, db: stored.model_copy(update=attrs.model_dump(exclude_unset=True)),
        ) as write,
        patch.object(server_settings_service.core_mail, "mail_problems", return_value=[]) as problems,
        patch.object(server_settings_service, "mail_env_managed", return_value={}) as managed,
        patch.object(
            server_settings_service.core_cryptography,
            "decrypt_token_fernet",
            side_effect=lambda token: {"enc-old": "plain-old", "enc-new": "plain-new"}[token],
        ),
        patch.object(server_settings_service.core_cryptography, "encrypt_token_fernet", return_value="enc-new"),
    ):
        yield MagicMock(stored=stored, read=read, write=write, problems=problems, managed=managed)


class TestEditMailSettings:
    def test_resending_the_unchanged_record_does_nothing(self, mail_env):
        db = MagicMock()

        result = server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored), db)

        mail_env.write.assert_not_called()
        db.commit.assert_not_called()
        assert db.rollback.call_count == 2
        assert result.host == "mail.example.com"

    def test_the_row_is_locked_for_the_edit(self, mail_env):
        server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, port=465), MagicMock())

        assert mail_env.read.call_args.kwargs == {"for_update": True}

    def test_a_stale_if_match_is_refused_and_writes_nothing(self, mail_env):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            server_settings_service.edit_mail_settings(
                _mail_edit(mail_env.stored, port=465), MagicMock(), if_match='"9"'
            )

        mail_env.write.assert_not_called()

    def test_an_omitted_password_keeps_the_stored_token(self, mail_env):
        db = MagicMock()

        server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, port=465), db)

        assert "password" not in mail_env.write.call_args.args[0].model_fields_set
        db.commit.assert_called_once()

    def test_an_unchanged_password_keeps_its_stored_token(self, mail_env):
        body = _mail_edit(mail_env.stored, port=465, password="plain-old")

        server_settings_service.edit_mail_settings(body, MagicMock())

        assert mail_env.write.call_args.args[0].password == "enc-old"

    @pytest.mark.parametrize("cleared", [None, ""])
    def test_clearing_the_password_stores_none(self, mail_env, cleared):
        result = server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, password=cleared), MagicMock())

        assert mail_env.write.call_args.args[0].password is None
        assert result.password_set is False

    def test_a_changed_password_is_encrypted_and_never_returned(self, mail_env):
        result = server_settings_service.edit_mail_settings(
            _mail_edit(mail_env.stored, password="plain-new"), MagicMock()
        )

        assert mail_env.write.call_args.args[0].password == "enc-new"
        assert result.password_set is True
        assert "plain-new" not in result.model_dump_json()
        assert "enc-new" not in result.model_dump_json()

    def test_an_invalid_configuration_is_a_400_and_writes_nothing(self, mail_env):
        mail_env.problems.return_value = [
            "Port must be between 1 and 65535",
            "Username and password must be set together",
        ]

        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, port=465), MagicMock())

        assert "Port must be between" in exc_info.value.detail
        assert "; " in exc_info.value.detail
        mail_env.write.assert_not_called()

    def test_disabling_mail_skips_validation(self, mail_env):
        mail_env.problems.return_value = ["never shown"]

        result = server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, host=None), MagicMock())

        mail_env.problems.assert_not_called()
        assert result.host is None

    def test_the_password_is_checked_in_plain_text(self, mail_env):
        server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, port=465), MagicMock())

        config = mail_env.problems.call_args.args[0]
        assert config.password == "plain-old"
        assert config.from_address == "me@example.com"

    def test_a_change_to_an_env_managed_field_is_refused(self, mail_env):
        mail_env.managed.return_value = {"host": "SMTP_HOST", "port": "SMTP_PORT"}

        with pytest.raises(core_exceptions.ConflictError) as exc_info:
            server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, port=465), MagicMock())

        assert "port is set by the SMTP_PORT environment variable" in exc_info.value.detail
        mail_env.write.assert_not_called()

    def test_a_change_to_a_field_that_is_not_env_managed_succeeds(self, mail_env):
        mail_env.managed.return_value = {"host": "SMTP_HOST"}

        result = server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, port=465), MagicMock())

        assert result.port == 465

    def test_resending_an_env_managed_value_unchanged_is_allowed(self, mail_env):
        mail_env.managed.return_value = {"host": "SMTP_HOST", "port": "SMTP_PORT"}

        server_settings_service.edit_mail_settings(
            _mail_edit(mail_env.stored, username="other@example.com"), MagicMock()
        )

        assert mail_env.write.call_args.args[0].username == "other@example.com"


class TestMailEnvManaged:
    def test_nothing_is_managed_without_smtp_host(self):
        with patch.object(server_settings_service, "_env_var_is_set", return_value=False):
            assert server_settings_service.mail_env_managed() == {}

    def test_every_mail_field_is_managed_when_smtp_host_is_set(self):
        with patch.object(server_settings_service, "_env_var_is_set", side_effect=lambda name: name == "SMTP_HOST"):
            managed = server_settings_service.mail_env_managed()

        assert managed == server_settings_constants.MAIL_ENV_VARS
        assert managed["password"] == "SMTP_PASSWORD"


class TestEnvVarIsSet:
    def test_a_default_value_does_not_count(self):
        with patch.object(server_settings_service.core_config, "settings", MagicMock(model_fields_set=set())):
            assert server_settings_service._env_var_is_set("SMTP_PORT") is False

    def test_an_explicit_value_counts(self):
        with patch.object(server_settings_service.core_config, "settings", MagicMock(model_fields_set={"SMTP_PORT"})):
            assert server_settings_service._env_var_is_set("SMTP_PORT") is True

    @pytest.mark.parametrize("variable", ["SMTP_PASSWORD", "SMTP_PASSWORD_FILE"])
    def test_a_secret_counts_through_its_file_variant(self, variable):
        with patch.dict("os.environ", {variable: "x"}, clear=True):
            assert server_settings_service._env_var_is_set("SMTP_PASSWORD") is True

    def test_an_unset_secret_does_not_count(self):
        with patch.dict("os.environ", {}, clear=True):
            assert server_settings_service._env_var_is_set("SMTP_PASSWORD") is False


class TestMailConfig:
    def test_decrypts_the_password_and_falls_back_to_the_username_sender(self, mail_env):
        config = server_settings_service.get_mail_config(MagicMock())

        assert config.password == "plain-old"
        assert config.from_address == "me@example.com"
        assert config.security == core_mail.MailSecurity.STARTTLS

    def test_an_explicit_sender_wins(self, mail_env):
        mail_env.read.return_value = _mail_row(from_address="noreply@example.com")

        assert server_settings_service.get_mail_config(MagicMock()).from_address == "noreply@example.com"

    def test_no_host_means_mail_is_disabled(self, mail_env):
        mail_env.read.return_value = _mail_row(host=None)

        assert server_settings_service.get_mail_config(MagicMock()) is None

    def test_a_missing_row_means_mail_is_disabled(self, mail_env):
        mail_env.read.return_value = None

        assert server_settings_service.get_mail_config(MagicMock()) is None


class TestEmailStatus:
    """Test suite for get_email_status."""

    def test_configured(self, mail_env):
        result = server_settings_service.get_email_status(MagicMock())

        assert result.configured is True
        assert result.problems == []

    def test_unset_host_reports_missing_host(self, mail_env):
        mail_env.read.return_value = _mail_row(host=None)

        result = server_settings_service.get_email_status(MagicMock())

        assert result.configured is False
        assert result.problems == ["Host is not set"]

    def test_invalid_settings_report_problems(self, mail_env):
        mail_env.problems.return_value = ["Username and password must be set together"]

        result = server_settings_service.get_email_status(MagicMock())

        assert result.configured is False
        assert result.problems == ["Username and password must be set together"]


class TestSendTestEmail:
    """Test suite for send_test_email."""

    @staticmethod
    def _admin():
        return MagicMock(email="admin@example.com", preferred_language="en", **{"name": "Admin"})

    def test_not_configured_raises_503_with_reasons(self, mail_env):
        mail_env.read.return_value = _mail_row(host=None)
        mail = MagicMock()

        with pytest.raises(core_exceptions.ServiceUnavailableError) as exc_info:
            server_settings_service.send_test_email(self._admin(), mail, MagicMock())

        assert "Host is not set" in exc_info.value.detail
        mail.send.assert_not_called()

    @patch("modules.server_settings.service.core_config.settings")
    def test_sends_to_the_admin_only(self, mock_settings, mail_env):
        mock_settings.ENDURAIN_HOST = "https://endurain.example.com"
        mail = MagicMock()

        server_settings_service.send_test_email(self._admin(), mail, MagicMock())

        message = mail.send.call_args.args[0]
        assert message.to == ["admin@example.com"]
        assert "mail.example.com:587" in message.text
        assert message.html and message.text

    @patch("modules.server_settings.service.core_config.settings")
    def test_mail_error_becomes_502_with_status_code(self, mock_settings, mail_env):
        mock_settings.ENDURAIN_HOST = "https://endurain.example.com"
        mail = MagicMock()
        mail.send.side_effect = platform_providers.MailError("SMTP authentication failed (status 535)", status=535)

        with pytest.raises(core_exceptions.UpstreamError) as exc_info:
            server_settings_service.send_test_email(self._admin(), mail, MagicMock())

        assert "status 535" in exc_info.value.detail


def _env_settings(**overrides):
    values = dict(
        SMTP_HOST="mail.example.com",
        SMTP_PORT=587,
        SMTP_USERNAME="me@example.com",
        SMTP_FROM=None,
        SMTP_SECURE=True,
        SMTP_SECURE_TYPE="starttls",
    )
    values.update(overrides)
    return MagicMock(**values)


@pytest.fixture
def import_env(mail_env):
    """Pretend ``SMTP_*`` variables are set, with a password, on top of the mail fixture."""
    with (
        patch.object(server_settings_service, "_env_var_is_set", return_value=True) as is_set,
        patch.object(server_settings_service.core_config, "settings", _env_settings()) as settings,
        patch.object(server_settings_service.core_config, "read_secret", return_value="plain-old") as secret,
    ):
        yield MagicMock(mail=mail_env, is_set=is_set, settings=settings, secret=secret)


class TestImportMailEnv:
    def test_nothing_happens_without_smtp_host(self, mail_env):
        with patch.object(server_settings_service, "_env_var_is_set", return_value=False):
            names = server_settings_service._import_mail_env(MagicMock())

        assert names == []
        mail_env.read.assert_not_called()
        mail_env.write.assert_not_called()

    def test_values_equal_to_the_stored_ones_write_nothing(self, import_env):
        names = server_settings_service._import_mail_env(MagicMock())

        import_env.mail.write.assert_not_called()
        assert "SMTP_HOST" in names and "SMTP_PASSWORD" in names

    def test_only_the_differing_fields_are_written(self, import_env):
        server_settings_service.core_config.settings.SMTP_PORT = 465
        server_settings_service.core_config.settings.SMTP_SECURE_TYPE = "ssl"

        server_settings_service._import_mail_env(MagicMock())

        written = import_env.mail.write.call_args.args[0].model_dump(exclude_unset=True)
        assert written == {"port": 465, "security": "ssl"}

    def test_a_different_password_is_encrypted_and_written(self, import_env):
        import_env.secret.return_value = "plain-new"

        server_settings_service._import_mail_env(MagicMock())

        assert import_env.mail.write.call_args.args[0].model_dump(exclude_unset=True) == {"password": "enc-new"}

    @pytest.mark.parametrize(
        ("secure", "secure_type", "expected"),
        [(False, "starttls", "none"), (True, "ssl", "ssl"), (True, "starttls", "starttls")],
    )
    def test_the_security_mode_is_mapped(self, import_env, secure, secure_type, expected):
        server_settings_service.core_config.settings.SMTP_SECURE = secure
        server_settings_service.core_config.settings.SMTP_SECURE_TYPE = secure_type
        stored_security = "ssl" if expected == "starttls" else "starttls"
        import_env.mail.read.return_value = import_env.mail.stored.model_copy(update={"security": stored_security})

        server_settings_service._import_mail_env(MagicMock())

        assert import_env.mail.write.call_args.args[0].model_dump(exclude_unset=True)["security"] == expected

    def test_invalid_values_leave_the_stored_settings_and_do_not_raise(self, import_env, caplog):
        import_env.mail.problems.return_value = ["Username and password must be set together"]

        names = server_settings_service._import_mail_env(MagicMock())

        import_env.mail.read.assert_not_called()
        import_env.mail.write.assert_not_called()
        assert "SMTP_HOST" in names
        assert "plain-old" not in caplog.text

    def test_the_row_is_locked(self, import_env):
        server_settings_service._import_mail_env(MagicMock())

        assert import_env.mail.read.call_args.kwargs == {"for_update": True}


class TestImportDeprecatedEnvSettings:
    def test_no_env_means_no_warning(self):
        db = MagicMock()
        with (
            patch.object(server_settings_service, "_import_mail_env", return_value=[]),
            patch.object(server_settings_service.logger, "warning") as warn,
        ):
            server_settings_service.import_deprecated_env_settings(db)

        warn.assert_not_called()

    def test_one_warning_names_the_variables_but_never_values(self):
        db = MagicMock()
        with (
            patch.object(server_settings_service, "_import_mail_env", return_value=["SMTP_HOST", "SMTP_PASSWORD"]),
            patch.object(server_settings_service.logger, "warning") as warn,
        ):
            server_settings_service.import_deprecated_env_settings(db)

        warn.assert_called_once()
        message = warn.call_args.args[0]
        assert "SMTP_HOST, SMTP_PASSWORD" in message
        assert "v0.22.0" in message
        db.commit.assert_called_once()

    def test_commits_before_warning(self):
        db = MagicMock()
        order: list[str] = []
        db.commit.side_effect = lambda: order.append("commit")
        with (
            patch.object(server_settings_service, "_import_mail_env", return_value=["SMTP_HOST"]),
            patch.object(server_settings_service.logger, "warning", side_effect=lambda *a, **k: order.append("warn")),
        ):
            server_settings_service.import_deprecated_env_settings(db)

        assert order == ["commit", "warn"]


class TestGetServerSettingsForPublic:
    """Test suite for get_server_settings_for_public."""

    @staticmethod
    def _stored_settings() -> server_settings_schema.ServerSettingsRead:
        return server_settings_schema.ServerSettingsRead(
            id=1,
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            signup_require_admin_approval=True,
            signup_require_email_verification=True,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            password_type="strict",
            tileserver_regenerate_thumbnails_on_change=False,
            password_length_regular_users=8,
            password_length_admin_users=12,
            tileserver_api_key="encrypted",
            geocoding_service="nominatim",
            geocoding_host=None,
            geocoding_use_https=True,
            geocoding_rate_limit=1.0,
            session_idle_timeout_enabled=False,
            session_idle_timeout_hours=1,
            session_absolute_timeout_hours=24,
            access_token_expire_minutes=15,
            refresh_token_expire_days=7,
            read_notification_retention_days=90,
            geocoding_api_key="encrypted-geo",
        )

    @patch("modules.server_settings.service.core_config.settings")
    @patch("modules.server_settings.service.server_settings_crud.get_server_settings")
    def test_reflects_configured_schemes_sorted(self, mock_get, mock_config, mock_db):
        """Test the redirect schemes mirror ALLOWED_REDIRECT_SCHEMES, sorted."""
        mock_get.return_value = self._stored_settings()
        mock_config.ALLOWED_REDIRECT_SCHEMES = {"gadgetbridge", "endurain"}

        result = server_settings_service.get_server_settings_for_public(mock_db)

        assert result.allowed_redirect_schemes == ["endurain", "gadgetbridge"]

    @patch("modules.server_settings.service.server_settings_crud.get_server_settings")
    def test_excludes_admin_only_fields(self, mock_get, mock_db):
        """Test sign-up policy and the tile API key never reach the public shape."""
        mock_get.return_value = self._stored_settings()

        dumped = server_settings_service.get_server_settings_for_public(mock_db).model_dump()

        assert "signup_require_admin_approval" not in dumped
        assert "tileserver_api_key" not in dumped


class TestEditMailSettingsLocking:
    """The validation that can resolve DNS runs before the settings row is locked."""

    def test_validation_runs_before_the_row_is_locked(self, mail_env):
        calls = []
        mail_env.read.side_effect = lambda db, **kwargs: (calls.append(("read", kwargs)), mail_env.stored)[1]
        with patch.object(
            server_settings_service.core_mail,
            "mail_problems",
            side_effect=lambda config: calls.append(("dns", {})) or [],
        ):
            server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, port=465), MagicMock())

        assert [name for name, _ in calls] == ["read", "dns", "read"]
        assert calls[-1][1] == {"for_update": True}

    def test_a_password_replaced_meanwhile_is_refused(self, mail_env):
        later = mail_env.stored.model_copy(update={"password": "enc-new"})
        mail_env.read.side_effect = [mail_env.stored, later]

        with pytest.raises(core_exceptions.PreconditionFailedError):
            server_settings_service.edit_mail_settings(_mail_edit(mail_env.stored, port=465), MagicMock())

        mail_env.write.assert_not_called()
