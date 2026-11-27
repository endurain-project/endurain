"""Importing a file stores its columnar samples and the start point of its activity, on the real database."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import modules.activities.activity.models as activity_models
import modules.activities.activity_streams.models as stream_models
from tests._factories.reprocess import RUN, TREADMILL, TRIATHLON, import_fixture
from tests._factories.users import make_user


@pytest.fixture
def owner(db: Session):
    user = make_user(db, timezone="Europe/Lisbon")
    db.commit()
    return user


def _activity(db: Session, activity_id) -> activity_models.Activity:
    db.expire_all()
    return db.execute(select(activity_models.Activity).where(activity_models.Activity.id == activity_id)).scalar_one()


def _samples(db: Session, activity_id) -> stream_models.ActivitySamples | None:
    db.expire_all()
    return db.get(stream_models.ActivitySamples, activity_id)


def _streams(db: Session, activity_id) -> dict[int, list[dict]]:
    rows = db.execute(
        select(stream_models.ActivityStreams).where(stream_models.ActivityStreams.activity_id == activity_id)
    ).scalars()
    return {row.stream_type: row.stream_waypoints for row in rows}


class TestAFileWithAGpsTrack:
    def test_the_samples_are_stored_and_the_old_streams_are_not(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)

        samples = _samples(db, activity_id)

        assert samples is not None
        assert samples.offsets_ms == sorted(samples.offsets_ms)
        for channel in (samples.heart_rate, samples.elevation, samples.latitude, samples.longitude):
            assert channel is not None
            assert len(channel) == len(samples.offsets_ms)
        assert _streams(db, activity_id) == {}

    def test_the_start_point_is_the_first_position(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)

        activity = _activity(db, activity_id)
        samples = _samples(db, activity_id)

        first = next(i for i, lat in enumerate(samples.latitude) if lat is not None)
        assert (activity.start_latitude, activity.start_longitude) == (
            samples.latitude[first],
            samples.longitude[first],
        )


class TestAFileWithoutAGpsTrack:
    def test_the_samples_have_no_position_and_the_activity_has_no_start_point(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, TREADMILL, tmp_path, storage)

        activity = _activity(db, activity_id)
        samples = _samples(db, activity_id)

        assert samples is not None
        assert (samples.latitude, samples.longitude) == (None, None)
        assert (activity.start_latitude, activity.start_longitude) == (None, None)


class TestAMultisportFile:
    def test_each_leg_has_samples_and_the_parent_has_none(self, db, owner, storage, tmp_path):
        [parent_id] = import_fixture(db, owner.id, TRIATHLON, tmp_path, storage)

        legs = (
            db.execute(
                select(activity_models.Activity)
                .where(activity_models.Activity.parent_activity_id == parent_id)
                .order_by(activity_models.Activity.start_time)
            )
            .scalars()
            .all()
        )

        assert len(legs) == 5
        assert _samples(db, parent_id) is None
        assert all(_samples(db, leg.id) is not None for leg in legs)

    def test_the_parent_takes_the_start_point_of_its_first_leg_that_has_one(self, db, owner, storage, tmp_path):
        [parent_id] = import_fixture(db, owner.id, TRIATHLON, tmp_path, storage)

        legs = (
            db.execute(
                select(activity_models.Activity)
                .where(activity_models.Activity.parent_activity_id == parent_id)
                .order_by(activity_models.Activity.start_time)
            )
            .scalars()
            .all()
        )
        first = next(leg for leg in legs if leg.start_latitude is not None)

        parent = _activity(db, parent_id)
        assert (parent.start_latitude, parent.start_longitude) == (first.start_latitude, first.start_longitude)
        assert parent.start_latitude is not None
