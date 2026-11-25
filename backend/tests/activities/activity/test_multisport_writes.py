"""What a multisport activity and its legs do to storing, editing, deleting and bulk-editing activities."""

from datetime import UTC, datetime

import pydantic
import pytest
from sqlalchemy import select, update

import core.exceptions as core_exceptions
import modules.activities.activity.audit_actions as activity_audit_actions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.events as activity_events
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service
from tests._factories.activities import make_activity, make_activity_at, make_multisport
from tests._factories.gears import make_gear
from tests._factories.users import audit_rows_of, make_user

_Visibility = activity_constants.ActivityVisibility
_Type = activity_constants.ActivityType
_START = datetime(2026, 7, 28, 9, tzinfo=UTC)
_LEGS = 5


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


def _rows(db, *activities):
    db.expire_all()
    return [db.get(activity_models.Activity, activity.id) for activity in activities]


def _edit(db, user, activity, **fields):
    return activity_service.edit_activity(
        activity.id,
        user.id,
        activity_schema.ActivityEdit(**fields),
        db,
        if_match=f'"{db.get(activity_models.Activity, activity.id).version}"',
    )


def _core(user_id, start_time=_START, **overrides):
    values = {
        "user_id": user_id,
        "name": "Leg",
        "distance": 1000,
        "activity_type": 1,
        "start_time": start_time,
        "end_time": start_time.replace(hour=10),
        "total_elapsed_time": 3600.0,
        **{flag: False for flag in activity_schema.ActivityBase.model_fields if flag.startswith("hide_")},
    }
    values.update(overrides)
    return activity_contracts.ActivityCore.model_validate(values)


class TestSameStart:
    def test_a_group_stored_leg_by_leg_hides_none_of_its_rows(self, db, owner):
        parent, legs = make_multisport(db, owner.id, start=_START)

        assert [row.is_hidden for row in _rows(db, parent, *legs)] == [False] * (_LEGS + 1)

    def test_a_group_restored_leg_by_leg_hides_none_of_its_rows(self, db, owner):
        parent = activity_integration.restore_activity(_core(owner.id, activity_type=48), db)

        leg = activity_integration.restore_activity(_core(owner.id), db, parent_activity_id=parent.id)

        assert [row.is_hidden for row in _rows(db, parent, leg)] == [False, False]
        assert _rows(db, leg)[0].parent_activity_id == parent.id

    def test_an_unrelated_activity_at_the_same_instant_still_makes_a_duplicate(self, db, owner):
        alone = make_activity_at(db, owner.id, _START)

        parent, legs = make_multisport(db, owner.id, start=_START)

        assert _rows(db, alone)[0].is_hidden is False
        assert [row.is_hidden for row in _rows(db, parent, legs[0])] == [True, True]

    def test_an_activity_at_the_instant_a_group_started_is_a_duplicate_of_it(self, db, owner):
        make_multisport(db, owner.id, start=_START)

        late = make_activity_at(db, owner.id, _START)

        assert _rows(db, late)[0].is_hidden is True

    def test_creating_a_leg_names_its_parent_on_the_row(self, db, owner):
        parent = make_activity(db, owner.id, activity_type=48)

        leg = activity_crud.create_activity(_core(owner.id), db, parent_activity_id=parent.id)

        assert leg.parent_activity_id == parent.id


class TestEditTypeAndGear:
    def test_no_client_may_set_the_multisport_type(self):
        with pytest.raises(pydantic.ValidationError, match="set by the server"):
            activity_schema.ActivityEdit(activity_type=_Type.MULTISPORT)

    def test_the_type_and_the_gear_of_a_multisport_activity_cannot_be_edited(self, db, owner):
        parent, _ = make_multisport(db, owner.id)
        gear = make_gear(db, owner.id)

        with pytest.raises(core_exceptions.ConflictError):
            _edit(db, owner, parent, activity_type=_Type.RUN)
        with pytest.raises(core_exceptions.ConflictError):
            _edit(db, owner, parent, gear_id=gear.id)

        row = _rows(db, parent)[0]
        assert (row.activity_type, row.gear_id) == (_Type.MULTISPORT.stored, None)

    def test_the_name_and_notes_of_a_multisport_activity_are_edited_like_any_activity(self, db, owner):
        parent, _ = make_multisport(db, owner.id)

        _edit(db, owner, parent, name="Ironman", private_notes="windy")

        assert _rows(db, parent)[0].name == "Ironman"

    def test_a_leg_keeps_its_own_type_and_gear(self, db, owner):
        _, legs = make_multisport(db, owner.id)
        gear = make_gear(db, owner.id)

        _edit(db, owner, legs[2], activity_type=_Type.GRAVEL_RIDE, gear_id=gear.id, name="Bike")

        row = _rows(db, legs[2])[0]
        assert (row.activity_type, row.gear_id, row.name) == (_Type.GRAVEL_RIDE.stored, gear.id, "Bike")


_PRIVACY_EDITS = [
    {"visibility": _Visibility.PUBLIC},
    {"is_hidden": True},
    *({flag: True} for flag in sorted(activity_constants.PRIVACY_FIELDS - {"visibility", "is_hidden"})),
]


class TestEditPrivacy:
    @pytest.mark.parametrize("fields", _PRIVACY_EDITS, ids=lambda fields: next(iter(fields)))
    def test_a_leg_does_not_take_a_privacy_change_of_its_own(self, db, owner, fields):
        _, legs = make_multisport(db, owner.id)
        before = _rows(db, legs[1])[0].version

        with pytest.raises(core_exceptions.ConflictError):
            _edit(db, owner, legs[1], **fields)

        assert _rows(db, legs[1])[0].version == before

    def test_the_privacy_of_a_parent_is_the_privacy_of_all_its_legs(self, db, owner, published):
        parent, legs = make_multisport(db, owner.id)

        _edit(db, owner, parent, visibility=_Visibility.PUBLIC, hide_hr=True, is_hidden=True, name="Race")

        rows = _rows(db, parent, *legs)
        assert {(row.visibility, row.hide_hr, row.is_hidden) for row in rows} == {(0, True, True)}
        assert [row.version for row in rows] == [2] * (_LEGS + 1)
        assert [row.name for row in rows[1:]] != ["Race"] * _LEGS

    def test_each_leg_that_changed_publishes_updated_with_the_privacy_fields_sent(self, db, owner, published):
        parent, legs = make_multisport(db, owner.id)

        _edit(db, owner, parent, visibility=_Visibility.PUBLIC, name="Race")

        events = published[activity_events.ACTIVITY_UPDATED]
        by_activity = {event.payload["activity_id"]: event.payload["changed_fields"] for event in events}
        assert by_activity == {
            str(parent.id): ["name", "visibility"],
            **{str(leg.id): ["visibility"] for leg in legs},
        }

    def test_each_leg_that_changed_stages_a_visibility_audit_row_naming_the_fields_and_never_the_values(
        self, db, owner
    ):
        parent, legs = make_multisport(db, owner.id)

        _edit(db, owner, parent, visibility=_Visibility.PUBLIC, hide_hr=True)

        rows = audit_rows_of(db, activity_audit_actions.VISIBILITY_UPDATE.id)
        assert sorted(row.target_id for row in rows) == sorted(str(a.id) for a in (parent, *legs))
        assert {tuple(sorted(row.details["changed_fields"])) for row in rows} == {("hide_hr", "visibility")}
        assert {row.target_owner_id for row in rows} == {str(owner.id)}

    def test_a_leg_that_already_has_the_values_is_not_rewritten_audited_or_announced(self, db, owner, published):
        parent, legs = make_multisport(db, owner.id)
        db.execute(
            update(activity_models.Activity).where(activity_models.Activity.id == legs[0].id).values(visibility=0)
        )
        db.flush()
        db.expire_all()

        _edit(db, owner, parent, visibility=_Visibility.PUBLIC)

        assert _rows(db, legs[0])[0].version == 1
        announced = {event.payload["activity_id"] for event in published[activity_events.ACTIVITY_UPDATED]}
        assert str(legs[0].id) not in announced
        assert str(legs[1].id) in announced
        assert len(audit_rows_of(db, activity_audit_actions.VISIBILITY_UPDATE.id)) == _LEGS

    def test_an_edit_that_changes_no_privacy_field_leaves_the_legs_alone(self, db, owner, published):
        parent, legs = make_multisport(db, owner.id)

        _edit(db, owner, parent, name="Race")

        assert [row.version for row in _rows(db, *legs)] == [1] * _LEGS
        assert [e.payload["activity_id"] for e in published[activity_events.ACTIVITY_UPDATED]] == [str(parent.id)]


class TestDelete:
    def test_a_leg_is_deleted_with_its_parent_and_not_alone(self, db, owner, published):
        _, legs = make_multisport(db, owner.id)

        with pytest.raises(core_exceptions.ConflictError):
            activity_service.delete_activity(legs[0].id, owner.id, db, if_match="*")

        assert _rows(db, legs[0])[0] is not None
        assert published[activity_events.ACTIVITY_DELETED] == []

    def test_deleting_a_parent_deletes_its_legs_and_leaves_a_tombstone_for_each(self, db, owner):
        parent, legs = make_multisport(db, owner.id)
        keep = make_activity_at(db, owner.id, _START.replace(day=29))

        activity_service.delete_activity(parent.id, owner.id, db, if_match="*")

        assert _rows(db, parent, *legs) == [None] * (_LEGS + 1)
        assert _rows(db, keep)[0] is not None
        tombstoned = set(db.scalars(select(activity_models.ActivityDeletion.record_id)))
        assert tombstoned == {parent.id, *(leg.id for leg in legs)}

    def test_deleting_a_parent_publishes_deleted_for_it_and_for_each_leg(self, db, owner, published):
        parent, legs = make_multisport(db, owner.id)

        activity_service.delete_activity(parent.id, owner.id, db, if_match="*")

        announced = [event.payload["activity_id"] for event in published[activity_events.ACTIVITY_DELETED]]
        assert sorted(announced) == sorted(str(a.id) for a in (parent, *legs))

    def test_a_stale_delete_of_a_parent_keeps_the_legs(self, db, owner, published):
        parent, legs = make_multisport(db, owner.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            activity_service.delete_activity(parent.id, owner.id, db, if_match='"99"')

        assert all(row is not None for row in _rows(db, parent, *legs))
        assert published[activity_events.ACTIVITY_DELETED] == []

    def test_account_deletion_removes_a_group_with_an_event_and_a_tombstone_for_every_row(self, db, owner, published):
        parent, legs = make_multisport(db, owner.id)

        deleted = activity_service.delete_activities_batch_for_user(owner.id, 1, db, source="test")
        db.commit()

        assert deleted == _LEGS + 1
        assert _rows(db, parent, *legs) == [None] * (_LEGS + 1)
        announced = [event.payload["activity_id"] for event in published[activity_events.ACTIVITY_DELETED]]
        assert sorted(announced) == sorted(str(a.id) for a in (parent, *legs))
        assert set(db.scalars(select(activity_models.ActivityDeletion.record_id))) == {
            parent.id,
            *(leg.id for leg in legs),
        }

    def test_account_deletion_in_small_batches_reaches_every_row_exactly_once(self, db, owner, published):
        groups = [make_multisport(db, owner.id, start=_START.replace(day=day)) for day in (1, 2)]
        alone = make_activity_at(db, owner.id, _START.replace(day=3))
        every_id = {a.id for parent, legs in groups for a in (parent, *legs)} | {alone.id}

        while activity_service.delete_activities_batch_for_user(owner.id, 2, db, source="test"):
            db.commit()

        announced = [event.payload["activity_id"] for event in published[activity_events.ACTIVITY_DELETED]]
        assert sorted(announced) == sorted(str(row_id) for row_id in every_id)
        assert (
            db.scalars(select(activity_models.Activity.id).where(activity_models.Activity.user_id == owner.id)).all()
            == []
        )

    def test_unlinking_strava_never_deletes_a_multisport_activity_without_its_legs(self, db, owner, published):
        parent, legs = make_multisport(db, owner.id)
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == parent.id)
            .values(strava_activity_id=7)
        )
        db.flush()

        deleted = activity_service.delete_all_strava_activities(owner.id, db, source="test", limit=10)
        db.commit()

        assert deleted == 0
        assert all(row is not None for row in _rows(db, parent, *legs))
        assert published[activity_events.ACTIVITY_DELETED] == []


class TestBulkVisibility:
    def test_the_legs_of_a_changed_parent_follow_it_with_a_new_version(self, db, owner):
        parent, legs = make_multisport(db, owner.id)

        changed = activity_crud.edit_user_activities_visibility_batch(owner.id, 0, 10, db)

        assert sorted(changed) == sorted(a.id for a in (parent, *legs))
        rows = _rows(db, parent, *legs)
        assert [(row.visibility, row.version) for row in rows] == [(0, 2)] * (_LEGS + 1)

    def test_a_leg_named_directly_is_not_changed_by_itself(self, db, owner):
        parent, legs = make_multisport(db, owner.id)
        db.execute(
            update(activity_models.Activity).where(activity_models.Activity.id == parent.id).values(visibility=0)
        )
        db.flush()

        changed = activity_crud.edit_user_activities_visibility_batch(owner.id, 0, 10, db)

        assert changed == []
        assert [row.visibility for row in _rows(db, *legs)] == [2] * _LEGS

    def test_a_batch_of_one_takes_a_whole_group_and_no_leg_alone(self, db, owner):
        make_multisport(db, owner.id, start=_START.replace(day=1))
        make_multisport(db, owner.id, start=_START.replace(day=2))

        first = activity_crud.edit_user_activities_visibility_batch(owner.id, 0, 1, db)
        second = activity_crud.edit_user_activities_visibility_batch(owner.id, 0, 1, db)
        third = activity_crud.edit_user_activities_visibility_batch(owner.id, 0, 1, db)

        assert (len(first), len(second), third) == (_LEGS + 1, _LEGS + 1, [])
        assert set(first).isdisjoint(second)
