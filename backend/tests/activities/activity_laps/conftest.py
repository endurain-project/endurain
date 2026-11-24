"""An owner, a follower and a stranger, and the shared activities the package's service and HTTP tests read."""

from collections.abc import Callable
from types import SimpleNamespace

import pytest

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.schema as activity_schema
from tests._factories.activities import make_activity
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user


@pytest.fixture
def people(committed_sessions):
    """An owner, an accepted follower of the owner and a stranger, committed."""
    with committed_sessions() as db:
        owner = make_user(db, timezone="UTC")
        follower = make_user(db, timezone="UTC")
        stranger = make_user(db, timezone="UTC")
        make_follow(db, follower.id, owner.id, accepted=True)
        db.commit()
    return SimpleNamespace(owner=owner, follower=follower, stranger=stranger)


@pytest.fixture
def make_owned_activity(committed_sessions, people) -> Callable[..., activity_schema.ActivityRead]:
    """Return a function that commits one of the owner's activities, with the children its ``stage`` callable adds."""

    def make(
        visibility: activity_constants.ActivityVisibility = activity_constants.ActivityVisibility.PRIVATE,
        stage: Callable[..., object] | None = None,
        **overrides: object,
    ) -> activity_schema.ActivityRead:
        with committed_sessions() as db:
            activity = make_activity(db, people.owner.id, visibility=visibility, **overrides)
            if stage is not None:
                stage(db, activity)
            db.commit()
        return activity

    return make


@pytest.fixture
def public_links(committed_sessions) -> None:
    """Turn public shareable links on for the server."""
    with committed_sessions() as db:
        edit_server_settings(db, public_shareable_links=True)
        db.commit()
