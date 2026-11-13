"""Tests for migration write orchestration."""

from unittest.mock import MagicMock, patch

import migrations.service as migrations_service


def test_mark_executed_commits_the_staged_migration():
    db = MagicMock()
    result = MagicMock()

    with patch("migrations.service.migrations_crud.set_migration_as_executed", return_value=result) as stage:
        assert migrations_service.mark_executed(4, db) is result

    stage.assert_called_once_with(4, db)
    db.commit.assert_called_once_with()
