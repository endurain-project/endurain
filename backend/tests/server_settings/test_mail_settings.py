"""The mail settings and the test email on the production application; the recording mail outbox stands in for SMTP."""

import uuid

import jasil.providers as platform_providers
import jasil.runtime as jasil_runtime
import jasil.testing as jasil_testing
import pytest
import sqlalchemy as sa
from jasil.audit.models import AuditLog

import core.exceptions as core_exceptions
import modules.server_settings.change_utils as server_settings_change_utils
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.mail_service as server_settings_mail_service
import modules.server_settings.models as server_settings_models
from tests._factories.server_settings import edit_mail_settings
from tests.server_settings.conftest import API, INTERNAL_HOST, MAIL_URL, STEP_UP

_TEST_EMAIL_URL = f"{API}/server-settings/email/test"
_VALID = {
    "host": "smtp.example.org",
    "port": 587,
    "security": "starttls",
    "username": "mailer",
    "password": "s3cret",
    "from_address": "no-reply@example.org",
}


def _put(client, *, at: int = 1, without_password: bool = False, **changes: object):
    body = {**_VALID, "step_up": STEP_UP, **changes}
    if without_password:
        del body["password"]
    return client.put(MAIL_URL, json=body, headers={"If-Match": f'"{at}"'})


def _stored(committed_sessions):
    with committed_sessions() as db:
        stored = server_settings_crud.get_mail_settings(db)
    assert stored is not None
    return stored


def _audit_rows(committed_sessions) -> list[AuditLog]:
    with committed_sessions() as db:
        rows = list(db.scalars(sa.select(AuditLog).where(AuditLog.action_id == "server_settings.mail.update")))
        db.expunge_all()
    return rows


def _outbox():
    return jasil_testing.memory_mail(jasil_runtime.get_active_platform()).outbox


class TestReadMailSettings:
    def test_a_fresh_install_reports_mail_as_not_configured(self, admin_client):
        response = admin_client.get(MAIL_URL)

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        body = response.json()
        assert body["host"] is None
        assert body["password_set"] is False
        assert body["email_status"] == {"configured": False, "problems": ["Host is not set"]}

    def test_a_stored_password_shows_only_as_a_flag(self, admin_client, committed_sessions):
        with committed_sessions() as db:
            edit_mail_settings(db, **_VALID)
            db.commit()

        response = admin_client.get(MAIL_URL)

        assert response.json()["password_set"] is True
        assert "password" not in response.json()
        assert "s3cret" not in response.text
        assert response.json()["email_status"] == {"configured": True, "problems": []}

    def test_settings_that_cannot_be_used_report_their_problems(self, admin_client, committed_sessions):
        with committed_sessions() as db:
            edit_mail_settings(db, host="smtp.example.org", username=None, from_address=None, password=None)
            db.commit()

        status = admin_client.get(MAIL_URL).json()["email_status"]

        assert status["configured"] is False
        assert status["problems"] == ["A sender address is required (set one, or use an email address as the username)"]

    def test_a_password_that_cannot_be_decrypted_is_reported_and_does_not_block_the_read(
        self, admin_client, committed_sessions
    ):
        with committed_sessions() as db:
            edit_mail_settings(db, **_VALID)
            db.execute(sa.update(server_settings_models.MailSettings).values(password="not-a-token"))
            db.commit()

        response = admin_client.get(MAIL_URL)

        assert response.status_code == 200
        status = response.json()["email_status"]
        assert status["configured"] is False
        assert "cannot be decrypted" in status["problems"][0]

    def test_a_missing_row_is_a_service_error(self, admin_client, committed_sessions):
        with committed_sessions() as db:
            db.execute(sa.delete(server_settings_models.MailSettings))
            db.commit()

        assert admin_client.get(MAIL_URL).status_code == 503


class TestEditMailSettings:
    def test_valid_settings_are_saved_with_the_password_encrypted_and_never_returned(
        self, admin_client, committed_sessions
    ):
        response = _put(admin_client)

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        body = response.json()
        assert (body["host"], body["port"], body["security"]) == ("smtp.example.org", 587, "starttls")
        assert body["password_set"] is True
        assert body["email_status"] == {"configured": True, "problems": []}
        assert "s3cret" not in response.text
        stored = _stored(committed_sessions)
        assert stored.password not in (None, "s3cret")
        assert server_settings_change_utils.decrypt_secret(stored.password, "password") == "s3cret"

    def test_a_save_audits_the_field_names_and_never_the_password(self, admin_client, committed_sessions):
        _put(admin_client)

        (row,) = _audit_rows(committed_sessions)
        assert row.details == {"changed_fields": ["from_address", "host", "password", "username"]}

    def test_a_blank_host_disables_mail_without_validating_the_rest(self, admin_client, committed_sessions):
        _put(admin_client)

        response = _put(admin_client, at=2, host="  ", username=None, from_address=None, password=None)

        assert response.status_code == 200
        assert response.json()["email_status"]["configured"] is False
        assert _stored(committed_sessions).host is None

    def test_an_omitted_password_keeps_the_stored_token(self, admin_client, committed_sessions):
        _put(admin_client)
        token = _stored(committed_sessions).password

        response = _put(admin_client, at=2, without_password=True, port=2525)

        assert response.status_code == 200
        stored = _stored(committed_sessions)
        assert (stored.port, stored.password) == (2525, token)

    def test_re_sending_the_same_password_keeps_the_token_and_the_version(self, admin_client, committed_sessions):
        _put(admin_client)
        token = _stored(committed_sessions).password

        response = _put(admin_client, at=2)

        assert response.headers["ETag"] == '"2"'
        assert _stored(committed_sessions).password == token
        assert len(_audit_rows(committed_sessions)) == 1

    @pytest.mark.parametrize("cleared", [None, ""])
    def test_clearing_the_password_removes_it(self, admin_client, committed_sessions, cleared):
        _put(admin_client)

        response = _put(admin_client, at=2, password=cleared, username=None)

        assert response.status_code == 200
        assert response.json()["password_set"] is False
        assert _stored(committed_sessions).password is None

    @pytest.mark.parametrize(
        ("changes", "problem"),
        [
            ({"from_address": None, "username": None, "password": None}, "A sender address is required"),
            ({"from_address": "not an address"}, "Sender address is not a valid email address"),
            ({"security": "none", "host": "10.0.0.5"}, "Security 'none' cannot be used with a username or password"),
            (
                {"security": "none", "host": "8.8.8.8", "username": None, "password": None},
                "only allowed for a private or loopback host",
            ),
            ({"password": None}, "Username and password must be set together"),
        ],
    )
    def test_an_unusable_configuration_is_a_400_naming_the_problem_and_writes_nothing(
        self, admin_client, committed_sessions, changes, problem
    ):
        response = _put(admin_client, **changes)

        assert response.status_code == 400
        assert problem in response.json()["detail"]
        assert _stored(committed_sessions).version == 1

    def test_the_validation_does_not_hold_the_settings_row_lock(self, admin_client, committed_sessions, dns):
        locked: list[bool] = []

        def try_to_lock(_name: str) -> None:
            with committed_sessions() as other:
                try:
                    other.execute(sa.text("SELECT 1 FROM mail_settings WHERE id = 1 FOR UPDATE NOWAIT"))
                    locked.append(True)
                except sa.exc.OperationalError:
                    locked.append(False)

        dns.on_lookup = try_to_lock

        response = _put(admin_client, security="none", host="mail.example.org", username=None, password=None)

        assert dns.names == ["mail.example.org"]
        assert locked == [True]
        assert response.status_code == 400

    def test_a_password_replaced_during_the_validation_is_refused_and_nothing_is_written(
        self, admin_client, committed_sessions, dns
    ):
        def replace_password(_name: str) -> None:
            with committed_sessions() as other:
                other.execute(sa.update(server_settings_models.MailSettings).values(password="replaced-meanwhile"))
                other.commit()

        dns.on_lookup = replace_password

        response = _put(
            admin_client,
            without_password=True,
            security="none",
            host=INTERNAL_HOST,
            username=None,
            from_address="no-reply@example.org",
        )

        assert response.status_code == 412
        stored = _stored(committed_sessions)
        assert (stored.host, stored.password) == (None, "replaced-meanwhile")

    def test_a_stale_tag_is_refused_and_writes_nothing(self, admin_client, committed_sessions):
        _put(admin_client, port=2525)

        response = _put(admin_client, at=1, port=465, security="ssl")

        assert response.status_code == 412
        assert _stored(committed_sessions).port == 2525

    def test_a_body_without_a_step_up_is_a_422_and_writes_nothing(self, admin_client, committed_sessions):
        response = admin_client.put(MAIL_URL, json=_VALID, headers={"If-Match": '"1"'})

        assert response.status_code == 422
        assert _stored(committed_sessions).version == 1

    def test_a_wrong_password_is_refused_before_anything_is_read_or_written(self, admin_client, committed_sessions):
        response = _put(admin_client, step_up={"current_password": "not-my-password"})

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"
        assert _stored(committed_sessions).version == 1

    def test_a_refused_step_up_is_checked_before_the_tag(self, admin_client):
        response = _put(admin_client, at=9, step_up={"current_password": "not-my-password"})

        assert response.status_code == 403

    @pytest.mark.parametrize("field", ["id", "version", "password_set", "email_status"])
    def test_a_field_the_server_owns_is_a_422(self, admin_client, field):
        response = _put(admin_client, **{field: 3})

        assert response.status_code == 422


class TestMailSettingsReads:
    def test_the_config_other_modules_send_with_has_the_password_decrypted_and_the_username_as_sender(self, db):
        edit_mail_settings(db, host="smtp.example.org", username="mailer@example.org", password="s3cret")

        config = server_settings_integration.get_mail_config(db)

        assert config is not None
        assert (config.host, config.port, config.from_address, config.password) == (
            "smtp.example.org",
            587,
            "mailer@example.org",
            "s3cret",
        )

    def test_an_explicit_sender_wins_over_the_username(self, db):
        edit_mail_settings(db, **_VALID)

        config = server_settings_integration.get_mail_config(db)

        assert config is not None
        assert config.from_address == "no-reply@example.org"

    def test_no_host_means_mail_is_off(self, db):
        assert server_settings_integration.get_mail_config(db) is None
        assert server_settings_integration.is_mail_configured(db) is False

    def test_a_stored_host_means_mail_is_configured_without_validating_it(self, db):
        edit_mail_settings(db, host="smtp.example.org", username=None, from_address=None, password=None)

        assert server_settings_integration.is_mail_configured(db) is True

    def test_a_missing_row_means_mail_is_off(self, db):
        db.execute(sa.delete(server_settings_models.MailSettings))

        assert server_settings_integration.get_mail_config(db) is None
        assert server_settings_integration.is_mail_configured(db) is False

    def test_an_undecryptable_password_is_a_service_error_for_the_sender(self, db):
        edit_mail_settings(db, **_VALID)
        db.execute(sa.update(server_settings_models.MailSettings).values(password="not-a-token"))

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_integration.get_mail_config(db)


class TestSendTestEmail:
    def test_the_mail_goes_to_the_calling_admin_only_and_names_the_server(
        self, admin_client, admin, committed_sessions
    ):
        with committed_sessions() as db:
            edit_mail_settings(db, **_VALID)
            db.commit()

        response = admin_client.post(_TEST_EMAIL_URL)

        assert response.status_code == 204
        (message,) = _outbox()
        assert message.to == [admin.email]
        assert "smtp.example.org:587" in message.text

    def test_unconfigured_mail_is_a_503_with_the_reasons_and_sends_nothing(self, admin_client):
        response = admin_client.post(_TEST_EMAIL_URL)

        assert response.status_code == 503
        assert "Host is not set" in response.json()["detail"]
        assert _outbox() == []

    def test_unusable_settings_are_a_503_with_the_reasons(self, admin_client, committed_sessions):
        with committed_sessions() as db:
            edit_mail_settings(db, host="smtp.example.org", username=None, from_address=None, password=None)
            db.commit()

        response = admin_client.post(_TEST_EMAIL_URL)

        assert response.status_code == 503
        assert "sender address is required" in response.json()["detail"]
        assert _outbox() == []

    def test_a_mail_server_that_refuses_the_message_is_a_502(self, admin_client, committed_sessions, monkeypatch):
        with committed_sessions() as db:
            edit_mail_settings(db, **_VALID)
            db.commit()

        def refuse(_message):
            raise platform_providers.MailError(
                "refused", status=550, kind=platform_providers.MailFailure.SENDER_REFUSED
            )

        monkeypatch.setattr(jasil_testing.memory_mail(jasil_runtime.get_active_platform()), "send", refuse)

        response = admin_client.post(_TEST_EMAIL_URL)

        assert response.status_code == 502
        assert "did not accept the test email" in response.json()["detail"]

    def test_an_admin_who_no_longer_exists_is_not_found(self, db):
        edit_mail_settings(db, **_VALID)

        with pytest.raises(core_exceptions.NotFoundError):
            server_settings_mail_service.send_test_email(uuid.uuid4(), jasil_runtime.get_active_platform().mail, db)
