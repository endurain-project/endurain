"""Tests for the EventLog ORM model (attribute inspection only)."""

from core.event_log.models import EventLog


class TestEventLogModel:
    def test_tablename(self):
        assert EventLog.__tablename__ == "event_log"

    def test_id_is_primary_key_string_36(self):
        column = EventLog.__table__.c.id
        assert column.primary_key is True
        assert column.type.length == 36

    def test_status_defaults_to_published(self):
        assert EventLog.__table__.c.status.default.arg == "published"

    def test_retry_count_defaults_to_zero(self):
        assert EventLog.__table__.c.retry_count.default.arg == 0

    def test_required_columns_not_nullable(self):
        columns = EventLog.__table__.c
        assert columns.event_type.nullable is False
        assert columns.event_source.nullable is False
        assert columns.event_payload.nullable is False
        assert columns.status.nullable is False
        assert columns.created_at.nullable is False

    def test_optional_columns_nullable(self):
        columns = EventLog.__table__.c
        assert columns.event_metadata.nullable is True
        assert columns.handler_name.nullable is True
        assert columns.worker_id.nullable is True
        assert columns.error_message.nullable is True
        assert columns.processing_time_ms.nullable is True
        assert columns.processed_at.nullable is True
        assert columns.completed_at.nullable is True

    def test_btree_indexes_present_gin_absent(self):
        # The GIN index is Postgres-only and lives in the migration, not in
        # metadata (so SQLite create_all works in tests).
        index_names = {index.name for index in EventLog.__table__.indexes}
        assert "idx_event_log_type_status" in index_names
        assert "idx_event_log_created" in index_names
        assert "idx_event_log_metadata" not in index_names
