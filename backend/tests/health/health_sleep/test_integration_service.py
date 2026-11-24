"""What other modules read from the sleep records: the sync feed and its deletions."""

from datetime import UTC, datetime, timedelta

import pytest

import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.integration_service as health_sleep_integration
from tests._factories.health import make_health_sleep
from tests._factories.users import make_user


@pytest.fixture
def user(db):
    return make_user(db)


def _horizon():
    return datetime.now(UTC) + timedelta(minutes=5)


class TestSyncFeed:
    def test_the_records_changed_since_a_position_come_oldest_change_first_and_only_the_users(self, db, user):
        other = make_user(db)
        first = make_health_sleep(db, user.id)
        make_health_sleep(db, other.id)

        changed = health_sleep_integration.list_changed_health_sleep(user.id, None, _horizon(), 10, db)

        assert [r.id for r in changed] == [first.id]

    def test_a_deleted_record_appears_in_the_deletions_feed(self, db, user):
        record = make_health_sleep(db, user.id)
        health_sleep_crud.delete_health_sleep(user.id, record.id, db, if_match='"1"')

        deletions = health_sleep_integration.list_health_sleep_deletions(user.id, None, _horizon(), 10, db)

        assert [(d.type, d.record_id) for d in deletions] == [("health_sleep", record.id)]
