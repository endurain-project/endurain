"""The sleep list's resting heart rate filter against real PostgreSQL.

The page and its total must describe the same rows, so a client paging nights with a resting heart rate
never receives a short page or a total that counts nights without one.
"""

import uuid
from datetime import date

import pytest

import core.date_range as core_date_range
import modules.health.health_sleep.models as sleep_models
import modules.health.health_sleep.service as sleep_service
from tests._helpers.db import ensure_user

_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_OTHER_USER_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def db(pg_factory):
    for user_id in (_USER_ID, _OTHER_USER_ID):
        ensure_user(pg_factory, user_id)
    with pg_factory() as session:
        yield session


def test_the_page_and_total_count_only_nights_with_a_resting_heart_rate(db):
    db.add_all(
        sleep_models.HealthSleep(user_id=_USER_ID, date=date(2026, 3, day), resting_heart_rate=rate)
        for day, rate in ((1, 50), (2, None), (3, 52), (4, None), (5, 54))
    )
    db.add(sleep_models.HealthSleep(user_id=_OTHER_USER_ID, date=date(2026, 3, 1), resting_heart_rate=60))
    db.commit()

    page = sleep_service.list_health_sleep(
        _USER_ID, db, page_number=1, num_records=2, date_range=core_date_range.DateRange(), has_resting_heart_rate=True
    )

    assert page.total == 3
    assert [record.resting_heart_rate for record in page.items] == [54, 52]
    assert page.next == 2


def test_without_the_filter_every_night_is_listed(db):
    db.add_all(
        sleep_models.HealthSleep(user_id=_USER_ID, date=date(2026, 3, day), resting_heart_rate=rate)
        for day, rate in ((1, 50), (2, None))
    )
    db.commit()

    page = sleep_service.list_health_sleep(_USER_ID, db, date_range=core_date_range.DateRange())

    assert page.total == 2


def test_the_list_flags_the_stages_without_carrying_them(db):
    db.add_all(
        [
            sleep_models.HealthSleep(
                user_id=_USER_ID, date=date(2026, 3, 1), sleep_stages=[{"stage_type": "deep", "duration_seconds": 60}]
            ),
            sleep_models.HealthSleep(user_id=_USER_ID, date=date(2026, 3, 2), sleep_stages=[]),
            sleep_models.HealthSleep(user_id=_USER_ID, date=date(2026, 3, 3)),
        ]
    )
    db.commit()

    page = sleep_service.list_health_sleep(_USER_ID, db, date_range=core_date_range.DateRange())

    assert [item.has_sleep_stages for item in page.items] == [False, False, True]
    assert all("sleep_stages" not in item.model_dump() for item in page.items)
