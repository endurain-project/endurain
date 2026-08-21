"""Tests for the activity streams service layer.

Streams mask per stream *type* rather than by a single parent flag, so unlike the
sibling child resources this service resolves the parent activity and filters.
"""

from unittest.mock import MagicMock, patch


def _stream(stream_type: int):
    return MagicMock(stream_type=stream_type)


class TestListActivityStreams:
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_owner_gets_every_stream_unfiltered(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        streams = [_stream(1), _stream(2)]
        mock_gate.resolve_readable_parent.return_value = MagicMock(user_id=1)
        mock_crud.get_activity_streams.return_value = streams

        assert service.list_activity_streams(5, 1, MagicMock()) == streams

    @patch("modules.activities.activity_streams.service.activity_streams_serializers")
    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_non_owner_gets_the_masked_set(self, mock_gate, mock_crud, mock_serializers):
        from modules.activities.activity_streams import service

        activity = MagicMock(user_id=2)
        mock_gate.resolve_readable_parent.return_value = activity
        mock_crud.get_activity_streams.return_value = [_stream(1)]
        mock_serializers.filter_visible_streams.return_value = []

        assert service.list_activity_streams(5, 1, MagicMock()) == []
        mock_serializers.filter_visible_streams.assert_called_once_with(
            [mock_crud.get_activity_streams.return_value[0]], activity
        )

    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_invisible_activity_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        mock_gate.resolve_readable_parent.return_value = None

        assert service.list_activity_streams(5, 1, MagicMock()) == []
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

        assert service.list_public_activity_streams(5, MagicMock()) == []
        mock_serializers.filter_visible_streams.assert_called_once()

    @patch("modules.activities.activity_streams.service.activity_streams_crud")
    @patch("modules.activities.activity_streams.service.activity_child_access")
    def test_non_public_activity_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_streams import service

        mock_gate.resolve_public_parent.return_value = None

        assert service.list_public_activity_streams(5, MagicMock()) == []
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
