"""Tests for migration tracking persistence."""

from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import migrations.crud as migrations_crud
import migrations.models as migrations_models


def test_marking_executed_stages_and_refreshes_without_committing():
    db = MagicMock()
    row = migrations_models.Migration(id=4, name="four", description="fourth", executed=False)
    db.execute.return_value.scalar_one_or_none.return_value = row

    result = migrations_crud.set_migration_as_executed(4, db)

    assert result.id == 4
    assert row.executed is True
    db.flush.assert_called_once_with()
    db.refresh.assert_called_once_with(row)
    db.commit.assert_not_called()


def test_marking_a_missing_migration_raises_not_found():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    with pytest.raises(core_exceptions.NotFoundError, match="Migration not found"):
        migrations_crud.set_migration_as_executed(4, db)

    db.commit.assert_not_called()
