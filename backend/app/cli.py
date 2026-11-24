"""Recovery commands an operator runs on the server, outside the API, with the application's own configuration.

``python -m cli reset-mfa USERNAME`` turns off two-step verification for an account and ends its sessions, for the one
case the API cannot serve: an administrator who lost both the authenticator and the backup codes, or whose
two-step sign-in is locked, and has no other administrator to reset it. Run it in the backend directory
(``/app/backend`` in the container). The action is audited with ``source=cli``.

``python -m cli set-password USERNAME`` sets a generated password for an account and prints it once, for an
administrator who forgot theirs on a server with no mail. The password follows the server's minimum length, uses
letters, digits and the symbols ``!@#%+=-`` (no look-alike characters) and never appears in a log. It
ends the account's sessions, revokes its API keys and reset
links, and requires a new password at the next sign-in, as an administrator setting a password does.

A command touches the same database and shared state store as the API. With the in-memory state store the API keeps
its own lock counters in its own process; the account has no second factor after the reset, and setting two-step
verification up again forgets the lock.
"""

import argparse
import sys
from collections.abc import Sequence

import jasil.audit as jasil_audit
import jasil.container as platform_container
import jasil.lifecycle as jasil_lifecycle
import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.platform_settings as core_platform_settings
import model_registry as orm_model_registry
import module_registry as runtime_module_registry
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.credentials.integration_service as credentials_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def _start_platform() -> None:
    """Build the platform substrate the way the worker does, so the command reads the same database and state."""
    orm_model_registry.import_all_models()
    substrate_settings = core_platform_settings.build_jasil_settings(
        core_config.settings,
        plain_areas=runtime_module_registry.storage_plain_areas(),
    )
    jasil_settings.configure(substrate_settings)
    platform = platform_container.build_platform(substrate_settings, sources=runtime_module_registry.runtime_sources())
    platform_runtime.set_active_platform(platform)
    runtime_module_registry.configure_application()


def reset_mfa(username: str) -> int:
    """Turn off two-step verification for an account and end its sessions.

    Args:
        username: The account's username.

    Returns:
        The process exit code: 0 when the reset was made, 1 when the account does not exist or has no two-step
        verification.
    """
    with core_database.SessionLocal() as db:
        user = users_integration.get_user_by_username(username, db)
        if user is None:
            logger.error("No account has that username", extra=core_logger.context(console=True))
            return 1
        with jasil_audit.audit_context(actor_type=jasil_audit.ActorType.SYSTEM, source=jasil_audit.Source.CLI):
            try:
                account_security_integration.reset_managed_user_mfa(user.id, db)
            except core_exceptions.ConflictError:
                db.rollback()
                logger.error(
                    "Two-step verification is not turned on for that account", extra=core_logger.context(console=True)
                )
                return 1
            db.commit()
    logger.info(
        "Two-step verification is off and every session of the account has ended",
        extra=core_logger.context(console=True, user_id=user.id),
    )
    return 0


def set_password(username: str) -> int:
    """Set a generated password for an account, the way an administrator setting it does, and print it once.

    The password has the length the server's settings require for the account's type (at least 24 characters) and
    uses letters, digits and the symbols ``!@#%+=-``, without look-alike characters. The
    account's sessions end, and it must choose a new
    password at the next sign-in.

    Args:
        username: The account's username.

    Returns:
        The process exit code: 0 when the password was set, 1 when the account does not exist.
    """
    with core_database.SessionLocal() as db:
        user = users_integration.get_user_by_username(username, db)
        if user is None:
            logger.error("No account has that username", extra=core_logger.context(console=True))
            return 1
        password = credentials_integration.generate_password_for_access_type(
            server_settings_integration.get_server_settings(db), users_schema.normalize_access_type(user.access_type)
        )
        with jasil_audit.audit_context(actor_type=jasil_audit.ActorType.SYSTEM, source=jasil_audit.Source.CLI):
            account_security_integration.change_managed_user_password(user.id, password, db)
            db.commit()
    logger.info(
        "The password is set, every session of the account has ended and a new password is required at sign-in",
        extra=core_logger.context(console=True, user_id=user.id),
    )
    # Written to the terminal only: a log line would keep the password in the log files.
    sys.stdout.write(f"New password: {password}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser.

    Returns:
        The parser, with one sub-command per recovery action.
    """
    parser = argparse.ArgumentParser(prog="python -m cli", description="Endurain recovery commands.")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-mfa", help="Turn off two-step verification for an account.")
    reset.add_argument("username", help="The account's username.")
    password = commands.add_parser("set-password", help="Set a generated password and print it once.")
    password.add_argument("username", help="The account's username.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the environment, start the platform and run one command.

    Args:
        argv: The arguments after the program name; ``None`` reads them from the command line.

    Returns:
        The process exit code.
    """
    args = build_parser().parse_args(argv)
    core_config.check_required_env_vars()
    core_config.check_required_dirs()
    core_logger.setup_main_logger()
    _start_platform()
    try:
        if args.command == "set-password":
            return set_password(args.username)
        return reset_mfa(args.username)
    finally:
        jasil_lifecycle.shutdown()


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    sys.exit(main())
