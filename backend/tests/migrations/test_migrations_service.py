"""Migration write orchestration: the tracking change is committed."""

import migrations.models as migrations_models
import migrations.service as migrations_service
from tests._factories.migrations import make_migration


def test_marking_executed_commits_the_change(committed_sessions):
    with committed_sessions() as db:
        make_migration(db, 4)
        db.commit()

    with committed_sessions() as db:
        assert migrations_service.mark_executed(4, db).executed is True

    with committed_sessions() as db:
        assert db.get(migrations_models.Migration, 4).executed is True
