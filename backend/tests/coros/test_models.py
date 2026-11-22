"""Model-level checks for the COROS tables and activity identifier."""

from __future__ import annotations

import uuid

import modules.activities.activity.models as activity_models
import modules.coros.models as coros_models


class TestCorosIntegrationModel:
    """The connection row has the identity and uniqueness the service expects."""

    def test_user_is_unique(self):
        table = coros_models.CorosIntegration.__table__
        index = next(index for index in table.indexes if index.name == "ix_coros_integrations_user_id")
        assert index.unique is True

    def test_state_is_unique(self):
        table = coros_models.CorosIntegration.__table__
        index = next(index for index in table.indexes if index.name == "ix_coros_integrations_state")
        assert index.unique is True

    def test_tokens_are_large_text_columns(self):
        columns = coros_models.CorosIntegration.__table__.columns
        assert columns["access_token"].type.length is None
        assert columns["refresh_token"].type.length is None

    def test_ids_are_uuids(self):
        columns = coros_models.CorosIntegration.__table__.columns
        assert columns["id"].type.python_type is uuid.UUID
        assert columns["user_id"].type.python_type is uuid.UUID

    def test_activity_carries_the_coros_identifier(self):
        assert "coros_activity_id" in activity_models.Activity.__table__.columns


class TestSkippedActivityModel:
    """A user cannot have the same activity marked skipped twice."""

    def test_user_and_label_are_unique_together(self):
        constraints = coros_models.CorosSkippedActivity.__table__.constraints
        names = {constraint.name for constraint in constraints}
        assert "uq_coros_skipped_activities_user_label" in names

    def test_ids_are_uuids(self):
        columns = coros_models.CorosSkippedActivity.__table__.columns
        assert columns["id"].type.python_type is uuid.UUID
        assert columns["user_id"].type.python_type is uuid.UUID


class TestImportedActivityModel:
    """A user cannot have the same activity marked complete twice."""

    def test_user_and_label_are_unique_together(self):
        constraints = coros_models.CorosImportedActivity.__table__.constraints
        names = {constraint.name for constraint in constraints}
        assert "uq_coros_imported_activities_user_label" in names

    def test_ids_are_uuids(self):
        columns = coros_models.CorosImportedActivity.__table__.columns
        assert columns["id"].type.python_type is uuid.UUID
        assert columns["user_id"].type.python_type is uuid.UUID
