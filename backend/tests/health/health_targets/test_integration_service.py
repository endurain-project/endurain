"""What other modules read from the health targets: the archive section and the sync feed."""

from datetime import UTC, datetime, timedelta

import pytest

import modules.health.health_targets.integration_service as health_targets_integration
import modules.health.health_targets.schema as health_targets_schema
from tests._factories.users import make_user


@pytest.fixture
def user(db):
    return make_user(db)


def _horizon():
    return datetime.now(UTC) + timedelta(minutes=5)


class TestProfileSection:
    def test_the_section_exports_the_users_targets_and_restores_archived_ones_over_them(self, db, user):
        section = health_targets_integration.profile_section()

        exported = section.export(user.id, db)
        restored = section.restore([{"steps": 7000}], user.id, {}, db)

        assert (section.key, [t.user_id for t in exported], restored) == ("health_targets", [user.id], 1)
        assert health_targets_integration.get_health_targets(user.id, db).steps == 7000


class TestSyncFeed:
    def test_the_targets_changed_since_a_position_are_listed(self, db, user):
        changed = health_targets_integration.list_changed_health_targets(user.id, None, _horizon(), 10, db)

        assert [t.user_id for t in changed] == [user.id]

    def test_no_deletion_is_listed_for_a_user_whose_targets_were_never_deleted(self, db, user):
        assert health_targets_integration.list_health_targets_deletions(user.id, None, _horizon(), 10, db) == []

    def test_a_new_account_gets_empty_targets_from_the_integration(self, db):
        assert isinstance(
            health_targets_integration.get_health_targets(make_user(db).id, db), health_targets_schema.HealthTargetsRead
        )
