"""The admin log routes on the production application: paging, download and the step-up-guarded clear."""

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from jasil.audit.models import AuditLog

import core.config as core_config
import modules.server_settings.logs_service as logs_service
from tests.server_settings.conftest import API, STEP_UP

_LOGS_URL = f"{API}/server-settings/logs"


def _line(level: str, message: str) -> str:
    return json.dumps({"timestamp": "2026-01-01T00:00:00+00:00", "level": level, "logger": "x", "message": message})


@pytest.fixture
def log_file() -> Path:
    """The log file the viewer reads, holding three records of known messages."""
    path = Path(core_config.settings.LOGS_DIR) / logs_service.LOG_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{_line(level, message)}\n" for level, message in _RECORDS))
    return path


_RECORDS = (("INFO", "probe-one"), ("WARNING", "probe-two"), ("ERROR", "probe-three"))


@pytest.fixture
def no_log_file(tmp_path, monkeypatch) -> None:
    """Point the viewer at a directory where no log has been written."""
    monkeypatch.setattr(core_config.settings, "LOGS_DIR", str(tmp_path / "no-logs-here"))


def _audit_rows(committed_sessions, action_id: str) -> list[AuditLog]:
    with committed_sessions() as db:
        rows = list(db.scalars(sa.select(AuditLog).where(AuditLog.action_id == action_id)))
        db.expunge_all()
    return rows


class TestReadLogs:
    def test_the_page_names_its_records_and_the_cursor_to_continue_from(self, admin_client, log_file):
        response = admin_client.get(f"{_LOGS_URL}?message_contains=probe&num_records=2")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items", "num_records", "next_cursor"}
        assert [item["message"] for item in body["items"]] == ["probe-two", "probe-three"]
        assert body["num_records"] == 2

    def test_the_level_query_keeps_the_given_severity_and_above(self, admin_client, log_file):
        response = admin_client.get(f"{_LOGS_URL}?message_contains=probe&level=WARNING")

        assert [item["message"] for item in response.json()["items"]] == ["probe-two", "probe-three"]

    def test_the_cursor_returns_only_records_written_after_it(self, admin_client, log_file):
        cursor = admin_client.get(f"{_LOGS_URL}?message_contains=probe").json()["next_cursor"]
        with log_file.open("a") as handle:
            handle.write(_line("INFO", "probe-four") + "\n")

        response = admin_client.get(f"{_LOGS_URL}?message_contains=probe&cursor={cursor}")

        assert [item["message"] for item in response.json()["items"]] == ["probe-four"]

    @pytest.mark.parametrize("query", ["after=3", "limit=5", "search=probe-two"])
    def test_the_names_of_the_old_api_are_ignored(self, admin_client, log_file, query):
        response = admin_client.get(f"{_LOGS_URL}?message_contains=probe&{query}")

        assert response.status_code == 200
        assert len(response.json()["items"]) == 3

    @pytest.mark.parametrize("cursor", ["abc", "-1", "1" * 19])
    def test_a_cursor_that_is_not_a_position_is_a_422(self, admin_client, log_file, cursor):
        assert admin_client.get(f"{_LOGS_URL}?cursor={cursor}").status_code == 422

    def test_a_missing_log_file_is_an_empty_page(self, admin_client, no_log_file):
        response = admin_client.get(_LOGS_URL)

        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_a_disabled_viewer_is_a_404(self, admin_client, log_file, monkeypatch):
        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", "demo")

        assert admin_client.get(_LOGS_URL).status_code == 404

    def test_the_status_route_and_the_delete_method_do_not_exist(self, admin_client):
        assert admin_client.get(f"{_LOGS_URL}/status").status_code == 404
        assert admin_client.delete(_LOGS_URL).status_code == 405


class TestDownloadLogs:
    def test_the_current_file_is_downloaded_and_the_download_audited(self, admin_client, log_file, committed_sessions):
        response = admin_client.get(f"{_LOGS_URL}/download")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "app.log" in response.headers["content-disposition"]
        assert response.content == log_file.read_bytes()
        (row,) = _audit_rows(committed_sessions, "server_settings.logs.download")
        assert row.details is None

    def test_no_log_file_is_a_404_and_is_not_audited(self, admin_client, committed_sessions, no_log_file):
        response = admin_client.get(f"{_LOGS_URL}/download")

        assert response.status_code == 404
        assert _audit_rows(committed_sessions, "server_settings.logs.download") == []

    def test_a_disabled_viewer_is_a_404(self, admin_client, log_file, monkeypatch):
        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", "demo")

        assert admin_client.get(f"{_LOGS_URL}/download").status_code == 404


class TestClearLogs:
    def test_the_log_and_its_rotated_backups_are_emptied_and_the_clear_audited(
        self, admin_client, log_file, committed_sessions
    ):
        (log_file.parent / "app.log.1").write_text("older")
        (log_file.parent / "app.log.2").write_text("oldest")
        (log_file.parent / "other.log").write_text("keep")
        (log_file.parent / "app.log.bak").write_text("keep too")

        response = admin_client.post(f"{_LOGS_URL}/clear", json={"step_up": STEP_UP})

        assert response.status_code == 204
        assert "probe-one" not in log_file.read_text()
        assert not (log_file.parent / "app.log.1").exists()
        assert not (log_file.parent / "app.log.2").exists()
        assert (log_file.parent / "other.log").read_text() == "keep"
        assert (log_file.parent / "app.log.bak").read_text() == "keep too"
        (row,) = _audit_rows(committed_sessions, "server_settings.logs.clear")
        assert row.details is None

    def test_clearing_when_no_file_was_written_is_a_204(self, admin_client, no_log_file):
        assert admin_client.post(f"{_LOGS_URL}/clear", json={"step_up": STEP_UP}).status_code == 204

    def test_a_wrong_password_is_a_403_that_clears_and_audits_nothing(self, admin_client, log_file, committed_sessions):
        (log_file.parent / "app.log.1").write_text("older")

        response = admin_client.post(f"{_LOGS_URL}/clear", json={"step_up": {"current_password": "not-my-password"}})

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"
        assert "probe-one" in log_file.read_text()
        assert (log_file.parent / "app.log.1").exists()
        assert _audit_rows(committed_sessions, "server_settings.logs.clear") == []

    def test_a_body_without_a_step_up_is_a_422(self, admin_client, log_file):
        response = admin_client.post(f"{_LOGS_URL}/clear", json={})

        assert response.status_code == 422
        assert "probe-one" in log_file.read_text()

    def test_a_disabled_viewer_is_a_404_and_clears_nothing(self, admin_client, log_file, monkeypatch):
        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", "demo")

        response = admin_client.post(f"{_LOGS_URL}/clear", json={"step_up": STEP_UP})

        assert response.status_code == 404
        assert "probe-one" in log_file.read_text()
