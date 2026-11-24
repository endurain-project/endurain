"""Reading back what an SSO flow left in the database."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import modules.auth.identity_provider_links.models as links_models
import modules.users.users.models as users_models
from tests._factories.users import audit_rows_of


def users_by_email(sessions: sessionmaker[Session], email: str) -> list[users_models.Users]:
    """Return the accounts that hold an email address."""
    with sessions() as db:
        return list(db.scalars(select(users_models.Users).where(users_models.Users.email == email)))


def links_of(sessions: sessionmaker[Session], idp_id: uuid.UUID | None = None) -> list[links_models.IdentityLink]:
    """Return the links to a provider, or every link."""
    with sessions() as db:
        statement = select(links_models.IdentityLink)
        if idp_id is not None:
            statement = statement.where(links_models.IdentityLink.idp_id == idp_id)
        return list(db.scalars(statement))


def audit(sessions: sessionmaker[Session], *action_ids: str) -> list:
    """Return the committed audit rows of the actions, oldest first."""
    with sessions() as db:
        return audit_rows_of(db, *action_ids)


def wait_until_a_session_waits_for_a_lock(factory: sessionmaker[Session], timeout: float = 10.0) -> None:
    """Block until another session of this database waits on a lock, so a test acts at that exact point."""
    import threading
    import time

    from sqlalchemy import text

    deadline = time.monotonic() + timeout
    with factory() as probe:
        while time.monotonic() < deadline:
            waiting = probe.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
            )
            if waiting:
                return
            # PostgreSQL reads pg_stat_activity once per transaction, so each poll needs a transaction of its own.
            probe.rollback()
            # A poll of the database's own state, not a wait for time to pass: it ends the moment the lock wait shows.
            threading.Event().wait(0.02)
    raise AssertionError("no session waited for a lock")
