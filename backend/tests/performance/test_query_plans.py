"""The hot reads are served by an index: with sequential scans switched off, no plan still scans a large table.

With ``enable_seqscan = off`` the planner takes a sequential scan only when no index can serve the table at all, so a
remaining ``Seq Scan`` names a query whose table needs an index.
"""

import json
from collections.abc import Callable, Iterator, Mapping

import pytest
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import modules.users.users.schema as users_schema
from tests._factories import followers as follower_factories
from tests._factories.auth import make_session
from tests._factories.users import make_user
from tests.performance import _support as support

_ROOT = core_config.ROOT_PATH

#: Rows seeded for the signed-in user and, again, for a second user, so that the user's own rows are selective.
_ROWS = 250

#: The tables that grow with use; a sequential scan of one of them is a missing index.
_LARGE_TABLES = frozenset(
    {
        "activities",
        "activities_streams",
        "activity_laps",
        "activity_sets",
        "activity_workout_steps",
        "activity_media",
        "activity_deletions",
        "activity_ingestion_jobs",
        "health_weight",
        "health_steps",
        "health_water",
        "health_sleep",
        "health_poop",
        "health_fasting",
        "health_targets",
        "health_record_deletions",
        "gear",
        "gear_components",
        "gear_deletions",
        "gear_component_deletions",
        "notifications",
        "followers",
        "users_sessions",
    }
)

#: Arranges ``rows`` of one user's data and returns the ids a URL may name, besides ``{user_id}``.
Arrange = Callable[[Session, users_schema.UserRead, int], Mapping[str, object]]


def _activities(db: Session, user: users_schema.UserRead, rows: int) -> None:
    gear = support.arrange_gears(db, user.id, 1, components=1)[0]
    support.arrange_activities(db, user.id, rows, with_gear=gear)
    return {}


def _activity_children(db: Session, user: users_schema.UserRead, rows: int) -> None:
    activity_ids = support.arrange_activities(db, user.id, 8, children=rows // 8)
    return {"activity_id": activity_ids[0]}


def _followed_feed(db: Session, user: users_schema.UserRead, rows: int) -> None:
    support.arrange_followed_feed(db, user, followees=rows // 10, per_followee=10)
    return {}


def _followers(db: Session, user: users_schema.UserRead, rows: int) -> None:
    for _ in range(rows):
        follower_factories.make_follow(db, make_user(db).id, user.id, accepted=True)
    return {}


def _weights(db: Session, user: users_schema.UserRead, rows: int) -> None:
    support.arrange_weights(db, user.id, rows)
    support.arrange_dashboard(db, user.id, 3)
    return {}


def _gears(db: Session, user: users_schema.UserRead, rows: int) -> None:
    support.arrange_gears(db, user.id, rows, components=1)
    return {}


def _notifications(db: Session, user: users_schema.UserRead, rows: int) -> None:
    support.arrange_notifications(db, user.id, rows)
    return {}


def _sessions(db: Session, user: users_schema.UserRead, rows: int) -> None:
    for _ in range(rows):
        make_session(db, user)
    return {}


def _jobs(db: Session, user: users_schema.UserRead, rows: int) -> None:
    support.arrange_jobs(db, user.id, rows)
    return {}


def _syncable(db: Session, user: users_schema.UserRead, rows: int) -> None:
    support.arrange_syncable(db, user.id, rows)
    return {}


#: What each case seeds, the rows it seeds and the URLs whose statements are planned.
_CASES: dict[str, tuple[Arrange, int, tuple[str, ...]]] = {
    "activity list": (
        _activities,
        _ROWS,
        (
            f"{_ROOT}/activities?num_records=50",
            f"{_ROOT}/activities?num_records=50&page_number=2&sort_by=start_time&sort_order=desc",
            f"{_ROOT}/activities?activity_type=run&start_date=2025-01-01&end_date=2030-01-01&sort_by=distance",
            f"{_ROOT}/activities?name_contains=Run%201",
            f"{_ROOT}/activities/types",
        ),
    ),
    "own feed": (_activities, _ROWS, (f"{_ROOT}/activities/feed?scope=mine&num_records=20",)),
    "followed feed": (_followed_feed, _ROWS, (f"{_ROOT}/activities/feed?num_records=20",)),
    "activity children": (
        _activity_children,
        _ROWS,
        (
            f"{_ROOT}/activities/{{activity_id}}",
            f"{_ROOT}/activities/{{activity_id}}/detail",
            f"{_ROOT}/activities/{{activity_id}}/laps?num_records=50",
            f"{_ROOT}/activities/{{activity_id}}/sets?num_records=50",
            f"{_ROOT}/activities/{{activity_id}}/workout-steps?num_records=50",
            f"{_ROOT}/activities/{{activity_id}}/media?num_records=50",
            f"{_ROOT}/activities/{{activity_id}}/streams",
        ),
    ),
    "followers": (_followers, _ROWS, (f"{_ROOT}/users/{{user_id}}/followers?num_records=50",)),
    "health weight": (
        _weights,
        _ROWS,
        (
            f"{_ROOT}/health/weight?num_records=50",
            f"{_ROOT}/health/weight?start_date=2025-01-01&end_date=2100-01-01&num_records=50",
            f"{_ROOT}/health/stats/daily",
        ),
    ),
    "gears": (
        _gears,
        _ROWS,
        (
            f"{_ROOT}/gears?num_records=50",
            f"{_ROOT}/gears?active=true&gear_type=bike&nickname_contains=Bike",
            f"{_ROOT}/gear-components?num_records=50",
        ),
    ),
    "notifications": (
        _notifications,
        _ROWS,
        (f"{_ROOT}/notifications?num_records=50", f"{_ROOT}/notifications?num_records=50&unread_only=true"),
    ),
    "sessions": (_sessions, _ROWS, (f"{_ROOT}/profile/sessions?num_records=50",)),
    "ingestion jobs": (_jobs, _ROWS, (f"{_ROOT}/jobs?num_records=50",)),
    "sync": (_syncable, _ROWS, (f"{_ROOT}/sync",)),
}


def _seq_scans(plan: dict) -> Iterator[dict]:
    """Yield every sequential scan node of a plan tree."""
    if plan["Node Type"] == "Seq Scan":
        yield plan
    for child in plan.get("Plans", []):
        yield from _seq_scans(child)


def _explained_without_seq_scans(statement: str, parameters: object) -> dict:
    """Plan one statement with its values on a connection where sequential scans are off."""
    with core_database.engine.connect() as connection:
        connection.exec_driver_sql("SET LOCAL enable_seqscan = off")
        rows = connection.exec_driver_sql(f"EXPLAIN (FORMAT JSON) {statement}", parameters).scalar_one()
    return rows[0]["Plan"] if isinstance(rows, list) else json.loads(rows)[0]["Plan"]


def _analyze() -> None:
    """Refresh the planner statistics of the seeded tables."""
    with core_database.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql("ANALYZE")


@pytest.mark.parametrize("case", _CASES.values(), ids=_CASES.keys())
def test_no_hot_query_scans_a_large_table_sequentially(committed_sessions, sign_in, case):
    arrange, rows, urls = case
    with committed_sessions() as db:
        user = make_user(db)
        ids = arrange(db, user, rows)
        arrange(db, make_user(db), rows)
        db.commit()
    _analyze()
    client = sign_in(user).client

    scans: list[str] = []
    for url in urls:
        url = url.format(user_id=user.id, **ids)
        assert client.get(url).status_code == 200, url
        with support.captured_statements() as seen:
            assert client.get(url).status_code == 200, url
        for statement in seen:
            if not statement.statement.lstrip().upper().startswith(("SELECT", "WITH")):
                continue
            plan = _explained_without_seq_scans(statement.statement, statement.parameters)
            scans.extend(
                f"{url}: Seq Scan on {node['Relation Name']} filter={node.get('Filter')}\n    {statement.shape[:600]}"
                for node in _seq_scans(plan)
                if node["Relation Name"] in _LARGE_TABLES
            )

    assert not scans, "\n".join(scans)
