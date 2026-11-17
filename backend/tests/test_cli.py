"""Tests for the operator recovery commands."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.audit as jasil_audit
import pytest

import cli
import core.exceptions as core_exceptions
import modules.auth.credentials.contracts as credentials_contracts

_USER = SimpleNamespace(id=uuid.UUID(int=1))


@pytest.fixture
def db():
    session = MagicMock()
    with patch.object(cli.core_database, "SessionLocal") as factory:
        factory.return_value.__enter__.return_value = session
        yield session


def test_a_reset_turns_off_mfa_commits_and_audits_as_the_command_line(db):
    seen = {}

    def reset(user_id, session):
        seen["context"] = jasil_audit.get_context()
        seen["user_id"] = user_id

    with (
        patch.object(cli.users_integration, "get_user_by_username", return_value=_USER) as lookup,
        patch.object(cli.account_security_integration, "reset_managed_user_mfa", side_effect=reset),
    ):
        code = cli.reset_mfa("alice")

    assert code == 0
    lookup.assert_called_once_with("alice", db)
    assert seen["user_id"] == _USER.id
    assert seen["context"].source == jasil_audit.Source.CLI
    assert seen["context"].actor_type == jasil_audit.ActorType.SYSTEM
    db.commit.assert_called_once()


def test_an_unknown_username_changes_nothing(db):
    with (
        patch.object(cli.users_integration, "get_user_by_username", return_value=None),
        patch.object(cli.account_security_integration, "reset_managed_user_mfa") as reset,
    ):
        code = cli.reset_mfa("nobody")

    assert code == 1
    reset.assert_not_called()
    db.commit.assert_not_called()


def test_an_account_without_mfa_is_reported_and_rolled_back(db):
    with (
        patch.object(cli.users_integration, "get_user_by_username", return_value=_USER),
        patch.object(
            cli.account_security_integration, "reset_managed_user_mfa", side_effect=core_exceptions.ConflictError
        ),
    ):
        code = cli.reset_mfa("alice")

    assert code == 1
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_the_parser_requires_a_command_and_a_username():
    parser = cli.build_parser()

    assert parser.parse_args(["reset-mfa", "alice"]).username == "alice"
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["reset-mfa"])


def _settings(regular=15, admin=15):
    return SimpleNamespace(password_length_regular_users=regular, password_length_admin_users=admin)


def _set_password(db, *, user=_USER, change=None, settings=None):
    user = user and SimpleNamespace(id=user.id, access_type="admin")
    with (
        patch.object(cli.users_integration, "get_user_by_username", return_value=user),
        patch.object(cli.server_settings_integration, "get_server_settings", return_value=settings or _settings()),
        patch.object(cli.account_security_integration, "change_managed_user_password", side_effect=change) as set_,
    ):
        return cli.set_password("alice"), set_


def test_a_generated_password_is_set_audited_committed_and_printed_once(db, capsys):
    seen = {}

    def change(user_id, password, session):
        seen["context"] = jasil_audit.get_context()
        seen["args"] = (user_id, password)

    code, _ = _set_password(db, change=change)

    assert code == 0
    assert seen["context"].source == jasil_audit.Source.CLI
    user_id, password = seen["args"]
    assert user_id == _USER.id
    assert capsys.readouterr().out == f"New password: {password}\n"
    db.commit.assert_called_once()


def test_the_password_follows_the_servers_minimum_for_the_account_type(db):
    seen = []
    _set_password(db, change=lambda _id, password, _db: seen.append(password), settings=_settings(admin=64))

    assert len(seen[0]) == 64


def test_a_password_the_policy_refuses_changes_nothing_and_prints_nothing(db, capsys):
    code, _ = _set_password(db, change=credentials_contracts.PasswordTooShortError("too short"))

    assert code == 1
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    assert capsys.readouterr().out == ""


def test_a_password_for_an_unknown_username_changes_nothing(db, capsys):
    code, change = _set_password(db, user=None)

    assert code == 1
    change.assert_not_called()
    db.commit.assert_not_called()
    assert capsys.readouterr().out == ""


def test_the_password_is_never_a_command_line_argument():
    parser = cli.build_parser()

    assert parser.parse_args(["set-password", "alice"]).command == "set-password"
    with pytest.raises(SystemExit):
        parser.parse_args(["set-password", "alice", "--password", "x"])
