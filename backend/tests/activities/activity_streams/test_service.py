"""Tests for the activity streams service layer.

Streams mask per stream *type* rather than by a single parent flag, so unlike the
sibling child resources this service resolves the parent activity and filters,
then cuts the masked result into the shared page envelope.
"""

from unittest.mock import MagicMock, patch

import modules.activities.activity_streams.schema as activity_streams_schema


def _stream(stream_type: int):
    return activity_streams_schema.ActivityStreamsRead(
        id=stream_type,
        activity_id=5,
        stream_type=stream_type,
        stream_waypoints=[],
    )


class TestListActivityStreams:
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_owner_gets_every_stream_unfiltered(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        streams = [_stream(1), _stream(2)]
        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=1)
        mock_crud.get_activity_streams.return_value = streams

        page = service.list_activity_streams(5, 1, MagicMock())

        assert (page.items, page.total) == (streams, 2)

    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_the_total_counts_only_what_the_page_could_hold(self, mock_gate, mock_crud):
        """The window is cut in Python, after the mask, so the total matches it."""
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=1)
        mock_crud.get_activity_streams.return_value = [_stream(1), _stream(2), _stream(3)]

        page = service.list_activity_streams(5, 1, MagicMock(), page_number=2, num_records=2)

        assert ([s.stream_type for s in page.items], page.total, page.next) == ([3], 3, None)

    @patch("modules.activities.activity_streams.service.activity_streams_serializers")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_non_owner_gets_the_masked_set(self, mock_gate, mock_crud, mock_serializers):
        from modules.activities.activity_streams import service

        activity = MagicMock(user_id=2)
        mock_gate.resolve_readable_parent.return_value = activity
        mock_crud.get_activity_streams.return_value = [_stream(1)]
        mock_serializers.filter_visible_streams.return_value = []

        page = service.list_activity_streams(5, 1, MagicMock())

        assert (page.items, page.total) == ([], 0)
        mock_serializers.filter_visible_streams.assert_called_once_with(
            [mock_crud.get_activity_streams.return_value[0]], activity
        )

    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_invisible_activity_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = None

        page = service.list_activity_streams(5, 1, MagicMock())

        assert (page.items, page.total) == ([], 0)
        mock_crud.get_activity_streams.assert_not_called()


class TestGetActivityStream:
    @patch("modules.activities.activity_streams.service.activity_streams_serializers")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_hidden_stream_is_none_for_a_non_owner(self, mock_gate, mock_crud, mock_serializers):
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=2)
        mock_crud.get_activity_stream_by_type.return_value = _stream(1)
        mock_serializers.is_stream_hidden.return_value = True

        assert service.get_activity_stream(5, 1, 1, MagicMock()) is None

    @patch("modules.activities.activity_streams.service.activity_streams_serializers")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_owner_sees_a_hidden_stream(self, mock_gate, mock_crud, mock_serializers):
        from modules.activities.activity_streams import service

        stream = _stream(1)
        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=1)
        mock_crud.get_activity_stream_by_type.return_value = stream
        mock_serializers.is_stream_hidden.return_value = True

        assert service.get_activity_stream(5, 1, 1, MagicMock()) is stream

    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_missing_stream_is_none(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=1)
        mock_crud.get_activity_stream_by_type.return_value = None

        assert service.get_activity_stream(5, 1, 1, MagicMock()) is None


class TestPublicStreams:
    @patch("modules.activities.activity_streams.service.activity_streams_serializers")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_public_list_is_always_masked(self, mock_gate, mock_crud, mock_serializers):
        """An anonymous caller is never the owner, so the mask always applies."""
        from modules.activities.activity_streams import service

        activity = MagicMock()
        mock_gate.resolve_public_parent.return_value = activity
        mock_crud.get_activity_streams.return_value = [_stream(1)]
        mock_serializers.filter_visible_streams.return_value = []

        page = service.list_public_activity_streams(5, MagicMock())

        assert (page.items, page.total) == ([], 0)
        mock_serializers.filter_visible_streams.assert_called_once()

    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_non_public_activity_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        mock_gate.resolve_public_parent.return_value = None

        page = service.list_public_activity_streams(5, MagicMock())

        assert (page.items, page.total) == ([], 0)
        assert service.get_public_activity_stream(5, 1, MagicMock()) is None
        mock_crud.get_activity_streams.assert_not_called()
        mock_crud.get_activity_stream_by_type.assert_not_called()

    @patch("modules.activities.activity_streams.service.activity_streams_serializers")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_public_hidden_stream_is_none(self, mock_gate, mock_crud, mock_serializers):
        from modules.activities.activity_streams import service

        mock_gate.resolve_public_parent.return_value = MagicMock()
        mock_crud.get_activity_stream_by_type.return_value = _stream(1)
        mock_serializers.is_stream_hidden.return_value = True

        assert service.get_public_activity_stream(5, 1, MagicMock()) is None
