"""A signed-in user and the public-links switch the exercise-title routes are read with."""

import pytest

from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user


@pytest.fixture
def me(committed_sessions, sign_in):
    """A user signed in to the production application."""
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    return sign_in(user)


@pytest.fixture
def public_links(committed_sessions) -> None:
    """Turn public shareable links on for the server."""
    with committed_sessions() as db:
        edit_server_settings(db, public_shareable_links=True)
        db.commit()
