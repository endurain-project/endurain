"""The map tile policy: which sources the CSP allows, the built-in presets and the settings read that feeds them."""

import pytest
from sqlalchemy import delete

import core.exceptions as core_exceptions
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.models as server_settings_models
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.tile_service as server_settings_tile_service
from tests._factories.server_settings import edit_server_settings
from tests.server_settings.conftest import INTERNAL_HOST


class TestExtractDomainFromTileUrl:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}.png", "https://tiles.stadiamaps.com"),
            ("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", "https://a.tile.openstreetmap.org"),
            ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", "https://tile.openstreetmap.org"),
            ("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", "https://*.tile.openstreetmap.org"),
            ("https://{S}.tile.openstreetmap.org/{z}/{x}/{y}.png", "https://*.tile.openstreetmap.org"),
            ("http://localhost:8080/tiles/{z}/{x}/{y}.png", "http://localhost:8080"),
            ("http://localhost/tiles/{z}/{x}/{y}.png", "http://localhost"),
            ("http://127.0.0.1:3000/tiles/{z}/{x}/{y}.png", "http://127.0.0.1:3000"),
            ("https://tiles.example.com:8443/map/{z}/{x}/{y}.png", "https://tiles.example.com:8443"),
            ("https://tiles.example.co.uk/{z}/{x}/{y}.png", "https://tiles.example.co.uk"),
            ("https://{s}.tiles.example.co.uk/{z}/{x}/{y}.png", "https://*.tiles.example.co.uk"),
            ("http://10.0.0.5:8080/{z}/{x}/{y}.png", "http://10.0.0.5:8080"),
            ("http://[::1]:8080/{z}/{x}/{y}.png", "http://[::1]:8080"),
        ],
    )
    def test_the_source_is_the_tile_host_and_never_a_wider_domain(self, url, expected):
        assert server_settings_tile_service.extract_domain_from_tile_url(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "tiles.example.com/{z}/{x}/{y}.png",
            "",
            "not-a-valid-url",
            "https://tiles.example.com:notaport/{z}/{x}/{y}.png",
        ],
    )
    def test_a_url_without_a_scheme_or_host_or_with_a_bad_port_has_no_source(self, url):
        assert server_settings_tile_service.extract_domain_from_tile_url(url) is None


class TestAllowedTileDomainsForUrl:
    def test_a_custom_host_is_added_to_the_builtin_domains(self):
        result = server_settings_tile_service.allowed_tile_domains_for_url("https://tiles.example.com/{z}/{x}/{y}.png")

        assert result[-1] == "https://tiles.example.com"
        assert len(result) == 3

    def test_a_host_a_builtin_wildcard_covers_adds_nothing(self):
        result = server_settings_tile_service.allowed_tile_domains_for_url(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        )

        assert len(result) == 2

    def test_a_builtin_wildcard_does_not_cover_the_same_host_over_another_scheme(self):
        result = server_settings_tile_service.allowed_tile_domains_for_url(
            "http://tile.openstreetmap.org/{z}/{x}/{y}.png"
        )

        assert result[-1] == "http://tile.openstreetmap.org"

    def test_a_url_with_no_host_adds_nothing(self):
        assert len(server_settings_tile_service.allowed_tile_domains_for_url("not-a-url")) == 2

    def test_the_result_is_a_copy_the_caller_may_change(self):
        first = server_settings_tile_service.allowed_tile_domains_for_url("not-a-url")
        first.append("https://changed.example.org")

        assert len(server_settings_tile_service.allowed_tile_domains_for_url("not-a-url")) == 2


class TestRejectUnsafeTileserver:
    @pytest.mark.parametrize(
        "url", ["https://tiles.example.org/{z}/{x}/{y}/{", "https://tiles.example.org/}{z}/{x}/{y}.png"]
    )
    def test_a_template_with_an_unbalanced_brace_is_refused_before_any_lookup(self, url, dns):
        with pytest.raises(core_exceptions.InvalidInputError, match="placeholder the renderer cannot fill"):
            server_settings_tile_service.reject_unsafe_tileserver(url)

        assert dns.names == []

    def test_a_template_resolving_to_a_private_address_is_refused(self, dns):
        with pytest.raises(core_exceptions.InvalidInputError):
            server_settings_tile_service.reject_unsafe_tileserver(f"https://{INTERNAL_HOST}/{{z}}/{{x}}/{{y}}.png")

        assert dns.names == [INTERNAL_HOST]


class TestTileMapsTemplates:
    def test_every_template_is_a_valid_schema_with_its_id(self):
        templates = server_settings_tile_service.get_tile_maps_templates()

        assert len(templates) > 0
        assert all(isinstance(template, server_settings_schema.TileMapsTemplate) for template in templates)
        assert len({template.template_id for template in templates}) == len(templates)
        assert "openstreetmap" in {template.template_id for template in templates}


class TestAllowedTileDomainsFromSettings:
    def test_the_stored_custom_tile_server_is_allowed(self, db):
        edit_server_settings(db, tileserver_url="https://tiles.example.org/{z}/{x}/{y}.png")

        domains = server_settings_integration.get_allowed_tile_domains(db)

        assert domains[-1] == "https://tiles.example.org"
        assert len(domains) == 3

    def test_a_builtin_tile_server_adds_nothing(self, db):
        assert len(server_settings_integration.get_allowed_tile_domains(db)) == 2

    def test_a_missing_settings_row_allows_only_the_builtin_domains(self, db):
        db.execute(delete(server_settings_models.ServerSettings))

        assert len(server_settings_integration.get_allowed_tile_domains(db)) == 2
