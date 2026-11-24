"""The application steps every health package shares, on the real database.

Steps records stand for any kind.
"""

import uuid
from datetime import UTC, date, datetime

import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa

import core.date_range as core_date_range
import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.service as health_fasting_service
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_steps.service as health_steps_service
import modules.health.models as health_models
import modules.health.record_crud as health_record_crud
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema
from tests._factories.health import make_health_steps
from tests._factories.users import make_user

_SPEC = health_steps_crud.SPEC
_NO_RANGE = core_date_range.DateRange()
_TODAY = date(2026, 3, 31)


@pytest.fixture
def clock():
    """The platform clock, set to midday UTC on :data:`_TODAY`."""
    platform_clock = platform_runtime.get_active_platform().clock
    platform_clock.moment = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
    return platform_clock


@pytest.fixture
def user(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def other(db):
    return make_user(db, timezone="UTC")


class TestCommitWrite:
    def test_the_staged_write_is_committed_and_returned(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            record = make_health_steps(db, user.id, steps=10)
            db.commit()

        with committed_sessions() as db:
            result = health_record_service.commit_write(
                _SPEC,
                record.id,
                user.id,
                lambda: health_record_crud.edit(
                    _SPEC, record.id, user.id, health_steps_schema.HealthStepsUpdate(steps=20), db, if_match='"1"'
                ),
                db,
                log_message="Edited a steps record",
            )

        assert result.steps == 20
        with committed_sessions() as db:
            assert db.get(health_steps_models.HealthSteps, record.id).steps == 20

    def test_a_write_that_lost_the_version_race_is_a_precondition_failure(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            record = make_health_steps(db, user.id, steps=10)
            db.commit()

        with committed_sessions() as loser, committed_sessions() as winner:
            row = health_record_crud.get_owned(_SPEC, record.id, user.id, loser)
            health_record_crud.edit(
                _SPEC, record.id, user.id, health_steps_schema.HealthStepsUpdate(steps=11), winner, if_match='"1"'
            )
            winner.commit()

            with pytest.raises(core_exceptions.PreconditionFailedError, match="steps record"):
                health_record_service.commit_write(
                    _SPEC,
                    record.id,
                    user.id,
                    lambda: health_record_crud.edit_row(
                        _SPEC, row, health_steps_schema.HealthStepsUpdate(steps=99), loser, if_match='"1"'
                    ),
                    loser,
                    log_message="Edited a steps record",
                )

        with committed_sessions() as db:
            assert db.get(health_steps_models.HealthSteps, record.id).steps == 11

    def test_a_record_deleted_meanwhile_is_not_found_with_the_spec_message(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            record = make_health_steps(db, user.id, steps=10)
            db.commit()

        with committed_sessions() as loser, committed_sessions() as winner:
            row = health_record_crud.get_owned(_SPEC, record.id, user.id, loser)
            health_record_crud.delete(_SPEC, record.id, user.id, winner, if_match='"1"')
            winner.commit()

            with pytest.raises(core_exceptions.NotFoundError, match="Health steps not found"):
                health_record_service.commit_write(
                    _SPEC,
                    record.id,
                    user.id,
                    lambda: health_record_crud.edit_row(
                        _SPEC, row, health_steps_schema.HealthStepsUpdate(steps=99), loser, if_match='"1"'
                    ),
                    loser,
                    log_message="Edited a steps record",
                )


class TestGetRecord:
    def test_the_owned_row_is_returned_as_its_read_schema(self, db, user):
        record = make_health_steps(db, user.id, steps=900)

        found = health_record_service.get_record(_SPEC, record.id, user.id, db)

        assert (found.id, found.steps, found.version) == (record.id, 900, 1)

    def test_another_users_record_is_not_found(self, db, user, other):
        theirs = make_health_steps(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError, match="Health steps not found"):
            health_record_service.get_record(_SPEC, theirs.id, user.id, db)


class TestChart:
    def test_an_interval_is_charted_from_its_start_in_the_finest_bucket(self, db, user, clock):
        windows = []

        def fetch(since, until, bucket):
            windows.append((since, until, bucket))
            return [health_schema.HealthChartPoint(date=date(2026, 3, 30), value=1)]

        series = health_record_service.chart(user.id, health_constants.Interval.LAST_30_DAYS, _NO_RANGE, fetch, db)

        assert windows == [(date(2026, 3, 1), None, health_constants.ChartBucket.DAY)]
        assert series.bucket is health_constants.ChartBucket.DAY
        assert [(p.date, p.value) for p in series.points] == [(date(2026, 3, 30), 1)]

    def test_a_range_replaces_the_interval(self, db, user, clock):
        windows = []
        window = core_date_range.DateRange(date(2023, 1, 1), date(2023, 1, 31))

        health_record_service.chart(
            user.id,
            health_constants.Interval.LAST_7_DAYS,
            window,
            lambda since, until, bucket: windows.append((since, until)) or [],
            db,
        )

        assert windows == [(date(2023, 1, 1), date(2023, 1, 31))]

    def test_a_range_with_only_an_end_opens_at_the_earliest_date(self, db, user, clock):
        windows = []

        health_record_service.chart(
            user.id,
            health_constants.Interval.LAST_7_DAYS,
            core_date_range.DateRange(None, date(2023, 1, 31)),
            lambda since, until, bucket: windows.append((since, until)) or [],
            db,
        )

        assert windows == [(date.min, date(2023, 1, 31))]

    def test_the_interval_follows_the_users_timezone(self, db, clock):
        auckland = make_user(db, timezone="Pacific/Auckland")
        windows = []

        # 12:00 UTC on 31 March is already 1 April in Auckland.
        health_record_service.chart(
            auckland.id,
            health_constants.Interval.LAST_7_DAYS,
            _NO_RANGE,
            lambda since, until, bucket: windows.append(since) or [],
            db,
        )

        assert windows == [date(2026, 3, 25)]


class TestListPage:
    @pytest.fixture
    def records(self, db, user, other):
        for day in (date(2026, 2, 20), date(2026, 3, 2), date(2026, 3, 30)):
            make_health_steps(db, user.id, date=day)
        make_health_steps(db, other.id, date=date(2026, 3, 30))

    def _list(self, db, user, interval, date_range=_NO_RANGE, page_number=1, num_records=2):
        return health_record_service.list_page(
            user.id,
            interval,
            date_range,
            page_number,
            num_records,
            lambda since, until: health_steps_crud.get_health_steps_number_by_user_id(user.id, db, since, until),
            lambda since, until: health_steps_crud.get_health_steps_by_user_id(
                user.id, db, page_number, num_records, since, until
            ),
            db,
        )

    def test_an_interval_counts_and_lists_from_its_start(self, db, user, records, clock):
        page = self._list(db, user, health_constants.Interval.LAST_30_DAYS)

        assert (page.total, [r.date for r in page.items]) == (2, [date(2026, 3, 30), date(2026, 3, 2)])

    def test_no_interval_is_unbounded_and_pages(self, db, user, records, clock):
        page = self._list(db, user, None)

        assert (page.total, len(page.items), page.next) == (3, 2, 2)

    def test_a_range_replaces_the_interval(self, db, user, records, clock):
        window = core_date_range.DateRange(date(2026, 2, 1), date(2026, 2, 28))

        page = self._list(db, user, health_constants.Interval.LAST_7_DAYS, window)

        assert (page.total, [r.date for r in page.items]) == (1, [date(2026, 2, 20)])


class TestUpsertDated:
    @staticmethod
    def _upsert(db, user, record):
        return health_steps_service.stage_upsert_health_steps(user.id, record, db)

    def test_a_missing_date_becomes_the_users_local_today(self, db, user, clock):
        stored = self._upsert(db, user, health_steps_schema.HealthStepsImport(steps=10))

        assert (stored.date, stored.steps) == (_TODAY, 10)

    def test_the_date_follows_the_users_timezone(self, db, clock):
        auckland = make_user(db, timezone="Pacific/Auckland")

        stored = self._upsert(db, auckland, health_steps_schema.HealthStepsImport(steps=10))

        assert stored.date == date(2026, 4, 1)

    def test_an_existing_day_is_edited_not_created(self, db, user):
        first = make_health_steps(db, user.id, date=date(2026, 3, 30), steps=5)

        stored = self._upsert(db, user, health_steps_schema.HealthStepsImport(date=date(2026, 3, 30), steps=10))

        assert (stored.id, stored.steps, stored.version) == (first.id, 10, 2)
        count = db.scalar(sa.select(sa.func.count()).select_from(health_steps_models.HealthSteps))
        assert count == 1


class TestRestoreArchivedRecords:
    @staticmethod
    def _restore(db, user, rows, **kwargs):
        return health_record_service.restore_archived_records(
            rows,
            health_steps_schema.HealthStepsImport,
            health_steps_service.stage_upsert_health_steps,
            user.id,
            db,
            kind="health_steps",
            **kwargs,
        )

    @staticmethod
    def _steps(db, user):
        rows = db.scalars(
            sa.select(health_steps_models.HealthSteps)
            .where(health_steps_models.HealthSteps.user_id == user.id)
            .order_by(health_steps_models.HealthSteps.date)
        )
        return [(r.date, r.steps, r.version) for r in rows]

    def test_each_row_is_staged_without_the_identity_the_archive_carries(self, db, user, other):
        identity = {"id": str(uuid.uuid4()), "user_id": str(other.id), "version": 4}

        count = self._restore(db, user, [{"date": "2024-01-15", "steps": 9000, **identity}])

        assert count == 1
        assert self._steps(db, user) == [(date(2024, 1, 15), 9000, 1)]
        assert self._steps(db, other) == []

    def test_an_invalid_row_is_skipped_and_the_rest_staged(self, db, user):
        rows = [{"steps": "many"}, {"unknown": 1}, {"date": "2024-01-16", "steps": 100}]

        assert self._restore(db, user, rows) == 1
        assert self._steps(db, user) == [(date(2024, 1, 16), 100, 1)]

    def test_a_row_for_a_day_the_user_has_updates_it(self, db, user):
        make_health_steps(db, user.id, date=date(2024, 1, 15), steps=5)

        assert self._restore(db, user, [{"date": "2024-01-15", "steps": 50}]) == 1
        assert self._steps(db, user) == [(date(2024, 1, 15), 50, 2)]

    def test_no_rows_stages_nothing(self, db, user):
        assert self._restore(db, user, []) == 0
        assert self._steps(db, user) == []

    def test_the_summary_counts_the_rows_staged(self, db, user, caplog):
        rows = [{"date": f"2024-01-{day}", "steps": 5} for day in (15, 16)]

        with caplog.at_level("DEBUG", logger=health_record_service.logger.name):
            self._restore(db, user, rows)

        [summary] = [r for r in caplog.records if r.getMessage() == "Imported health records"]
        assert (summary.levelname, summary.count, summary.skipped) == ("DEBUG", 2, 0)

    def test_a_value_the_server_derives_is_dropped_from_an_archived_row(self, db, user):
        row = {
            "fast_start_time": "2024-01-15T20:00:00Z",
            "fast_end_time": "2024-01-16T12:00:00Z",
            "actual_duration_seconds": 57600,
            "status": "completed",
        }

        def restore(derived: frozenset[str]) -> int:
            return health_record_service.restore_archived_records(
                [row],
                health_fasting_schema.HealthFastingImport,
                health_fasting_service.stage_import_health_fasting,
                user.id,
                db,
                kind="health_fasting",
                server_derived=derived,
            )

        assert restore(frozenset()) == 0
        assert restore(frozenset({"actual_duration_seconds"})) == 1

    def test_a_record_the_stage_keeps_out_is_not_counted_and_is_summarised_as_skipped(self, db, user, caplog):
        health_fasting_service.stage_import_health_fasting(
            user.id,
            health_fasting_schema.HealthFastingImport(
                fast_start_time=datetime(2024, 1, 15, 8, tzinfo=UTC),
                fast_end_time=datetime(2024, 1, 15, 18, tzinfo=UTC),
                status="completed",
            ),
            db,
        )
        overlapping = {
            "fast_start_time": "2024-01-15T12:00:00Z",
            "fast_end_time": "2024-01-15T20:00:00Z",
            "status": "completed",
        }

        with caplog.at_level("DEBUG", logger=health_record_service.logger.name):
            restored = health_record_service.restore_archived_records(
                [overlapping],
                health_fasting_schema.HealthFastingImport,
                health_fasting_service.stage_import_health_fasting,
                user.id,
                db,
                kind="health_fasting",
            )

        assert restored == 0
        [summary] = [r for r in caplog.records if r.getMessage() == "Imported health records"]
        assert (summary.count, summary.skipped) == (0, 1)


class TestPruneDeletions:
    def test_only_tombstones_past_their_retention_are_removed_and_committed(self, committed_sessions):
        recent, old = uuid.uuid4(), uuid.uuid4()
        with committed_sessions() as db:
            user = make_user(db)
            db.add_all(
                [
                    health_models.HealthRecordDeletion(
                        user_id=user.id,
                        record_id=old,
                        record_type="health_weight",
                        deleted_at=datetime(2020, 1, 1, tzinfo=UTC),
                    ),
                    health_models.HealthRecordDeletion(user_id=user.id, record_id=recent, record_type="health_weight"),
                ]
            )
            db.commit()

        with committed_sessions() as db:
            assert health_record_service.prune_deletions(db) == 1

        with committed_sessions() as db:
            assert [d.record_id for d in db.scalars(sa.select(health_models.HealthRecordDeletion))] == [recent]
