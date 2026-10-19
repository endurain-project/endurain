"""Tests for the activity streams service layer.

Streams mask per stream *type* rather than by a single parent flag, so unlike the
sibling child resources this service resolves the parent activity and filters,
then cuts the masked result into the shared page envelope.
"""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_streams.schema as activity_streams_schema


def _stream(stream_type: int):
    return activity_streams_schema.ActivityStreamsRead(
        id=stream_type,
        activity_id=5,
        stream_type=stream_type,
        stream_waypoints=[],
    )


class TestListActivityStreams:
    @patch("modules.activities.activity_streams.service._max_heart_rate_of", return_value=None)
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_owner_gets_every_stream_unfiltered(self, mock_gate, mock_crud, _max_hr):
        from modules.activities.activity_streams import service

        streams = [_stream(1), _stream(2)]
        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=1)
        mock_crud.get_activity_streams.return_value = streams

        page = service.list_activity_streams(5, 1, MagicMock())

        assert (page.items, page.total) == (streams, 2)

    @patch("modules.activities.activity_streams.service._max_heart_rate_of", return_value=None)
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_the_total_counts_only_what_the_page_could_hold(self, mock_gate, mock_crud, _max_hr):
        """The window is cut in Python, after the mask, so the total matches it."""
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=1)
        mock_crud.get_activity_streams.return_value = [_stream(1), _stream(2), _stream(3)]

        page = service.list_activity_streams(5, 1, MagicMock(), page_number=2, num_records=2)

        assert ([s.stream_type for s in page.items], page.total, page.next) == ([3], 3, None)

    @patch("modules.activities.activity_streams.service._filter_visible_streams")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_non_owner_gets_the_masked_set(self, mock_gate, mock_crud, mock_filter):
        from modules.activities.activity_streams import service

        activity = MagicMock(user_id=2)
        mock_gate.resolve_readable_parent.return_value = activity
        mock_crud.get_activity_streams.return_value = [_stream(1)]
        mock_filter.return_value = []

        page = service.list_activity_streams(5, 1, MagicMock())

        assert (page.items, page.total) == ([], 0)
        mock_filter.assert_called_once_with([mock_crud.get_activity_streams.return_value[0]], activity)

    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_invisible_activity_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = None

        page = service.list_activity_streams(5, 1, MagicMock())

        assert (page.items, page.total) == ([], 0)
        mock_crud.get_activity_streams.assert_not_called()


class TestGetActivityStream:
    @patch("modules.activities.activity_streams.service._is_stream_hidden")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_hidden_stream_is_none_for_a_non_owner(self, mock_gate, mock_crud, mock_hidden):
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=2)
        mock_crud.get_activity_stream_by_type.return_value = _stream(1)
        mock_hidden.return_value = True

        with pytest.raises(core_exceptions.NotFoundError):
            service.get_activity_stream(5, 1, 1, MagicMock())

    @patch("modules.activities.activity_streams.service._max_heart_rate_of", return_value=None)
    @patch("modules.activities.activity_streams.service._is_stream_hidden")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_owner_sees_a_hidden_stream(self, mock_gate, mock_crud, mock_hidden, _max_hr):
        from modules.activities.activity_streams import service

        stream = _stream(1)
        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=1)
        mock_crud.get_activity_stream_by_type.return_value = stream
        mock_hidden.return_value = True

        assert service.get_activity_stream(5, 1, 1, MagicMock()) is stream

    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_missing_stream_is_none(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=1)
        mock_crud.get_activity_stream_by_type.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            service.get_activity_stream(5, 1, 1, MagicMock())


class TestPublicStreams:
    @patch("modules.activities.activity_streams.service._filter_visible_streams")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_public_list_is_always_masked(self, mock_gate, mock_crud, mock_filter):
        """An anonymous caller is never the owner, so the mask always applies."""
        from modules.activities.activity_streams import service

        activity = MagicMock()
        mock_gate.resolve_public_parent.return_value = activity
        mock_crud.get_activity_streams.return_value = [_stream(1)]
        mock_filter.return_value = []

        page = service.list_public_activity_streams(5, MagicMock())

        assert (page.items, page.total) == ([], 0)
        mock_filter.assert_called_once()

    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_non_public_activity_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        mock_gate.resolve_public_parent.return_value = None

        page = service.list_public_activity_streams(5, MagicMock())

        assert (page.items, page.total) == ([], 0)
        with pytest.raises(core_exceptions.NotFoundError):
            service.get_public_activity_stream(5, 1, MagicMock())
        mock_crud.get_activity_streams.assert_not_called()
        mock_crud.get_activity_stream_by_type.assert_not_called()

    @patch("modules.activities.activity_streams.service._is_stream_hidden")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_public_hidden_stream_is_none(self, mock_gate, mock_crud, mock_hidden):
        from modules.activities.activity_streams import service

        mock_gate.resolve_public_parent.return_value = MagicMock()
        mock_crud.get_activity_stream_by_type.return_value = _stream(1)
        mock_hidden.return_value = True

        with pytest.raises(core_exceptions.NotFoundError):
            service.get_public_activity_stream(5, 1, MagicMock())


class TestStreamMask:
    """The per-type mask: each stream type is gated by its own parent flag."""

    def test_a_stream_is_hidden_by_its_own_flag_only(self):
        from modules.activities.activity_streams import constants, service

        activity = MagicMock(hide_hr=True, hide_map=False)

        assert service._is_stream_hidden(activity, constants.STREAM_TYPE_HR) is True
        assert service._is_stream_hidden(activity, constants.STREAM_TYPE_MAP) is False

    def test_an_unmapped_stream_type_is_never_hidden(self):
        from modules.activities.activity_streams import service

        assert service._is_stream_hidden(MagicMock(), 999) is False

    def test_filter_keeps_only_the_visible_streams(self):
        from modules.activities.activity_streams import constants, service

        activity = MagicMock(hide_hr=True, hide_map=False)
        streams = [_stream(constants.STREAM_TYPE_HR), _stream(constants.STREAM_TYPE_MAP)]

        visible = service._filter_visible_streams(streams, activity)

        assert [s.stream_type for s in visible] == [constants.STREAM_TYPE_MAP]


def _hr_stream(waypoints=None) -> activity_streams_schema.ActivityStreamsRead:
    return activity_streams_schema.ActivityStreamsRead(
        id=1,
        activity_id=5,
        stream_type=1,
        stream_waypoints=waypoints if waypoints is not None else [{"hr": 100}, {"hr": 150}, {"hr": 180}],
    )


class TestZonesAreComputedWhenServed:
    """Zones follow the owner's current thresholds; nothing is stored, so nothing goes stale."""

    @pytest.fixture
    def parent(self):
        return MagicMock(user_id=1, total_timer_time=3.0)

    @patch("modules.activities.activity_streams.service.users_integration.get_user")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_an_hr_stream_carries_its_breakdown(self, mock_gate, mock_crud, mock_get_user, parent):
        from modules.activities.activity_streams import service

        mock_get_user.return_value = MagicMock(max_heart_rate=200, birthdate=None, timezone="UTC")
        mock_gate.resolve_readable_parent.return_value = parent
        mock_crud.get_activity_stream_by_type.return_value = _hr_stream()

        stream = service.get_activity_stream(5, 1, 1, MagicMock())

        hr = stream.zone_percentages["hr"]
        # 100 < 120 (zone 1), 150 in [140,160) (zone 3), 180 >= 180 (zone 5)
        assert [hr[f"zone_{n}"]["percent"] for n in range(1, 6)] == [33.33, 0.0, 33.33, 0.0, 33.33]

    @patch("modules.activities.activity_streams.service.users_integration.get_user")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_a_changed_max_heart_rate_is_reflected_on_the_next_read(self, mock_gate, mock_crud, mock_get_user, parent):
        """The regression the stored design had: a profile edit left old activities on the old zones."""
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = parent
        mock_crud.get_activity_stream_by_type.return_value = _hr_stream()

        mock_get_user.return_value = MagicMock(max_heart_rate=200, birthdate=None, timezone="UTC")
        before = service.get_activity_stream(5, 1, 1, MagicMock()).zone_percentages
        mock_get_user.return_value = MagicMock(max_heart_rate=150, birthdate=None, timezone="UTC")
        after = service.get_activity_stream(5, 1, 1, MagicMock()).zone_percentages

        assert before != after

    @patch("modules.activities.activity_streams.service.users_integration.get_user")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_no_known_max_heart_rate_means_no_zones(self, mock_gate, mock_crud, mock_get_user, parent):
        from modules.activities.activity_streams import service

        mock_get_user.return_value = MagicMock(max_heart_rate=None, birthdate=None, timezone="UTC")
        mock_gate.resolve_readable_parent.return_value = parent
        mock_crud.get_activity_stream_by_type.return_value = _hr_stream()

        assert service.get_activity_stream(5, 1, 1, MagicMock()).zone_percentages is None

    @patch("modules.activities.activity_streams.service.users_integration.get_user")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_the_owner_is_looked_up_once_and_only_for_hr(self, mock_gate, mock_crud, mock_get_user, parent):
        from modules.activities.activity_streams import service

        mock_get_user.return_value = MagicMock(max_heart_rate=200, birthdate=None, timezone="UTC")
        mock_gate.resolve_readable_parent.return_value = parent
        mock_crud.get_activity_streams.return_value = [_hr_stream(), _stream(2), _stream(3)]

        page = service.list_activity_streams(5, 1, MagicMock())

        mock_get_user.assert_called_once()
        assert [s.zone_percentages is not None for s in page.items] == [True, False, False]

        mock_get_user.reset_mock()
        mock_crud.get_activity_streams.return_value = [_stream(2), _stream(3)]
        service.list_activity_streams(5, 1, MagicMock())
        mock_get_user.assert_not_called()

    @patch("modules.activities.activity_streams.service.users_integration.get_user")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_a_stream_hidden_from_the_viewer_is_never_computed(self, mock_gate, mock_crud, mock_get_user, parent):
        from modules.activities.activity_streams import service

        parent.user_id = 99
        parent.hide_hr = True
        mock_gate.resolve_readable_parent.return_value = parent
        mock_crud.get_activity_streams.return_value = [_hr_stream()]

        page = service.list_activity_streams(5, 1, MagicMock())

        assert page.items == []
        mock_get_user.assert_not_called()

    @patch("modules.activities.activity_streams.service.users_integration.get_user")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_integration")
    def test_a_public_viewer_gets_the_owners_zones(self, mock_gate, mock_crud, mock_get_user, parent):
        from modules.activities.activity_streams import service

        parent.hide_hr = False
        mock_get_user.return_value = MagicMock(max_heart_rate=200, birthdate=None, timezone="UTC")
        mock_gate.resolve_public_parent.return_value = parent
        mock_crud.get_activity_stream_by_type.return_value = _hr_stream()

        assert service.get_public_activity_stream(5, 1, MagicMock()).zone_percentages is not None
