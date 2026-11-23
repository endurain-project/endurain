"""The operator recovery commands, run against the real database."""

import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings
import jasil.testing as jasil_testing
import pytest
from jasil.audit.models import AuditLog
from sqlalchemy import select

import cli
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.contributor_registry as users_contributor_registry
from tests._factories.tokens import make_mfa
from tests._factories.users import PASSWORD, make_user


def _audit(committed_sessions, action_id: str) -> list[AuditLog]:
    with committed_sessions() as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action_id == action_id)))


def _session_survives(committed_sessions, signed_in) -> bool:
    with committed_sessions() as db:
        return sessions_integration.get_session_by_id_not_expired(signed_in.session_id, db) is not None


@pytest.fixture
def alice(committed_sessions, sign_in):
    """An administrator with two-step verification on and an open session."""
    with committed_sessions() as db:
        user = make_user(db, username="alice")
        make_mfa(db, user)
        db.commit()
    return sign_in(user)


def _printed_password(out: str) -> str | None:
    """The password the command wrote to the terminal, apart from the log lines the process also writes there."""
    for line in out.splitlines():
        if line.startswith("New password: "):
            return line.removeprefix("New password: ")
    return None


@pytest.fixture
def run_command(app, committed_sessions):
    """Run ``cli.main`` as a fresh process does, then give the test its own platform and settings back.

    The command builds and publishes its own platform and releases it on exit, so the registrations the harness made
    are cleared first and what the test had published is restored afterwards, for a request or a sign-in after it.
    """
    platform = platform_runtime.get_active_platform()
    settings = jasil_settings.get_settings()

    def run(argv: list[str]) -> int:
        jasil_testing.reset_all()
        users_contributor_registry.clear()
        try:
            return cli.main(argv)
        finally:
            assert not platform_runtime.is_platform_active()
            jasil_settings.configure(settings)
            platform_runtime.set_active_platform(platform)

    return run


class TestMain:
    def test_set_password_starts_the_platform_sets_a_password_that_signs_in_and_releases_it(
        self, run_command, client, committed_sessions, alice, capsys
    ):
        assert run_command(["set-password", "alice"]) == 0

        out = capsys.readouterr().out
        password = _printed_password(out)
        assert password
        assert out.count(password) == 1
        assert not _session_survives(committed_sessions, alice)
        (row,) = _audit(committed_sessions, "auth.password.set")
        assert (row.source, row.actor_type) == ("cli", "system")
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "alice", "password": password},
            headers={"X-Client-Type": "web"},
        )
        assert response.status_code == 200, response.text

    def test_reset_mfa_starts_the_platform_turns_off_mfa_and_ends_the_sessions(
        self, run_command, committed_sessions, alice
    ):
        assert run_command(["reset-mfa", "alice"]) == 0

        with committed_sessions() as db:
            assert mfa_integration.is_mfa_enabled_for_user(alice.user.id, db) is False
        assert not _session_survives(committed_sessions, alice)
        (row,) = _audit(committed_sessions, "auth.mfa.reset")
        assert (row.source, row.actor_type, row.target_id) == ("cli", "system", str(alice.user.id))

    @pytest.mark.parametrize("command", ["set-password", "reset-mfa"])
    def test_an_unknown_username_exits_with_one_and_releases_the_platform(
        self, run_command, committed_sessions, alice, capsys, command
    ):
        assert run_command([command, "nobody"]) == 1

        assert _printed_password(capsys.readouterr().out) is None
        assert _session_survives(committed_sessions, alice)
        assert _audit(committed_sessions, "auth.password.set") == []
        assert _audit(committed_sessions, "auth.mfa.reset") == []

    def test_a_missing_command_is_refused_before_anything_starts(self, run_command):
        with pytest.raises(SystemExit) as exit_info:
            run_command([])

        assert exit_info.value.code == 2


class TestResetMfa:
    def test_a_reset_turns_off_mfa_ends_the_sessions_and_audits_as_the_command_line(self, committed_sessions, alice):
        assert cli.reset_mfa("alice") == 0

        with committed_sessions() as db:
            assert mfa_integration.is_mfa_enabled_for_user(alice.user.id, db) is False
        assert not _session_survives(committed_sessions, alice)
        (row,) = _audit(committed_sessions, "auth.mfa.reset")
        assert (row.source, row.actor_type, row.target_id) == ("cli", "system", str(alice.user.id))

    def test_an_unknown_username_changes_nothing(self, committed_sessions, alice):
        assert cli.reset_mfa("nobody") == 1

        with committed_sessions() as db:
            assert mfa_integration.is_mfa_enabled_for_user(alice.user.id, db) is True
        assert _session_survives(committed_sessions, alice)
        assert _audit(committed_sessions, "auth.mfa.reset") == []

    def test_an_account_without_mfa_is_reported_and_keeps_its_sessions(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db, username="bob")
            db.commit()
        signed_in = sign_in(user)

        assert cli.reset_mfa("bob") == 1

        assert _session_survives(committed_sessions, signed_in)
        assert _audit(committed_sessions, "auth.mfa.reset") == []


class TestSetPassword:
    def test_a_generated_password_is_set_audited_and_printed_once(self, committed_sessions, alice, capsys):
        assert cli.set_password("alice") == 0

        printed = capsys.readouterr().out
        assert printed.startswith("New password: ")
        password = printed.removeprefix("New password: ").strip()
        assert password != PASSWORD
        with committed_sessions() as db:
            assert credentials_integration.is_password_change_required(alice.user.id, db) is True
        assert not _session_survives(committed_sessions, alice)
        (row,) = _audit(committed_sessions, "auth.password.set")
        assert (row.source, row.actor_type) == ("cli", "system")
        assert password not in str(row.details)

    def test_the_new_password_signs_the_account_in(self, client, committed_sessions, alice, capsys):
        cli.set_password("alice")
        password = capsys.readouterr().out.removeprefix("New password: ").strip()

        response = client.post(
            "/api/v1/auth/login",
            data={"username": "alice", "password": password},
            headers={"X-Client-Type": "web"},
        )

        assert response.status_code == 200, response.text

    def test_the_password_follows_the_servers_minimum_for_the_account_type(self, committed_sessions, alice, capsys):
        from tests._factories.server_settings import edit_server_settings

        with committed_sessions() as db:
            edit_server_settings(db, password_length_regular_users=64, password_length_admin_users=64)
            db.commit()

        cli.set_password("alice")

        assert len(capsys.readouterr().out.removeprefix("New password: ").strip()) == 64

    def test_an_unknown_username_changes_nothing_and_prints_nothing(self, committed_sessions, alice, capsys):
        assert cli.set_password("nobody") == 1

        assert capsys.readouterr().out == ""
        assert _session_survives(committed_sessions, alice)
        assert _audit(committed_sessions, "auth.password.set") == []


def test_the_parser_requires_a_command_and_a_username():
    parser = cli.build_parser()

    assert parser.parse_args(["reset-mfa", "alice"]).username == "alice"
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["reset-mfa"])


def test_the_password_is_never_a_command_line_argument():
    parser = cli.build_parser()

    assert parser.parse_args(["set-password", "alice"]).command == "set-password"
    with pytest.raises(SystemExit):
        parser.parse_args(["set-password", "alice", "--password", "x"])
