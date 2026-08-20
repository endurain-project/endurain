"""HR-zone scoring: the loop, the max-HR lookup, and what gets stored.

These moved out of ``crud`` when the persistence layer stopped asking the users
module questions mid-batch. The service now resolves each owner's max heart
rate, computes the breakdowns, and hands CRUD a ``{stream_id: zones}`` map — so
these tests assert on that map rather than on mutated ORM rows.
"""

from unittest.mock import MagicMock, patch

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_streams.contracts as contracts

_SVC = "modules.activities.activity_streams.service"


def _record(stream_id: int = 7, activity_id: int = 1) -> contracts.HrStreamRecord:
    return contracts.HrStreamRecord(
        stream_id=stream_id,
        activity_id=activity_id,
        waypoints=[{"hr": 100}],
    )


def _context(activity_id: int = 1, owner_id: int = 2) -> activity_contracts.ActivityScoringContext:
    return activity_contracts.ActivityScoringContext(
        activity_id=activity_id,
        owner_id=owner_id,
        total_timer_time=60.0,
    )


class TestRecomputeHrZonesForUser:
    @patch(f"{_SVC}.activity_streams_utils.compute_hr_zone_breakdown_sync")
    @patch(f"{_SVC}.activity_streams_utils.resolve_max_heart_rate", return_value=200)
    @patch(f"{_SVC}.users_integration_service.get_user")
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_stores_the_computed_zones(self, mock_crud, mock_activity, mock_get_user, mock_max, mock_compute):
        from modules.activities.activity_streams import service

        hr_block = {"zone_1": {"percent": 100.0}}
        mock_compute.return_value = hr_block
        mock_activity.list_user_activity_scoring_contexts.side_effect = [[_context()], []]
        mock_crud.list_hr_streams_for_activities.return_value = [_record()]
        db = MagicMock()

        service.recompute_hr_zones_for_user(1, db)

        mock_compute.assert_called_once_with([{"hr": 100}], 200, 60.0)
        mock_crud.set_zone_percentages.assert_called_once_with({7: {"hr": hr_block}}, db)

    @patch(f"{_SVC}.activity_streams_utils.resolve_max_heart_rate", return_value=None)
    @patch(f"{_SVC}.users_integration_service.get_user")
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_clears_zones_when_max_hr_unresolvable(self, mock_crud, mock_activity, mock_get_user, mock_max):
        """A user who removes their max HR loses the zones derived from it."""
        from modules.activities.activity_streams import service

        mock_activity.list_user_activity_scoring_contexts.side_effect = [[_context()], []]
        mock_crud.list_hr_streams_for_activities.return_value = [_record()]
        db = MagicMock()

        service.recompute_hr_zones_for_user(1, db)

        mock_crud.set_zone_percentages.assert_called_once_with({7: None}, db)

    @patch(f"{_SVC}.users_integration_service.get_user", return_value=None)
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_a_missing_user_still_clears(self, mock_crud, mock_activity, mock_get_user):
        from modules.activities.activity_streams import service

        mock_activity.list_user_activity_scoring_contexts.side_effect = [[_context()], []]
        mock_crud.list_hr_streams_for_activities.return_value = [_record()]

        service.recompute_hr_zones_for_user(1, MagicMock())

        assert mock_crud.set_zone_percentages.call_args.args[0] == {7: None}

    @patch(f"{_SVC}.users_integration_service.get_user", side_effect=RuntimeError("boom"))
    @patch(f"{_SVC}.activity_streams_crud")
    def test_swallows_errors(self, mock_crud, mock_get_user):
        """A recompute failure must not fail the profile edit that triggered it."""
        from modules.activities.activity_streams import service

        service.recompute_hr_zones_for_user(1, MagicMock())

        mock_crud.set_zone_percentages.assert_not_called()


class TestScoreActivityHrZones:
    @patch(f"{_SVC}.users_integration_service.get_user", return_value=None)
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_noop_when_user_missing(self, mock_crud, mock_activity, mock_get_user):
        from modules.activities.activity_streams import service

        mock_activity.get_activity_scoring_context.return_value = _context()
        service.score_activity_hr_zones(1, 2, MagicMock())

        mock_crud.set_zone_percentages.assert_not_called()

    @patch(f"{_SVC}.activity_streams_utils.resolve_max_heart_rate", return_value=None)
    @patch(f"{_SVC}.users_integration_service.get_user", return_value=MagicMock())
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_noop_when_no_max_hr(self, mock_crud, mock_activity, mock_get_user, mock_max):
        from modules.activities.activity_streams import service

        mock_activity.get_activity_scoring_context.return_value = _context()
        service.score_activity_hr_zones(1, 2, MagicMock())

        mock_crud.get_activity_hr_stream.assert_not_called()
        mock_crud.set_zone_percentages.assert_not_called()

    @patch(f"{_SVC}.activity_streams_utils.resolve_max_heart_rate", return_value=190)
    @patch(f"{_SVC}.users_integration_service.get_user", return_value=MagicMock())
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_noop_when_the_activity_has_no_hr_stream(self, mock_crud, mock_activity, mock_get_user, mock_max):
        from modules.activities.activity_streams import service

        mock_activity.get_activity_scoring_context.return_value = _context()
        mock_crud.get_activity_hr_stream.return_value = None

        service.score_activity_hr_zones(1, 2, MagicMock())

        mock_crud.set_zone_percentages.assert_not_called()

    @patch(f"{_SVC}.activity_streams_utils.compute_hr_zone_breakdown_sync", return_value={"zone_1": 1})
    @patch(f"{_SVC}.activity_streams_utils.resolve_max_heart_rate", return_value=190)
    @patch(f"{_SVC}.users_integration_service.get_user", return_value=MagicMock())
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_stores_the_breakdown(self, mock_crud, mock_activity, mock_get_user, mock_max, mock_compute):
        from modules.activities.activity_streams import service

        mock_activity.get_activity_scoring_context.return_value = _context()
        mock_crud.get_activity_hr_stream.return_value = _record()
        db = MagicMock()

        service.score_activity_hr_zones(1, 2, db)

        mock_crud.set_zone_percentages.assert_called_once_with({7: {"hr": {"zone_1": 1}}}, db)


class TestBackfillMissingHrZones:
    @patch(f"{_SVC}.activity_streams_utils.compute_hr_zone_breakdown_sync", return_value={"zone_1": 1})
    @patch(f"{_SVC}.activity_streams_utils.resolve_max_heart_rate", return_value=190)
    @patch(f"{_SVC}.users_integration_service.get_user", return_value=MagicMock())
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_scores_missing_streams(self, mock_crud, mock_activity, mock_get_user, mock_max, mock_compute):
        from modules.activities.activity_streams import service

        mock_crud.list_hr_streams_missing_zones.side_effect = [[_record(stream_id=5)], []]
        mock_activity.get_activity_scoring_contexts.return_value = {1: _context()}

        assert service.backfill_missing_hr_zones(MagicMock()) == 1
        assert mock_crud.set_zone_percentages.call_args_list[0].args[0] == {5: {"hr": {"zone_1": 1}}}

    @patch(f"{_SVC}.activity_streams_utils.resolve_max_heart_rate", return_value=None)
    @patch(f"{_SVC}.users_integration_service.get_user", return_value=MagicMock())
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_skips_when_the_owner_has_no_max_hr(self, mock_crud, mock_activity, mock_get_user, mock_max):
        """Left untouched, so a later profile edit can still score them."""
        from modules.activities.activity_streams import service

        mock_crud.list_hr_streams_missing_zones.side_effect = [[_record(stream_id=5)], []]
        mock_activity.get_activity_scoring_contexts.return_value = {1: _context()}

        assert service.backfill_missing_hr_zones(MagicMock()) == 0
        assert mock_crud.set_zone_percentages.call_args_list[0].args[0] == {}

    @patch(f"{_SVC}.activity_streams_utils.compute_hr_zone_breakdown_sync", return_value={"zone_1": 1})
    @patch(f"{_SVC}.activity_streams_utils.resolve_max_heart_rate", return_value=190)
    @patch(f"{_SVC}.users_integration_service.get_user", return_value=MagicMock())
    @patch(f"{_SVC}.activity_child_access")
    @patch(f"{_SVC}.activity_streams_crud")
    def test_each_owner_is_looked_up_once_per_run(
        self,
        mock_crud,
        mock_activity,
        mock_get_user,
        mock_max,
        mock_compute,
    ):
        from modules.activities.activity_streams import service

        mock_crud.list_hr_streams_missing_zones.side_effect = [
            [_record(stream_id=5), _record(stream_id=6, activity_id=2)],
            [],
        ]
        mock_activity.get_activity_scoring_contexts.return_value = {
            1: _context(activity_id=1, owner_id=2),
            2: _context(activity_id=2, owner_id=2),
        }

        service.backfill_missing_hr_zones(MagicMock())

        mock_get_user.assert_called_once()
