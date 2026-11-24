"""The sleep list's resting heart rate filter, on the real database.

The page and its total must describe the same rows, so a client paging nights with a resting heart rate
never receives a short page or a total that counts nights without one.
"""

from datetime import date

import pytest

import core.date_range as core_date_range
import modules.health.health_sleep.service as sleep_service
from tests._factories.health import make_health_sleep
from tests._factories.users import make_user


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


def test_the_page_and_total_count_only_nights_with_a_resting_heart_rate(db, user, other):
    for day, rate in ((1, 50), (2, None), (3, 52), (4, None), (5, 54)):
        make_health_sleep(db, user.id, date=date(2026, 3, day), resting_heart_rate=rate)
    make_health_sleep(db, other.id, date=date(2026, 3, 1), resting_heart_rate=60)

    page = sleep_service.list_health_sleep(
        user.id, db, page_number=1, num_records=2, date_range=core_date_range.DateRange(), has_resting_heart_rate=True
    )

    assert page.total == 3
    assert [record.resting_heart_rate for record in page.items] == [54, 52]
    assert page.next == 2


def test_without_the_filter_every_night_is_listed(db, user):
    for day, rate in ((1, 50), (2, None)):
        make_health_sleep(db, user.id, date=date(2026, 3, day), resting_heart_rate=rate)

    page = sleep_service.list_health_sleep(user.id, db, date_range=core_date_range.DateRange())

    assert page.total == 2


def test_the_list_flags_the_stages_without_carrying_them(db, user):
    stage = {"stage_type": "deep", "start_time_gmt": "2026-03-01T01:00:00Z", "end_time_gmt": "2026-03-01T02:00:00Z"}
    make_health_sleep(db, user.id, date=date(2026, 3, 1), sleep_stages=[stage])
    make_health_sleep(db, user.id, date=date(2026, 3, 2), sleep_stages=[])
    make_health_sleep(db, user.id, date=date(2026, 3, 3))

    page = sleep_service.list_health_sleep(user.id, db, date_range=core_date_range.DateRange())

    assert [item.has_sleep_stages for item in page.items] == [False, False, True]
    assert all("sleep_stages" not in item.model_dump() for item in page.items)
