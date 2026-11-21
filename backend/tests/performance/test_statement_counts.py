"""A request sends as many SQL statements for a large dataset as for a small one: no route queries once per row."""

from collections import Counter
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

import core.config as core_config
import modules.users.users.schema as users_schema
from tests._factories import followers as follower_factories
from tests._factories.auth import make_session
from tests._factories.users import make_user
from tests.performance import _support as support

_ROOT = core_config.ROOT_PATH
_SMALL = 2
_LARGE = 12

#: Arranges a user's data of a given size and returns the URL to request.
Arrange = Callable[[Session, users_schema.UserRead, int], str]


def _activity_list(db: Session, user: users_schema.UserRead, size: int) -> str:
    gear = support.arrange_gears(db, user.id, 1, components=0)[0]
    support.arrange_activities(db, user.id, size, with_gear=gear)
    return f"{_ROOT}/activities?num_records=100&sort_by=start_time&sort_order=desc"


def _activity_list_filtered(db: Session, user: users_schema.UserRead, size: int) -> str:
    gear = support.arrange_gears(db, user.id, 1, components=0)[0]
    support.arrange_activities(db, user.id, size, with_gear=gear)
    return (
        f"{_ROOT}/activities?num_records=100&activity_type=run&name_contains=Run&gear_id={gear}&start_date=2025-01-01"
    )


def _followed_feed(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_followed_feed(db, user, followees=size, per_followee=2)
    return f"{_ROOT}/activities/feed?num_records=100"


def _own_feed(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_activities(db, user.id, size)
    return f"{_ROOT}/activities/feed?scope=mine&num_records=100"


def _activity_types(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_activities(db, user.id, size, children=0)
    return f"{_ROOT}/activities/types"


def _child_route(suffix: str) -> Arrange:
    def arrange(db: Session, user: users_schema.UserRead, size: int) -> str:
        activity_id = support.arrange_activities(db, user.id, 1, children=size)[0]
        return f"{_ROOT}/activities/{activity_id}{suffix}"

    return arrange


def _weights(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_weights(db, user.id, size)
    return f"{_ROOT}/health/weight?num_records=100"


def _weights_in_range(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_weights(db, user.id, size)
    return f"{_ROOT}/health/weight?num_records=100&start_date=2020-01-01&end_date=2100-01-01"


def _dashboard(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_dashboard(db, user.id, size)
    return f"{_ROOT}/health/stats/daily"


def _gears(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_gears(db, user.id, size)
    return f"{_ROOT}/gears?num_records=100"


def _gear_detail(db: Session, user: users_schema.UserRead, size: int) -> str:
    gear = support.arrange_gears(db, user.id, 1, components=size)[0]
    return f"{_ROOT}/gears/{gear}"


def _gear_components_of_gear(db: Session, user: users_schema.UserRead, size: int) -> str:
    gear = support.arrange_gears(db, user.id, 1, components=size)[0]
    return f"{_ROOT}/gears/{gear}/components"


def _gear_components(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_gears(db, user.id, size, components=2)
    return f"{_ROOT}/gear-components?num_records=100"


def _notifications(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_notifications(db, user.id, size)
    return f"{_ROOT}/notifications?num_records=100"


def _followers(db: Session, user: users_schema.UserRead, size: int) -> str:
    for _ in range(size):
        follower = make_user(db)
        follower_factories.make_follow(db, follower.id, user.id, accepted=True)
    return f"{_ROOT}/users/{user.id}/followers?num_records=100"


def _sessions(db: Session, user: users_schema.UserRead, size: int) -> str:
    for _ in range(size):
        make_session(db, user)
    return f"{_ROOT}/profile/sessions?num_records=100"


def _jobs(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_jobs(db, user.id, size)
    return f"{_ROOT}/jobs?num_records=100"


def _sync(db: Session, user: users_schema.UserRead, size: int) -> str:
    support.arrange_syncable(db, user.id, size)
    return f"{_ROOT}/sync"


_CASES: dict[str, Arrange] = {
    "activity list": _activity_list,
    "activity list with filters": _activity_list_filtered,
    "followed feed": _followed_feed,
    "own feed": _own_feed,
    "activity types": _activity_types,
    "activity detail": _child_route(""),
    "activity detail view": _child_route("/detail"),
    "activity laps": _child_route("/laps"),
    "activity streams": _child_route("/streams"),
    "activity sets": _child_route("/sets"),
    "activity workout steps": _child_route("/workout-steps"),
    "activity media": _child_route("/media"),
    "health weight list": _weights,
    "health weight list in a date range": _weights_in_range,
    "health dashboard": _dashboard,
    "gears": _gears,
    "gear detail": _gear_detail,
    "components of a gear": _gear_components_of_gear,
    "gear components": _gear_components,
    "notifications": _notifications,
    "followers": _followers,
    "sessions": _sessions,
    "ingestion jobs": _jobs,
    "sync": _sync,
}


def _statements_sent(committed_sessions, sign_in, arrange: Arrange, size: int) -> Counter[str]:
    """Arrange a new user's data at ``size`` and count the statements one request for it sends, by statement shape."""
    with committed_sessions() as db:
        user = make_user(db)
        url = arrange(db, user, size)
        db.commit()
    client = sign_in(user).client
    # The first request fills process-wide caches that a second one finds filled.
    assert client.get(url).status_code == 200
    with support.captured_statements() as seen:
        response = client.get(url)
    assert response.status_code == 200
    return Counter(statement.shape for statement in seen)


@pytest.mark.parametrize("arrange", _CASES.values(), ids=_CASES.keys())
def test_the_statement_count_does_not_grow_with_the_data(committed_sessions, sign_in, arrange):
    small = _statements_sent(committed_sessions, sign_in, arrange, _SMALL)
    large = _statements_sent(committed_sessions, sign_in, arrange, _LARGE)

    assert large.total() == small.total(), {
        "small": small.total(),
        "large": large.total(),
        "grew": dict(large - small),
    }
