"""Extra tests for core configuration module."""

import os
from pathlib import Path
from tempfile import gettempdir
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


class TestLookLikeIp:
    """_looks_like_ip: best-effort IP literal detection."""

    def test_valid_ipv4(self):
        from core.network import _looks_like_ip

        assert _looks_like_ip("192.168.1.1") is True

    def test_valid_ipv6(self):
        from core.network import _looks_like_ip

        assert _looks_like_ip("::1") is True

    def test_hostname(self):
        from core.network import _looks_like_ip

        assert _looks_like_ip("example.com") is False

    def test_hostname_with_digits(self):
        from core.network import _looks_like_ip

        assert _looks_like_ip("host123") is False


@patch.dict(os.environ, {}, clear=True)
class TestSettings:
    """Settings pydantic model construction and validation."""

    def test_defaults(self):
        from core.config import Settings

        s = Settings(_env_file=None)
        assert s.LOG_LEVEL == "info"
        assert s.ENVIRONMENT == "production"
        assert s.TZ == "UTC"
        assert s.ENDURAIN_HOST == "http://localhost:8080"

    def test_log_level_lowercased(self):
        from core.config import Settings

        s = Settings(_env_file=None, LOG_LEVEL="DEBUG")
        assert s.LOG_LEVEL == "debug"

    def test_environment_lowercased(self):
        from core.config import Settings

        s = Settings(_env_file=None, ENVIRONMENT="PRODUCTION")
        assert s.ENVIRONMENT == "production"

    def test_host_names_lowercased(self):
        from core.config import Settings

        s = Settings(_env_file=None, PHOTON_API_HOST="PHOTON.EXAMPLE.COM", NOMINATIM_API_HOST="NOMINATIM.EXAMPLE.ORG")
        assert s.PHOTON_API_HOST == "photon.example.com"
        assert s.NOMINATIM_API_HOST == "nominatim.example.org"

    def test_allowed_redirect_schemes_comma_separated(self):
        from core.config import Settings

        s = Settings(_env_file=None, ALLOWED_REDIRECT_SCHEMES="http,https,myapp")
        assert {"http", "https", "myapp"} == s.ALLOWED_REDIRECT_SCHEMES

    def test_allowed_redirect_schemes_empty(self):
        from core.config import Settings

        s = Settings(_env_file=None, ALLOWED_REDIRECT_SCHEMES="")
        assert set() == s.ALLOWED_REDIRECT_SCHEMES

    def test_allowed_redirect_schemes_none(self):
        from core.config import Settings

        s = Settings(_env_file=None, ALLOWED_REDIRECT_SCHEMES=None)
        assert set() == s.ALLOWED_REDIRECT_SCHEMES

    def test_trusted_proxies_comma_separated(self):
        from core.config import Settings

        s = Settings(_env_file=None, TRUSTED_PROXIES="192.168.1.1,10.0.0.1")
        assert s.TRUSTED_PROXIES == ["192.168.1.1", "10.0.0.1"]

    def test_trusted_proxies_empty(self):
        from core.config import Settings

        s = Settings(_env_file=None, TRUSTED_PROXIES="")
        assert s.TRUSTED_PROXIES == []

    def test_trusted_proxies_none(self):
        from core.config import Settings

        s = Settings(_env_file=None, TRUSTED_PROXIES=None)
        assert s.TRUSTED_PROXIES == []

    def test_smtp_secure_type_starttls(self):
        from core.config import Settings

        s = Settings(_env_file=None, SMTP_SECURE_TYPE="STARTTLS")
        assert s.SMTP_SECURE_TYPE == "starttls"

    def test_smtp_secure_type_ssl(self):
        from core.config import Settings

        s = Settings(_env_file=None, SMTP_SECURE_TYPE="SSL")
        assert s.SMTP_SECURE_TYPE == "ssl"

    def test_smtp_secure_type_none(self):
        from core.config import Settings

        s = Settings(_env_file=None, SMTP_SECURE_TYPE=None)
        assert s.SMTP_SECURE_TYPE == "starttls"

    def test_smtp_secure_type_empty(self):
        from core.config import Settings

        s = Settings(_env_file=None, SMTP_SECURE_TYPE="")
        assert s.SMTP_SECURE_TYPE == "starttls"

    def test_smtp_secure_type_invalid(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(_env_file=None, SMTP_SECURE_TYPE="invalid_value")
        assert s.SMTP_SECURE_TYPE == "starttls"

    def test_smtp_secure_type_not_string_defaults_to_starttls(self):
        from core.config import Settings

        s = Settings(_env_file=None, SMTP_SECURE_TYPE=123)
        assert s.SMTP_SECURE_TYPE == "starttls"

    def test_filesystem_defaults(self):
        from core.config import Settings

        s = Settings(_env_file=None, BACKEND_DIR="/custom/backend")
        assert s.DATA_DIR == "/custom/backend/data"
        assert s.LOGS_DIR == "/custom/backend/logs"
        assert s.FILES_DIR == "/custom/backend/data/activity_files"
        assert s.ACTIVITY_MEDIA_DIR == "/custom/backend/data/activity_media"
        assert s.ACTIVITY_THUMBNAILS_DIR == "/custom/backend/data/activity_thumbnails"

    def test_data_dir_custom(self):
        from core.config import Settings

        s = Settings(_env_file=None, DATA_DIR="/custom/data")
        assert s.DATA_DIR == "/custom/data"
        assert s.FILES_DIR == "/custom/data/activity_files"

    def test_development_trusted_proxies_default(self):
        from core.config import Settings

        s = Settings(_env_file=None, ENVIRONMENT="development")
        assert s.TRUSTED_PROXIES == ["*"]

    def test_trusted_proxies_with_hostname(self):
        from core.config import Settings

        s = Settings(_env_file=None, TRUSTED_PROXIES="proxy.internal,192.168.1.1")
        assert s.TRUSTED_PROXIES == ["proxy.internal", "192.168.1.1"]

    def test_trusted_proxies_with_cidr(self):
        from core.config import Settings

        s = Settings(_env_file=None, TRUSTED_PROXIES="10.0.0.0/8,proxy.internal")
        assert s.TRUSTED_PROXIES == ["10.0.0.0/8", "proxy.internal"]

    def test_trusted_proxies_with_wildcard(self):
        from core.config import Settings

        s = Settings(_env_file=None, TRUSTED_PROXIES="*")
        assert s.TRUSTED_PROXIES == ["*"]

    def test_trusted_proxies_mixed_formats(self):
        from core.config import Settings

        s = Settings(_env_file=None, TRUSTED_PROXIES="192.168.1.1,10.0.0.0/8,proxy.local,*")
        assert len(s.TRUSTED_PROXIES) == 4
        assert "192.168.1.1" in s.TRUSTED_PROXIES
        assert "10.0.0.0/8" in s.TRUSTED_PROXIES
        assert "proxy.local" in s.TRUSTED_PROXIES
        assert "*" in s.TRUSTED_PROXIES

    def test_trusted_proxies_invalid_cidr_rejected(self):
        from pydantic import ValidationError

        from core.config import Settings

        with pytest.raises(ValidationError):
            Settings(_env_file=None, TRUSTED_PROXIES="999.999.999.999/32")

    def test_trusted_proxies_invalid_hostname_rejected(self):
        from pydantic import ValidationError

        from core.config import Settings

        with pytest.raises(ValidationError):
            Settings(_env_file=None, TRUSTED_PROXIES="caddy:8080")

        with pytest.raises(ValidationError):
            Settings(_env_file=None, TRUSTED_PROXIES="http://caddy")

    def test_trusted_proxies_resolved_ips_cache_initialized(self):
        from core.config import Settings

        s = Settings(_env_file=None, TRUSTED_PROXIES="proxy.internal")
        # Cache should be initialized as empty set
        assert s._resolved_trusted_proxy_ips == set()

    def test_csp_additional_connect_src_default_empty(self):
        from core.config import Settings

        s = Settings(_env_file=None)
        assert s.CSP_ADDITIONAL_CONNECT_SRC == []

    def test_csp_additional_connect_src_comma_separated(self):
        from core.config import Settings

        s = Settings(
            _env_file=None,
            CSP_ADDITIONAL_CONNECT_SRC="https://auth.example.com,https://proxy.example.com",
        )
        assert s.CSP_ADDITIONAL_CONNECT_SRC == [
            "https://auth.example.com",
            "https://proxy.example.com",
        ]

    def test_csp_additional_connect_src_empty_string(self):
        from core.config import Settings

        s = Settings(_env_file=None, CSP_ADDITIONAL_CONNECT_SRC="")
        assert s.CSP_ADDITIONAL_CONNECT_SRC == []

    def test_csp_additional_connect_src_none(self):
        from core.config import Settings

        s = Settings(_env_file=None, CSP_ADDITIONAL_CONNECT_SRC=None)
        assert s.CSP_ADDITIONAL_CONNECT_SRC == []

    def test_csp_additional_connect_src_rejects_injection_entries(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(
                _env_file=None,
                CSP_ADDITIONAL_CONNECT_SRC="https://ok.example.com,bad; script-src *,has space",
            )
        # Entries with ';' or whitespace are dropped; the valid one survives.
        assert s.CSP_ADDITIONAL_CONNECT_SRC == ["https://ok.example.com"]

    def test_csp_additional_connect_src_drops_bare_wildcard_keeps_host_wildcard(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(
                _env_file=None,
                CSP_ADDITIONAL_CONNECT_SRC="*,https://*.example.com,https://auth.example.com",
            )
        # Bare '*' is dropped; host wildcards and exact origins are preserved.
        assert s.CSP_ADDITIONAL_CONNECT_SRC == [
            "https://*.example.com",
            "https://auth.example.com",
        ]

    def test_csp_additional_connect_src_drops_scheme_only_sources(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(
                _env_file=None,
                CSP_ADDITIONAL_CONNECT_SRC="https:,ws:,https://auth.example.com",
            )
        # Scheme-only sources are dropped; the exact origin survives.
        assert s.CSP_ADDITIONAL_CONNECT_SRC == ["https://auth.example.com"]

    def test_reverse_geo_rate_limit_float(self):
        from core.config import Settings

        s = Settings(_env_file=None, REVERSE_GEO_RATE_LIMIT="2.5")
        assert s.REVERSE_GEO_RATE_LIMIT == 2.5

    def test_reverse_geo_rate_limit_empty(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(_env_file=None, REVERSE_GEO_RATE_LIMIT="")
        assert s.REVERSE_GEO_RATE_LIMIT == 1.0

    def test_reverse_geo_rate_limit_invalid(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(_env_file=None, REVERSE_GEO_RATE_LIMIT="not-a-number")
        assert s.REVERSE_GEO_RATE_LIMIT == 1.0


@patch.dict(os.environ, {}, clear=True)
class TestSettingsSsrfAllowedHosts:
    """SSRF_ALLOWED_HOSTS validator."""

    def test_empty(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="")
        assert s.SSRF_ALLOWED_HOSTS == []

    def test_none(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS=None)
        assert s.SSRF_ALLOWED_HOSTS == []

    def test_valid_hostname(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="auth.example.com")
        assert s.SSRF_ALLOWED_HOSTS == ["auth.example.com"]

    def test_hostname_with_scheme_stripped_via_port(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="https://oidc.example.com")
        assert s.SSRF_ALLOWED_HOSTS == []

    def test_hostname_with_port(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="auth.example.com:8443")
        assert s.SSRF_ALLOWED_HOSTS == ["auth.example.com"]

    def test_ipv4_cidr(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="10.10.0.0/24")
        assert s.SSRF_ALLOWED_HOSTS == ["10.10.0.0/24"]

    def test_ipv6_cidr(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="fd00::/32")
        assert "fd00::/32" in s.SSRF_ALLOWED_HOSTS

    def test_single_ip(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="10.10.0.5")
        assert s.SSRF_ALLOWED_HOSTS == ["10.10.0.5/32"]

    def test_wildcard_rejected(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="*")
        assert s.SSRF_ALLOWED_HOSTS == []

    def test_broad_ipv4_range_rejected(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="0.0.0.0/0")
        assert s.SSRF_ALLOWED_HOSTS == []

    def test_broad_ipv6_range_rejected(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="::/0")
        assert s.SSRF_ALLOWED_HOSTS == []

    def test_invalid_cidr_rejected(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="not-a-cidr/abc")
        assert s.SSRF_ALLOWED_HOSTS == []

    def test_mixed_valid_and_invalid(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="valid.example.com,*,10.10.0.0/24")
        assert "valid.example.com" in s.SSRF_ALLOWED_HOSTS
        assert "10.10.0.0/24" in s.SSRF_ALLOWED_HOSTS
        assert len(s.SSRF_ALLOWED_HOSTS) == 2

    def test_ipv6_literal_hostname(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="[::1]:8080")
        assert "::1" in s.SSRF_ALLOWED_HOSTS

    def test_lowercased_hostname(self):
        from core.config import Settings

        s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="AUTH.EXAMPLE.COM")
        assert s.SSRF_ALLOWED_HOSTS == ["auth.example.com"]

    def test_bracket_only_hostname_empty_after_strip(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console"):
            s = Settings(_env_file=None, SSRF_ALLOWED_HOSTS="[]")
        assert s.SSRF_ALLOWED_HOSTS == []


@patch.dict(os.environ, {}, clear=True)
class TestSettingsWarnings:
    """Settings model_validator warnings."""

    def test_memory_rate_limit_warning_production(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console") as mock_log:
            Settings(
                _env_file=None,
                ENVIRONMENT="production",
                RATE_LIMIT_STORAGE_URI="memory://",
                RATE_LIMIT_ENABLED=True,
            )
        mock_log.assert_any_call(
            "RATE_LIMIT_STORAGE_URI uses process-local memory outside "
            "development. API rate-limit counters are not shared "
            "across workers; use Redis for multi-worker deployments.",
            "warning",
        )

    def test_memory_auth_security_storage_warning_production(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console") as mock_log:
            Settings(
                _env_file=None,
                ENVIRONMENT="production",
                RATE_LIMIT_STORAGE_URI="memory://",
                AUTH_SECURITY_STORAGE_URI=None,
                RATE_LIMIT_ENABLED=True,
            )
        mock_log.assert_any_call(
            "AUTH_SECURITY_STORAGE_URI resolves to process-local "
            "memory outside development. Login lockout and pending "
            "MFA state, including setup secrets, are not shared "
            "across workers; use Redis for multi-worker deployments.",
            "warning",
        )

    def test_no_warnings_in_development(self):
        from core.config import Settings

        with patch("core.config.core_logger.print_to_log_and_console") as mock_log:
            Settings(
                _env_file=None, ENVIRONMENT="development", RATE_LIMIT_STORAGE_URI="memory://", RATE_LIMIT_ENABLED=True
            )
        relevant = [c for c in mock_log.call_args_list if "process-local memory" in str(c)]
        assert len(relevant) == 0


class TestReadSecret:
    """read_secret: env var and Docker secrets file loading."""

    def test_from_env_var(self):
        from core.config import read_secret

        with patch.dict(os.environ, {"MY_SECRET": "direct_value"}):
            result = read_secret("MY_SECRET")

        assert result == "direct_value"

    def test_from_file(self, tmp_path):
        from core.config import read_secret

        secret_file = tmp_path / "my_secret.txt"
        secret_file.write_text("file_value\n")
        secret_file.chmod(0o600)

        with (
            patch.dict(os.environ, {"MY_SECRET_FILE": str(secret_file)}),
            patch("core.config._is_safe_path", return_value=True),
        ):
            result = read_secret("MY_SECRET")

        assert result == "file_value"

    def test_default_when_not_found(self):
        from core.config import read_secret

        with patch.dict(os.environ, {}):
            result = read_secret("NONEXISTENT", default_value="default_value")

        assert result == "default_value"

    def test_none_when_not_found_no_default(self):
        from core.config import read_secret

        with patch.dict(os.environ, {"SOME_OTHER_VAR": "x"}):
            result = read_secret("NONEXISTENT")

        assert result is None

    def test_file_not_found_raises(self):
        from core.config import read_secret

        with (
            patch.dict(os.environ, {"MY_SECRET_FILE": "/secrets/secret.txt"}),
            pytest.raises(OSError, match="Error reading secret file"),
        ):
            read_secret("MY_SECRET")

    def test_file_is_directory_raises(self, tmp_path):
        from core.config import read_secret

        with (
            patch.dict(os.environ, {"MY_SECRET_FILE": str(tmp_path)}),
            patch("core.config._is_safe_path", return_value=True),
            pytest.raises(OSError, match="Error reading secret file"),
        ):
            read_secret("MY_SECRET")

    def test_file_too_large_raises(self, tmp_path):
        from core.config import read_secret

        large_file = tmp_path / "large_secret.txt"
        large_file.write_text("x" * 65537)
        large_file.chmod(0o600)

        with (
            patch.dict(os.environ, {"MY_SECRET_FILE": str(large_file)}),
            patch("core.config._is_safe_path", return_value=True),
            pytest.raises(OSError, match="Error reading secret file"),
        ):
            read_secret("MY_SECRET")

    def test_world_readable_warning(self, tmp_path):
        from core.config import read_secret

        secret_file = tmp_path / "world_readable.txt"
        secret_file.write_text("secret_value\n")
        secret_file.chmod(0o644)

        with (
            patch.dict(os.environ, {"MY_SECRET_FILE": str(secret_file)}),
            patch("core.config._is_safe_path", return_value=True),
            patch("core.config.core_logger.print_to_log_and_console") as mock_log,
        ):
            result = read_secret("MY_SECRET")

        assert result == "secret_value"
        warning_calls = [c for c in mock_log.call_args_list if "world-readable" in str(c)]
        assert len(warning_calls) >= 1

    def test_empty_file_warning(self, tmp_path):
        from core.config import read_secret

        empty_file = tmp_path / "empty_secret.txt"
        empty_file.write_text("")
        empty_file.chmod(0o600)

        with (
            patch.dict(os.environ, {"MY_SECRET_FILE": str(empty_file)}),
            patch("core.config._is_safe_path", return_value=True),
            patch("core.config.core_logger.print_to_log_and_console") as mock_log,
        ):
            result = read_secret("MY_SECRET")

        assert result is None
        warning_calls = [c for c in mock_log.call_args_list if "empty" in str(c)]
        assert len(warning_calls) >= 1

    def test_unsafe_path_raises(self):
        from core.config import read_secret

        with (
            patch.dict(os.environ, {"MY_SECRET_FILE": "/etc/passwd"}),
            patch("core.config._is_safe_path", return_value=False),
            pytest.raises(OSError, match="Error reading secret file"),
        ):
            read_secret("MY_SECRET")

    def test_unexpected_exception_during_read_raises(self, tmp_path):
        from core.config import read_secret

        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("value")
        secret_file.chmod(0o600)

        with (
            patch.dict(os.environ, {"MY_SECRET_FILE": str(secret_file)}),
            patch("core.config._is_safe_path", return_value=True),
            patch("pathlib.Path.open", side_effect=TypeError("unexpected type")),
            pytest.raises(OSError, match="Unexpected error reading secret"),
        ):
            read_secret("MY_SECRET")


class TestIsSafePath:
    """_is_safe_path: path traversal protection."""

    def test_docker_secrets_path(self):
        from core.config import _is_safe_path

        assert _is_safe_path(Path("/run/secrets/db_password")) is True

    def test_alternative_secrets_path(self):
        from core.config import _is_safe_path

        assert _is_safe_path(Path("/var/run/secrets/db_password")) is True

    def test_custom_secrets_path(self):
        from core.config import _is_safe_path

        assert _is_safe_path(Path("/secrets/my_secret")) is True

    def test_arbitrary_path(self):
        from core.config import _is_safe_path

        assert _is_safe_path(Path("/etc/passwd")) is False

    def test_development_tmp_path(self):
        from core.config import _is_safe_path

        with patch("core.config.settings.ENVIRONMENT", "development"):
            tmp = Path(gettempdir()) / "test_secret"
            result = _is_safe_path(tmp)
        assert result is True

    def test_development_cwd(self):
        from core.config import _is_safe_path

        with patch("core.config.settings.ENVIRONMENT", "development"):
            cwd = Path.cwd().resolve()
            result = _is_safe_path(cwd / "some_file.txt")
        assert result is True

    def test_exception_during_safe_path_check_returns_false(self):
        from core.config import _is_safe_path

        class _EvilPath:
            def __str__(self):
                raise TypeError("evil")

        assert _is_safe_path(_EvilPath()) is False


class TestValidateFernetKey:
    """validate_fernet_key: Fernet format validation."""

    def test_valid_key(self):
        from core.config import validate_fernet_key

        key = Fernet.generate_key().decode()
        assert validate_fernet_key(key) is True

    def test_none_key(self):
        from core.config import validate_fernet_key

        assert validate_fernet_key(None) is False

    def test_empty_key(self):
        from core.config import validate_fernet_key

        assert validate_fernet_key("") is False

    def test_invalid_format(self):
        from core.config import validate_fernet_key

        assert validate_fernet_key("not-a-valid-fernet-key") is False

    def test_unexpected_exception_during_fernet_validation_returns_false(self):
        from core.config import validate_fernet_key

        with patch("core.config.core_logger.print_to_log_and_console"):
            result = validate_fernet_key(b"some bytes")
        assert result is False


class TestValidateLogLevel:
    """validate_log_level: log level string validation."""

    def test_valid_levels(self):
        from core.config import validate_log_level

        for level in ("critical", "error", "warning", "info", "debug", "trace"):
            assert validate_log_level(level) is True

    def test_case_insensitive(self):
        from core.config import validate_log_level

        assert validate_log_level("INFO") is True
        assert validate_log_level("Debug") is True

    def test_invalid_level(self):
        from core.config import validate_log_level

        assert validate_log_level("invalid") is False


class TestCheckRequiredEnvVars:
    """check_required_env_vars: startup validation."""

    def _minimal_env(self, **overrides):
        env = {
            "DB_PASSWORD": "dbpass",
            "SECRET_KEY": "secretkey",
            "FERNET_KEY": Fernet.generate_key().decode(),
            "ENDURAIN_HOST": "http://localhost:8080",
        }
        env.update(overrides)
        return env

    def test_all_required_present(self):
        from core.config import check_required_env_vars

        with (
            patch.dict(os.environ, self._minimal_env(), clear=True),
            patch("core.config.core_logger.print_to_log_and_console"),
        ):
            check_required_env_vars()

    def test_missing_db_password_raises(self):
        from core.config import check_required_env_vars

        env = self._minimal_env()
        env.pop("DB_PASSWORD", None)
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(OSError, match="Missing required environment variable: DB_PASSWORD"),
        ):
            check_required_env_vars()

    def test_missing_enduraint_host_raises(self):
        from core.config import check_required_env_vars

        env = self._minimal_env()
        env.pop("ENDURAIN_HOST", None)
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(OSError, match="Missing required environment variable: ENDURAIN_HOST"),
        ):
            check_required_env_vars()

    def test_invalid_fernet_key_warns(self):
        from core.config import check_required_env_vars

        with (
            patch.dict(os.environ, self._minimal_env(FERNET_KEY="invalid-key"), clear=True),
            pytest.raises(ValueError, match="FERNET_KEY validation failed"),
        ):
            check_required_env_vars()

    def test_email_not_configured(self):
        from core.config import check_required_env_vars

        with (
            patch.dict(os.environ, self._minimal_env(), clear=True),
            patch("core.config.core_logger.print_to_log_and_console") as mock_log,
        ):
            check_required_env_vars()

        info_calls = [c for c in mock_log.call_args_list if "Email not configured" in str(c)]
        assert len(info_calls) >= 1

    def test_secret_via_file_variant(self):
        from core.config import check_required_env_vars

        with (
            patch.dict(
                os.environ,
                self._minimal_env(
                    DB_PASSWORD_FILE="/run/secrets/db_password", SECRET_KEY_FILE="/run/secrets/secret_key"
                ),
                clear=True,
            ),
            patch("core.config.core_logger.print_to_log_and_console"),
        ):
            check_required_env_vars()


class TestCheckRequiredDirs:
    """check_required_dirs: directory creation and validation."""

    def test_creates_missing_dirs(self, tmp_path):
        from core.config import check_required_dirs

        test_data = tmp_path / "data"
        with (
            patch("core.config.settings.DATA_DIR", str(test_data)),
            patch("core.config.settings.LOGS_DIR", str(tmp_path / "logs")),
            patch("core.config.settings.FILES_DIR", str(test_data / "activity_files")),
            patch("core.config.settings.ACTIVITY_MEDIA_DIR", str(test_data / "activity_media")),
            patch("core.config.settings.ACTIVITY_THUMBNAILS_DIR", str(test_data / "activity_thumbnails")),
            patch("core.config.USER_IMAGES_DIR", str(test_data / "user_images")),
            patch("core.config.SERVER_IMAGES_DIR", str(test_data / "server_images")),
            patch("core.config.FILES_PROCESSED_DIR", str(test_data / "activity_files" / "processed")),
            patch("core.config.FILES_BULK_IMPORT_DIR", str(test_data / "activity_files" / "bulk_import")),
            patch(
                "core.config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR",
                str(test_data / "activity_files" / "bulk_import" / "import_errors"),
            ),
        ):
            check_required_dirs()

        assert test_data.exists()

    def test_file_path_where_dir_expected_raises(self, tmp_path):
        from core.config import check_required_dirs

        file_path = tmp_path / "not_a_dir"
        file_path.write_text("this is a file, not a directory")

        with (
            patch("core.config.settings.DATA_DIR", str(file_path)),
            patch("core.config.settings.LOGS_DIR", str(tmp_path / "logs")),
            patch("core.config.settings.FILES_DIR", str(tmp_path / "files")),
            patch("core.config.settings.ACTIVITY_MEDIA_DIR", str(tmp_path / "activity_media")),
            patch("core.config.settings.ACTIVITY_THUMBNAILS_DIR", str(tmp_path / "activity_thumbnails")),
            patch("core.config.USER_IMAGES_DIR", str(tmp_path / "user_images")),
            patch("core.config.SERVER_IMAGES_DIR", str(tmp_path / "server_images")),
            patch("core.config.FILES_PROCESSED_DIR", str(tmp_path / "processed")),
            patch("core.config.FILES_BULK_IMPORT_DIR", str(tmp_path / "bulk_import")),
            patch("core.config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR", str(tmp_path / "import_errors")),
            pytest.raises(OSError, match="Required directory is not a directory"),
        ):
            check_required_dirs()


class TestModuleLevelConstants:
    """Module-level derived constants."""

    def test_api_version(self):
        from core.config import API_VERSION

        assert API_VERSION == "v0.19.1"

    def test_license_constants(self):
        from core.config import LICENSE_IDENTIFIER, LICENSE_NAME, LICENSE_URL

        assert "AGPL" in LICENSE_IDENTIFIER
        assert LICENSE_NAME == "GNU Affero General Public License v3.0 or later"
        assert "spdx.org" in LICENSE_URL

    def test_root_path(self):
        from core.config import ROOT_PATH

        assert ROOT_PATH == "/api/v1"

    def test_image_dirs(self):
        from core.config import SERVER_IMAGES_DIR, USER_IMAGES_DIR, settings

        assert f"{settings.DATA_DIR}/user_images" == USER_IMAGES_DIR
        assert f"{settings.DATA_DIR}/server_images" == SERVER_IMAGES_DIR

    def test_reverse_geo_constants(self):
        from core.config import REVERSE_GEO_LAST_CALL, REVERSE_GEO_MIN_INTERVAL

        assert isinstance(REVERSE_GEO_MIN_INTERVAL, float)
        assert REVERSE_GEO_LAST_CALL == 0.0

    def test_supported_file_formats(self):
        from core.config import SUPPORTED_FILE_FORMATS

        assert ".fit" in SUPPORTED_FILE_FORMATS
        assert ".gpx" in SUPPORTED_FILE_FORMATS


class TestCheckDeprecatedEnvVars:
    """check_deprecated_env_vars: fail-fast on variables retired in v0.19.x."""

    @patch.dict(os.environ, {}, clear=True)
    def test_no_deprecated_vars_passes_silently(self):
        from core.config import check_deprecated_env_vars

        with patch("core.config.core_logger.print_to_log_and_console") as mock_log:
            check_deprecated_env_vars()

        assert mock_log.call_count == 0

    @patch.dict(os.environ, {"SOME_CURRENT_VAR": "value"}, clear=True)
    def test_unrelated_var_passes_silently(self):
        from core.config import check_deprecated_env_vars

        with patch("core.config.core_logger.print_to_log_and_console") as mock_log:
            check_deprecated_env_vars()

        assert mock_log.call_count == 0

    @patch.dict(os.environ, {"FRONTEND_PROTOCOL": "https"}, clear=True)
    def test_frontend_protocol_aborts_with_replacement_hint(self):
        from core.config import check_deprecated_env_vars

        with (
            patch("core.config.core_logger.print_to_log_and_console") as mock_log,
            pytest.raises(OSError, match="FRONTEND_PROTOCOL"),
        ):
            check_deprecated_env_vars()

        logged = " ".join(str(call) for call in mock_log.call_args_list)
        assert "FRONTEND_PROTOCOL" in logged
        # Remediation points operators at the replacement variable.
        assert "ENVIRONMENT" in logged

    @patch.dict(os.environ, {"UID": "1000"}, clear=True)
    def test_uid_aborts_with_compose_guidance(self):
        from core.config import check_deprecated_env_vars

        with (
            patch("core.config.core_logger.print_to_log_and_console") as mock_log,
            pytest.raises(OSError, match="UID"),
        ):
            check_deprecated_env_vars()

        logged = " ".join(str(call) for call in mock_log.call_args_list)
        assert "docker-compose" in logged

    @patch.dict(
        os.environ,
        {"UID": "1000", "GID": "1000", "FRONTEND_PROTOCOL": "http"},
        clear=True,
    )
    def test_multiple_deprecated_vars_reported_together(self):
        from core.config import check_deprecated_env_vars

        with (
            patch("core.config.core_logger.print_to_log_and_console") as mock_log,
            pytest.raises(OSError) as exc_info,
        ):
            check_deprecated_env_vars()

        # A single abort lists every offending variable at once so the
        # operator can fix the deployment in one pass.
        message = str(exc_info.value)
        assert "UID" in message
        assert "GID" in message
        assert "FRONTEND_PROTOCOL" in message

        # One header line plus one line per offending variable.
        assert mock_log.call_count == 4

    def test_mapping_contains_expected_keys(self):
        from core.config import DEPRECATED_ENV_VARS

        assert set(DEPRECATED_ENV_VARS) == {"UID", "GID", "FRONTEND_PROTOCOL"}
        assert all(isinstance(hint, str) and hint for hint in DEPRECATED_ENV_VARS.values())
