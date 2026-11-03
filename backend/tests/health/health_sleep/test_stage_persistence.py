"""Sleep stages carry timestamps, and the JSON column that stores them must accept those."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import sessionmaker
from tests._helpers.db import create_sqlite_session, ensure_user

import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.service as health_sleep_service

_START = datetime(2026, 1, 1, 22, 0, tzinfo=UTC)
_MIDDLE = datetime(2026, 1, 1, 23, 0, tzinfo=UTC)
_END = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)


@pytest.fixture
def db():
    session = create_sqlite_session()
    ensure_user(sessionmaker(bind=session.get_bind()), 1)
    yield session
    session.close()


def _stages(*bounds: tuple[datetime, datetime]) -> list[health_sleep_schema.HealthSleepStage]:
    return [
        health_sleep_schema.HealthSleepStage(
            stage_type=health_sleep_schema.SleepStageType.DEEP,
            start_time_gmt=start,
            end_time_gmt=end,
            duration_seconds=int((end - start).total_seconds()),
        )
        for start, end in bounds
    ]


def _assert_stage_times(record: health_sleep_schema.HealthSleepRead, *bounds: tuple[datetime, datetime]) -> None:
    assert record.sleep_stages is not None
    assert [(stage.start_time_gmt, stage.end_time_gmt) for stage in record.sleep_stages] == list(bounds)


class TestStageTimestamps:
    def test_create_stores_stage_timestamps(self, db):
        created = health_sleep_crud.create_health_sleep(
            1,
            health_sleep_schema.HealthSleepCreate(date=date(2026, 1, 1), sleep_stages=_stages((_START, _MIDDLE))),
            db,
        )

        read = health_sleep_crud.get_health_sleep_by_id(1, created.id, db)
        _assert_stage_times(read, (_START, _MIDDLE))

    def test_edit_stores_stage_timestamps(self, db):
        created = health_sleep_crud.create_health_sleep(
            1, health_sleep_schema.HealthSleepCreate(date=date(2026, 1, 1)), db
        )

        health_sleep_crud.edit_health_sleep(
            1,
            created.id,
            health_sleep_schema.HealthSleepUpdate(sleep_stages=_stages((_MIDDLE, _END))),
            db,
            if_match="*",
        )

        _assert_stage_times(health_sleep_crud.get_health_sleep_by_id(1, created.id, db), (_MIDDLE, _END))

    def test_upsert_creates_then_updates_with_stage_timestamps(self, db):
        day = date(2026, 1, 1)
        health_sleep_service.stage_upsert_health_sleep(
            1, health_sleep_schema.HealthSleepCreate(date=day, sleep_stages=_stages((_START, _MIDDLE))), db
        )

        updated = health_sleep_service.stage_upsert_health_sleep(
            1, health_sleep_schema.HealthSleepCreate(date=day, sleep_stages=_stages((_MIDDLE, _END))), db
        )

        _assert_stage_times(health_sleep_crud.get_health_sleep_by_id(1, updated.id, db), (_MIDDLE, _END))


class TestSleepStagesDump:
    @pytest.mark.parametrize("mode", ["python", "json"])
    def test_dump_is_json_safe_in_every_mode(self, mode):
        dumped = health_sleep_schema.HealthSleepCreate(sleep_stages=_stages((_START, _MIDDLE))).model_dump(mode=mode)

        assert dumped["sleep_stages"][0]["start_time_gmt"] == _START.isoformat().replace("+00:00", "Z")

    def test_no_stages_dump_as_none(self):
        assert health_sleep_schema.HealthSleepCreate().model_dump()["sleep_stages"] is None
