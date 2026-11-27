"""Activities written by several sessions at once, on PostgreSQL: versions, row locks, dedup and event delivery.

Every session has its own connection, so these show what a second session sees only after the first commits, which one
shared transaction never can. A session that must wait for another is observed through ``pg_stat_activity`` instead of
by sleeping.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import jasil.jobs.registry as jobs_registry
import jasil.settings as jasil_settings
import jasil.testing as jasil_testing
import pytest
import sqlalchemy as sa

import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.events as activity_events
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service
import modules.gears.gear.models as gear_models
from tests._factories.activities import make_activity, make_parsed_activity
from tests._factories.gears import make_gear
from tests._factories.users import make_user


def _wait_until_a_session_waits_for_a_lock(factory, timeout: float = 10.0) -> None:
    """Block until another session of this database waits on a lock, so a test acts at that exact point."""
    deadline = datetime.now(UTC) + timedelta(seconds=timeout)
    with factory() as probe:
        while datetime.now(UTC) < deadline:
            waiting = probe.scalar(
                sa.text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
            )
            if waiting:
                return
            # PostgreSQL reads pg_stat_activity once per transaction, so each poll needs a transaction of its own.
            probe.rollback()
            threading.Event().wait(0.02)
    raise AssertionError("no session waited for a lock")


class _Worker:
    """Runs a function on a thread of its own and keeps what it returned or raised."""

    def __init__(self, work) -> None:
        self.result = None
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, args=(work,))
        self._thread.start()

    def _run(self, work) -> None:
        try:
            self.result = work()
        except BaseException as err:
            self.error = err

    def join(self) -> None:
        self._thread.join(timeout=20)
        assert not self._thread.is_alive()


@pytest.fixture
def owner(arrange):
    return arrange(lambda db: make_user(db, timezone="UTC"))


@pytest.fixture
def activity(arrange, owner):
    return arrange(lambda db: make_activity(db, owner.id, name="Original"))


def _stored(committed_sessions, activity_id) -> activity_models.Activity | None:
    with committed_sessions() as db:
        row = db.get(activity_models.Activity, activity_id)
        if row is not None:
            db.expunge(row)
        return row


class TestVersions:
    def test_an_edit_made_after_another_commit_is_refused_against_the_old_version(
        self, committed_sessions, owner, activity
    ):
        with committed_sessions() as db:
            activity_service.edit_activity(
                activity.id, owner.id, activity_schema.ActivityEdit(name="first"), db, if_match='"1"'
            )

        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            activity_service.edit_activity(
                activity.id, owner.id, activity_schema.ActivityEdit(name="second"), db, if_match='"1"'
            )

        assert _stored(committed_sessions, activity.id).name == "first"

    def test_the_precondition_is_checked_on_the_row_that_is_written(self, committed_sessions, owner, activity):
        """A commit landing after the session started but before the edit's load is caught."""
        with committed_sessions() as stale_session:
            # Opens the transaction early; READ COMMITTED means that pins nothing.
            activity_crud.get_activity_by_id_from_user_id(activity.id, owner.id, stale_session)
            with committed_sessions() as other:
                activity_crud.edit_activity(
                    owner.id, activity.id, activity_schema.ActivityEdit(name="other writer"), other, if_match="*"
                )
                other.commit()
            with pytest.raises(core_exceptions.PreconditionFailedError):
                activity_crud.edit_activity(
                    owner.id, activity.id, activity_schema.ActivityEdit(name="mine"), stale_session, if_match='"1"'
                )

    def test_an_edit_that_loses_the_race_at_the_write_is_412_and_keeps_the_winners_change(
        self, committed_sessions, owner, activity
    ):
        with committed_sessions() as winner:
            activity_crud.edit_activity(
                owner.id, activity.id, activity_schema.ActivityEdit(name="winner"), winner, if_match='"1"'
            )

            def lose():
                with committed_sessions() as loser:
                    activity_service.edit_activity(
                        activity.id, owner.id, activity_schema.ActivityEdit(name="loser"), loser, if_match='"1"'
                    )

            worker = _Worker(lose)
            _wait_until_a_session_waits_for_a_lock(committed_sessions)
            winner.commit()
            worker.join()

        assert isinstance(worker.error, core_exceptions.PreconditionFailedError)
        assert _stored(committed_sessions, activity.id).name == "winner"

    def test_a_delete_that_loses_the_race_at_the_write_is_412(self, committed_sessions, owner, activity):
        with committed_sessions() as winner:
            activity_crud.edit_activity(
                owner.id, activity.id, activity_schema.ActivityEdit(name="winner"), winner, if_match='"1"'
            )

            def delete():
                with committed_sessions() as loser:
                    activity_service.delete_activity(activity.id, owner.id, loser, if_match='"1"')

            worker = _Worker(delete)
            _wait_until_a_session_waits_for_a_lock(committed_sessions)
            winner.commit()
            worker.join()

        assert isinstance(worker.error, core_exceptions.PreconditionFailedError)
        assert _stored(committed_sessions, activity.id) is not None

    def test_an_edit_of_an_activity_deleted_meanwhile_is_404_not_412(self, committed_sessions, owner, activity):
        with committed_sessions() as deleter:
            activity_crud.delete_activity(activity.id, owner.id, deleter, if_match='"1"')

            def edit():
                with committed_sessions() as editor:
                    activity_service.edit_activity(
                        activity.id, owner.id, activity_schema.ActivityEdit(name="late"), editor, if_match='"1"'
                    )

            worker = _Worker(edit)
            _wait_until_a_session_waits_for_a_lock(committed_sessions)
            deleter.commit()
            worker.join()

        assert isinstance(worker.error, core_exceptions.NotFoundError)

    def test_a_gear_deleted_after_the_ownership_check_is_reported_as_not_found(
        self, committed_sessions, owner, activity, arrange
    ):
        gear = arrange(lambda db: make_gear(db, owner.id))
        with committed_sessions() as deleter:
            deleter.execute(sa.delete(gear_models.Gear).where(gear_models.Gear.id == gear.id))

            def assign():
                with committed_sessions() as editor:
                    activity_service.edit_activity(
                        activity.id, owner.id, activity_schema.ActivityEdit(gear_id=gear.id), editor, if_match='"1"'
                    )

            worker = _Worker(assign)
            _wait_until_a_session_waits_for_a_lock(committed_sessions)
            deleter.commit()
            worker.join()

        assert isinstance(worker.error, core_exceptions.NotFoundError)
        assert _stored(committed_sessions, activity.id).gear_id is None

    def test_a_background_thumbnail_write_does_not_invalidate_a_users_etag(self, committed_sessions, owner, activity):
        with committed_sessions() as db:
            assert activity_crud.set_activity_thumbnail_key(activity.id, f"{activity.id}.webp", db) is True
            db.commit()

        with committed_sessions() as db:
            edited = activity_service.edit_activity(
                activity.id, owner.id, activity_schema.ActivityEdit(name="still allowed"), db, if_match='"1"'
            )

        assert edited.version == 2

    def test_delete_all_waits_for_a_bulk_edit_that_holds_the_rows(self, committed_sessions, owner, activity):
        """Both take the row locks in id order first, so overlapping bulk writes queue instead of deadlocking."""

        def delete_all():
            with committed_sessions() as db:
                deleted = activity_crud.delete_activities_batch_for_user(owner.id, 100, db)
                db.commit()
            return deleted

        with committed_sessions() as editor:
            assert activity_crud.edit_user_activities_visibility_batch(owner.id, 0, 100, editor) == [activity.id]
            worker = _Worker(delete_all)
            _wait_until_a_session_waits_for_a_lock(committed_sessions)
            editor.commit()
            worker.join()

        assert worker.error is None
        assert [item.id for item in worker.result] == [activity.id]


class TestStravaId:
    def test_two_users_may_store_the_same_strava_activity_and_each_holds_it_once(self, arrange, committed_sessions):
        first_user = arrange(lambda db: make_user(db))
        second_user = arrange(lambda db: make_user(db))

        def parsed(user_id):
            return make_parsed_activity(
                user_id, source=activity_contracts.ImportSource(kind="strava"), strava_activity_id=9_000_000_001
            )

        with committed_sessions() as db:
            first = activity_integration.store_parsed_activity(parsed(first_user.id), db)
            second = activity_integration.store_parsed_activity(parsed(second_user.id), db)
            again = activity_integration.store_parsed_activity(parsed(first_user.id), db)
            db.commit()

        assert len({first.id, second.id}) == 2
        assert again.id == first.id
        with committed_sessions() as db:
            owners = db.scalars(
                sa.select(activity_models.Activity.user_id).where(
                    activity_models.Activity.strava_activity_id == 9_000_000_001
                )
            ).all()
        assert sorted(owners) == sorted([first_user.id, second_user.id])


def _parsed(user_id: uuid.UUID, dedup_key: str) -> activity_contracts.ParsedActivity:
    return make_parsed_activity(
        user_id,
        source=activity_contracts.ImportSource(kind="upload", dedup_key=dedup_key),
        start=datetime(2026, 7, 28, 9, 0, tzinfo=UTC),
    )


@pytest.fixture(params=["durable", "best_effort"])
def delivery(request, tmp_path, owner):
    """A platform in the requested delivery mode, and the events the bus dispatched on it."""
    durable = request.param == "durable"
    platform = jasil_testing.install_test_platform(
        tmp_path,
        clock=jasil_testing.FixedClock(datetime.now(UTC)),
        settings=jasil_settings.JasilSettings(
            audit=jasil_settings.AuditSettings(enabled=True), jobs=jasil_settings.JobSettings(enabled=durable)
        ),
    )
    if durable:
        jobs_registry.registry.register(activity_events.ACTIVITY_CREATED, "test.activity_created", lambda _event: None)
    dispatched: list = []
    platform.events.subscribe(activity_events.ACTIVITY_CREATED, dispatched.append)
    return request.param, dispatched


def _committed_activities(factory) -> int:
    with factory() as db:
        return db.scalar(sa.select(sa.func.count()).select_from(activity_models.Activity)) or 0


def _outbox_rows(factory, activity_id: uuid.UUID) -> int:
    with factory() as db:
        return (
            db.execute(
                sa.text(
                    "SELECT count(*) FROM jasil_event_outbox WHERE event_type = :event_type "
                    "AND payload ->> 'activity_id' = :activity_id"
                ),
                {"event_type": activity_events.ACTIVITY_CREATED, "activity_id": str(activity_id)},
            ).scalar_one()
            or 0
        )


def _delivered(dispatched: list, activity_id: uuid.UUID) -> int:
    return sum(1 for event in dispatched if event.payload.get("activity_id") == str(activity_id))


class TestCreatedDelivery:
    """``activity.created`` commits atomically with the activity, in both delivery modes."""

    def test_nothing_is_visible_or_delivered_before_the_commit(self, delivery, committed_sessions, owner):
        _mode, dispatched = delivery
        with committed_sessions() as db:
            stored = activity_integration.store_parsed_activity(_parsed(owner.id, "staged"), db)

            assert _committed_activities(committed_sessions) == 0
            assert _outbox_rows(committed_sessions, stored.id) == 0
            assert dispatched == []

    def test_a_rolled_back_unit_of_work_leaves_no_activity_and_no_event(self, delivery, committed_sessions, owner):
        _mode, dispatched = delivery
        with committed_sessions() as db:
            stored = activity_integration.store_parsed_activity(_parsed(owner.id, "rolled-back"), db)
            db.rollback()

        assert _committed_activities(committed_sessions) == 0
        assert _outbox_rows(committed_sessions, stored.id) == 0
        assert dispatched == []

    def test_a_session_closed_without_committing_leaves_nothing(self, delivery, committed_sessions, owner):
        """The crash-before-commit case: the staged work and its event vanish together."""
        _mode, dispatched = delivery
        db = committed_sessions()
        stored = activity_integration.store_parsed_activity(_parsed(owner.id, "abandoned"), db)
        db.close()

        assert _committed_activities(committed_sessions) == 0
        assert _outbox_rows(committed_sessions, stored.id) == 0
        assert dispatched == []

    def test_the_commit_makes_the_activity_and_its_event_durable_together(self, delivery, committed_sessions, owner):
        mode, dispatched = delivery
        with committed_sessions() as db:
            stored = activity_integration.store_parsed_activity(_parsed(owner.id, "committed"), db)
            db.commit()

        assert _committed_activities(committed_sessions) == 1
        if mode == "durable":
            assert _outbox_rows(committed_sessions, stored.id) == 1
            assert dispatched == [], "the durable route must not also dispatch on the bus"
        else:
            assert _delivered(dispatched, stored.id) == 1
            assert _outbox_rows(committed_sessions, stored.id) == 0

    def test_a_reimport_stages_no_second_event(self, delivery, committed_sessions, owner):
        mode, dispatched = delivery
        with committed_sessions() as db:
            first = activity_integration.store_parsed_activity(_parsed(owner.id, "same-key"), db)
            db.commit()
        with committed_sessions() as db:
            second = activity_integration.store_parsed_activity(_parsed(owner.id, "same-key"), db)
            db.commit()

        assert second.id == first.id
        assert _committed_activities(committed_sessions) == 1
        assert (
            _outbox_rows(committed_sessions, first.id) if mode == "durable" else _delivered(dispatched, first.id)
        ) == 1

    def test_concurrent_imports_of_one_activity_store_it_once_and_publish_once(
        self, delivery, committed_sessions, owner
    ):
        """The dedup read-then-write races; the unique index picks one winner and the losers return it."""
        mode, dispatched = delivery
        barrier = threading.Barrier(6)

        def import_it():
            barrier.wait()
            with committed_sessions() as db:
                stored = activity_integration.store_parsed_activity(_parsed(owner.id, "raced"), db)
                db.commit()
                return stored.id

        workers = [_Worker(import_it) for _ in range(6)]
        for worker in workers:
            worker.join()

        assert [worker.error for worker in workers] == [None] * 6
        ids = {worker.result for worker in workers}
        assert len(ids) == 1
        assert _committed_activities(committed_sessions) == 1
        [activity_id] = ids
        assert (
            _outbox_rows(committed_sessions, activity_id) if mode == "durable" else _delivered(dispatched, activity_id)
        ) == 1
