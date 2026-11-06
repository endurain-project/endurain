"""Audit rows of a change to who can see an activity."""

from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState

import modules.activities.activity.audit_actions as activity_audit_actions
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.bulk_edit_job_service as job_service
import modules.activities.activity.bulk_edit_state_store as bulk_edit_state_store
import modules.activities.activity.events as activity_events
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service

_JOBS = "modules.activities.activity.bulk_edit_job_service"
_SERVICE = "modules.activities.activity.service"
_Kind = bulk_edit_constants.BulkEditKind.VISIBILITY


class TestBulkVisibilityRequest:
    @pytest.fixture
    def states(self):
        return bulk_edit_state_store.ActivityBulkEditStateStore(MemoryState())

    def _request(self, states, db, *, jobs_enabled):
        with (
            patch(f"{_JOBS}.core_config.settings", MagicMock(JOBS_ENABLED=jobs_enabled)),
            patch(f"{_JOBS}.activity_event_publishers"),
            patch(f"{_JOBS}._pool"),
        ):
            return job_service.request_visibility_edit(4, 2, states, db)

    @pytest.mark.parametrize("jobs_enabled", [True, False])
    def test_the_request_is_audited_with_the_visibility(self, states, mock_db, jobs_enabled):
        with jasil_testing.capture_audit() as audit:
            self._request(states, mock_db, jobs_enabled=jobs_enabled)

        entry = audit.assert_audited(
            activity_audit_actions.VISIBILITY_BULK_UPDATE.id, target_type="user", target_id="4", target_owner_id="4"
        )
        assert entry.details == {"visibility": 2}

    def test_a_refused_second_request_is_not_audited(self, states, mock_db):
        states.begin(4, _Kind)

        with jasil_testing.capture_audit() as audit, pytest.raises(Exception, match="already in progress"):
            self._request(states, mock_db, jobs_enabled=True)

        audit.assert_not_audited(activity_audit_actions.VISIBILITY_BULK_UPDATE.id)

    def test_the_job_writes_no_row_per_activity(self, states):
        states.begin(4, _Kind)
        payload = activity_events.VisibilityEditRequestedPayload(user_id=4, visibility=2)

        with (
            jasil_testing.capture_audit() as audit,
            patch(f"{_JOBS}.core_database"),
            patch(f"{_JOBS}.activity_event_publishers"),
            patch(f"{_JOBS}.activity_crud") as crud,
        ):
            crud.edit_user_activities_visibility_batch.side_effect = [[1, 2], []]
            job_service.run_visibility_edit(payload, states)

        assert audit.entries == []


class TestSingleActivityEdit:
    def _edit(self, edit: activity_schema.ActivityEdit, *, before: dict, after: dict, mock_db):
        with (
            patch(f"{_SERVICE}.activity_crud") as crud,
            patch(f"{_SERVICE}.activity_event_publishers"),
            patch(f"{_SERVICE}.gears_integration"),
            patch(f"{_SERVICE}._with_thumbnail_urls"),
        ):
            crud.get_activity_by_id_from_user_id.return_value = MagicMock(**before)
            crud.edit_activity.return_value = MagicMock(**after)
            activity_service.edit_activity(5, 1, edit, mock_db, if_match="*")

    def test_a_changed_visibility_and_hide_flag_are_audited_by_name(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._edit(
                activity_schema.ActivityEdit(name="Run", visibility="private", hide_map=True, hide_hr=False),
                before={"visibility": 0, "hide_map": False, "hide_hr": False},
                after={"visibility": 2, "hide_map": True, "hide_hr": False},
                mock_db=mock_db,
            )

        entry = audit.assert_audited(
            activity_audit_actions.VISIBILITY_UPDATE.id, target_type="activity", target_id="5", target_owner_id="1"
        )
        assert entry.details == {"changed_fields": ["visibility", "hide_map"]}

    def test_an_edit_that_changes_no_visibility_field_is_not_audited(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._edit(
                activity_schema.ActivityEdit(name="Run"),
                before={"visibility": 0},
                after={"visibility": 0},
                mock_db=mock_db,
            )

        audit.assert_not_audited(activity_audit_actions.VISIBILITY_UPDATE.id)

    def test_a_visibility_resent_unchanged_is_not_audited(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._edit(
                activity_schema.ActivityEdit(visibility="followers", hide_map=False),
                before={"visibility": 1, "hide_map": False},
                after={"visibility": 1, "hide_map": False},
                mock_db=mock_db,
            )

        audit.assert_not_audited(activity_audit_actions.VISIBILITY_UPDATE.id)
