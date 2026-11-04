"""Tests for the activity collection of the profile data export."""

import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import modules.users.users_profile.export_activity_service as export_activity_service
import modules.users.users_profile.export_service as profile_export_service
import modules.users.users_profile.utils as profile_utils
from modules.users.users_profile.exceptions import (
    DatabaseConnectionError,
    DataCollectionError,
    MemoryAllocationError,
)

_MODULE = "modules.users.users_profile.export_activity_service"


def _make_activity_mock(activity_id: int) -> MagicMock:
    m = MagicMock()
    m.id = activity_id
    return m


def _config(batch_size: int = 10) -> profile_export_service.ExportPerformanceConfig:
    config = profile_export_service.ExportPerformanceConfig()
    config.batch_size = batch_size
    config.enable_memory_monitoring = False
    return config


def _counts() -> dict[str, int]:
    return profile_utils.initialize_operation_counts(include_user_count=True)


def _collect(z, config, counts, db=None):
    return export_activity_service.collect_user_activities_data(z, 1, counts, config, db or MagicMock(spec=Session))


def _read_json(buf: io.BytesIO, name: str):
    buf.seek(0)
    with zipfile.ZipFile(buf) as archive:
        return json.loads(archive.read(name))


class TestCollectUserActivities:
    def test_no_activities_writes_an_empty_array(self) -> None:
        buf = io.BytesIO()
        counts = _counts()
        db = MagicMock(spec=Session)
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(export_activity_service, "_get_activities_batch", return_value=[]),
            patch.object(export_activity_service, "_collect_and_write_global_activity_components") as collect_global,
        ):
            result = _collect(z, _config(), counts, db)

        assert result == []
        assert _read_json(buf, "data/activities.json") == []
        assert counts["activities"] == 0
        collect_global.assert_called_once_with(z, counts, db)

    def test_activities_are_streamed_in_batches_and_only_their_ids_are_kept(self) -> None:
        buf = io.BytesIO()
        counts = _counts()
        config = _config(batch_size=2)
        db = MagicMock(spec=Session)
        batches = [[_make_activity_mock(1), _make_activity_mock(2)], [_make_activity_mock(3)], []]

        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(export_activity_service, "_get_activities_batch", side_effect=batches),
            patch.object(profile_utils, "model_to_dict", side_effect=lambda a: {"id": a.id}),
            patch.object(export_activity_service, "_collect_and_write_activity_components") as components,
            patch.object(export_activity_service, "_collect_and_write_global_activity_components"),
        ):
            result = _collect(z, config, counts, db)

        assert result == [1, 2, 3]
        assert _read_json(buf, "data/activities.json") == [{"id": 1}, {"id": 2}, {"id": 3}]
        assert counts["activities"] == 3
        components.assert_called_once_with(z, [1, 2, 3], counts, config, db)

    def test_the_archive_entry_keeps_the_format_an_in_memory_dump_wrote(self) -> None:
        buf = io.BytesIO()
        rows = [{"id": 1, "name": "Corrida ☀"}, {"id": 2, "name": "x"}, {"id": 3, "name": "y"}]
        batches = [[_make_activity_mock(1), _make_activity_mock(2)], [_make_activity_mock(3)], []]

        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(export_activity_service, "_get_activities_batch", side_effect=batches),
            patch.object(profile_utils, "model_to_dict", side_effect=lambda a: rows[a.id - 1]),
            patch.object(export_activity_service, "_collect_and_write_activity_components"),
            patch.object(export_activity_service, "_collect_and_write_global_activity_components"),
        ):
            _collect(z, _config(batch_size=2), _counts())

        buf.seek(0)
        with zipfile.ZipFile(buf) as archive:
            raw = archive.read("data/activities.json").decode()
        assert raw == json.dumps(rows, default=str, ensure_ascii=False)

    def test_a_batch_is_written_before_the_next_one_is_read(self) -> None:
        """Activities are never all held at once: each batch is converted as it arrives."""
        buf = io.BytesIO()
        order: list[str] = []

        def fetch(user_id, offset, limit, db):
            order.append(f"fetch{offset}")
            return [_make_activity_mock(offset + 1)] if offset < 2 else []

        def convert(activity):
            order.append(f"convert{activity.id}")
            return {"id": activity.id}

        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(export_activity_service, "_get_activities_batch", side_effect=fetch),
            patch.object(profile_utils, "model_to_dict", side_effect=convert),
            patch.object(export_activity_service, "_collect_and_write_activity_components"),
            patch.object(export_activity_service, "_collect_and_write_global_activity_components"),
        ):
            _collect(z, _config(batch_size=1), _counts())

        assert order == ["fetch0", "convert1", "fetch1", "convert2", "fetch2"]

    def test_get_activities_batch_calls_crud_and_returns_activities(self) -> None:
        mock_db = MagicMock(spec=Session)
        mock_activity = _make_activity_mock(1)

        with patch(
            f"{_MODULE}.activity_integration.list_user_activities_page",
            return_value=[mock_activity],
        ):
            result = export_activity_service._get_activities_batch(1, 0, 10, mock_db)

        assert len(result) == 1
        assert result[0].id == 1

    def test_get_activities_batch_raises_on_exception(self) -> None:
        mock_db = MagicMock(spec=Session)

        with (
            patch(
                f"{_MODULE}.activity_integration.list_user_activities_page",
                side_effect=Exception("db error"),
            ),
            pytest.raises(Exception, match="db error"),
        ):
            export_activity_service._get_activities_batch(1, 0, 10, mock_db)

    def test_a_failing_batch_fails_the_export_instead_of_dropping_its_activities(self) -> None:
        buf = io.BytesIO()

        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(
                export_activity_service,
                "_get_activities_batch",
                side_effect=[[_make_activity_mock(1), _make_activity_mock(2)], ValueError("bad page")],
            ),
            patch.object(profile_utils, "model_to_dict", side_effect=lambda a: {"id": a.id}),
            patch.object(export_activity_service, "_collect_and_write_activity_components") as components,
            pytest.raises(DataCollectionError, match="bad page"),
        ):
            _collect(z, _config(batch_size=2), _counts())

        components.assert_not_called()

    def test_activities_batch_sqlalchemy_error_propagates(self) -> None:
        """SQLAlchemyError from a batch propagates as DatabaseConnectionError."""
        buf = io.BytesIO()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(
                export_activity_service,
                "_get_activities_batch",
                side_effect=SQLAlchemyError("db down"),
            ),
            patch.object(export_activity_service, "_collect_and_write_activity_components"),
            pytest.raises(DatabaseConnectionError),
        ):
            _collect(z, _config(), _counts())

    def test_get_activities_batch_memory_error_propagates(self) -> None:
        """MemoryAllocationError from a batch propagates through batch loop."""
        buf = io.BytesIO()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(
                export_activity_service,
                "_get_activities_batch",
                side_effect=MemoryAllocationError("oom"),
            ),
            patch.object(export_activity_service, "_collect_and_write_activity_components"),
            pytest.raises(MemoryAllocationError),
        ):
            _collect(z, _config(), _counts())

    def test_component_data_collection_error_propagates_unwrapped(self) -> None:
        """DataCollectionError from component processing propagates unwrapped."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            activity = _make_activity_mock(1)

            with (
                patch.object(export_activity_service, "_get_activities_batch", side_effect=[[activity], []]),
                patch.object(profile_utils, "model_to_dict", return_value={"id": 1}),
                patch.object(
                    export_activity_service,
                    "_collect_and_write_activity_components",
                    side_effect=DataCollectionError("component failure"),
                ),
                pytest.raises(DataCollectionError, match="component failure"),
            ):
                _collect(z, _config(), _counts())


class TestCollectUserActivitiesEdgeCases:
    def test_no_valid_activity_ids(self) -> None:
        """Activities collected but all have None IDs."""
        buf = io.BytesIO()
        counts = _counts()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            activity = MagicMock()
            activity.id = None

            with (
                patch.object(export_activity_service, "_get_activities_batch", side_effect=[[activity], []]),
                patch.object(profile_utils, "model_to_dict", return_value={"id": None}),
                patch.object(export_activity_service, "_collect_and_write_activity_components") as components,
            ):
                result = _collect(z, _config(), counts)

        # The row is still exported; with no usable id there is nothing to attach components or files to.
        assert result == []
        assert counts["activities"] == 1
        components.assert_not_called()

    def test_exercise_titles_collected_successfully(self) -> None:
        """Exercise titles collected and written."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_db = MagicMock(spec=Session)
            activity = _make_activity_mock(1)
            contributor = MagicMock(
                key="exercise_titles",
                archive_path="data/activity_exercise_titles.json",
                count_key="activity_exercise_titles",
            )
            contributor.export.return_value = [MagicMock(), MagicMock()]

            with (
                patch.object(export_activity_service, "_get_activities_batch", side_effect=[[activity], []]),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(export_activity_service, "_collect_and_write_activity_components"),
                patch.object(
                    export_activity_service.activities_contributor_registry,
                    "profile_global_contributors",
                    return_value=(contributor,),
                ),
                patch.object(profile_utils, "model_to_dict", return_value={"title": "t"}),
            ):
                _collect(z, _config(), _counts(), mock_db)

            contributor.export.assert_called_once_with(mock_db)

    def test_exercise_titles_collection_exception_raises(self) -> None:
        """Exception during exercise titles raises DataCollectionError."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            activity = _make_activity_mock(1)
            contributor = MagicMock(
                key="exercise_titles",
                archive_path="data/activity_exercise_titles.json",
                count_key="activity_exercise_titles",
            )
            contributor.export.side_effect = Exception("boom")

            with (
                patch.object(export_activity_service, "_get_activities_batch", side_effect=[[activity], []]),
                patch.object(profile_utils, "write_json_to_zip"),
                patch.object(export_activity_service, "_collect_and_write_activity_components"),
                patch.object(
                    export_activity_service.activities_contributor_registry,
                    "profile_global_contributors",
                    return_value=(contributor,),
                ),
                pytest.raises(DataCollectionError),
            ):
                _collect(z, _config(), _counts())


class TestCollectActivityComponents:
    def test_components_loop_calls_chunked_and_simple(self) -> None:
        """Both splittable and non-splittable component paths executed."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            with (
                patch.object(export_activity_service, "_collect_and_write_component_chunked") as mock_chunked,
                patch.object(export_activity_service, "_collect_and_write_component_simple") as mock_simple,
                patch.object(profile_utils, "write_json_to_zip"),
            ):
                export_activity_service._collect_and_write_activity_components(
                    z, [1], _counts(), _config(), MagicMock(spec=Session)
                )

            assert mock_chunked.call_count == 3
            assert mock_simple.call_count == 2


def _chunked(z, crud, activity_ids, batch_size, config=None):
    export_activity_service._collect_and_write_component_chunked(
        z,
        "laps",
        "data/activity_laps.json",
        crud,
        activity_ids,
        batch_size,
        _counts(),
        config or _config(),
        MagicMock(spec=Session),
    )


class TestCollectComponentChunkedDetailed:
    def test_chunked_single_batch_all_written_at_once(self) -> None:
        """Single batch fits in one write; file_counter==0 path."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            with (
                patch.object(profile_utils, "model_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip") as mock_write,
            ):
                _chunked(z, lambda ids, db: [MagicMock()] * len(ids) if ids else [], [1, 2], 5)

            mock_write.assert_called_once()
            args = mock_write.call_args[0]
            assert args[1] == "data/activity_laps.json"

    def test_chunked_multiple_chunks_written(self) -> None:
        """Buffer exceeds max_items_per_file, multiple chunk files."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            with (
                patch.object(profile_utils, "model_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip") as mock_write,
            ):
                _chunked(z, lambda ids, db: [MagicMock()] * (len(ids) + 1) if ids else [], [1, 2], 2)

            assert mock_write.call_count >= 2

    def test_chunked_remaining_buffer_written(self) -> None:
        """Remaining items at end written with numbered filename."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            with (
                patch.object(profile_utils, "model_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip") as mock_write,
            ):
                _chunked(
                    z, lambda ids, db: [MagicMock()] * len(ids) if ids else [], [1, 2, 3], 2, _config(batch_size=4)
                )

            assert mock_write.call_count == 2

    def test_chunked_empty_result_writes_empty_file(self) -> None:
        """No items collected -> empty file written."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            with patch.object(profile_utils, "write_json_to_zip") as mock_write:
                _chunked(z, lambda ids, db: [], [1, 2], 5)

            mock_write.assert_called_once()
            args = mock_write.call_args[0]
            assert args[1] == "data/activity_laps.json"
            assert args[2] == []

    def test_chunked_crud_exception_raises_data_collection_error(self) -> None:
        """CRUD exception raises DataCollectionError."""
        buf = io.BytesIO()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(profile_utils, "model_to_dict", return_value={"id": 1}),
            patch.object(profile_utils, "write_json_to_zip"),
            pytest.raises(DataCollectionError),
        ):
            _chunked(z, lambda ids, db: (_ for _ in ()).throw(Exception("fail")), [1, 2, 3], 2)

    def test_chunked_memory_error_propagates(self) -> None:
        """MemoryAllocationError from check_memory_usage propagates."""
        buf = io.BytesIO()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(
                profile_utils,
                "check_memory_usage",
                side_effect=MemoryAllocationError("oom"),
            ),
            pytest.raises(MemoryAllocationError),
        ):
            _chunked(z, lambda ids, db: [], [1, 2], 5)


def _simple(z, crud, activity_ids, batch_size, config=None):
    export_activity_service._collect_and_write_component_simple(
        z,
        "steps",
        "data/activity_workout_steps.json",
        crud,
        activity_ids,
        batch_size,
        _counts(),
        config or _config(),
        MagicMock(spec=Session),
    )


class TestCollectComponentSimpleDetailed:
    def test_simple_with_data(self) -> None:
        """Component data collected and written."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            mock_crud = MagicMock(return_value=[MagicMock(), MagicMock()])
            captured = []

            def capture_write(zipf, filename, data, counts):
                captured[:] = data

            with (
                patch.object(profile_utils, "model_to_dict", return_value={"id": 1}),
                patch.object(profile_utils, "write_json_to_zip", side_effect=capture_write) as mock_write,
            ):
                _simple(z, mock_crud, [1], 5)

            mock_crud.assert_called_once()
            mock_write.assert_called_once()
            assert len(captured) == 2

    def test_simple_crud_exception_raises_data_collection_error(self) -> None:
        """CRUD exception raises DataCollectionError."""
        buf = io.BytesIO()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(profile_utils, "model_to_dict", return_value={"id": 1}),
            patch.object(profile_utils, "write_json_to_zip"),
            pytest.raises(DataCollectionError),
        ):
            _simple(
                z,
                lambda ids, db: (_ for _ in ()).throw(Exception("fail")),
                [1, 2, 3],
                2,
                _config(batch_size=2),
            )

    def test_simple_memory_error_propagates(self) -> None:
        """MemoryAllocationError from check_memory_usage propagates."""
        buf = io.BytesIO()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch.object(
                profile_utils,
                "check_memory_usage",
                side_effect=MemoryAllocationError("oom"),
            ),
            pytest.raises(MemoryAllocationError),
        ):
            _simple(z, lambda ids, db: [], [1], 5)

    def test_simple_empty_result_writes_empty_file(self) -> None:
        """No data collected -> empty file written."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            with patch.object(profile_utils, "write_json_to_zip") as mock_write:
                _simple(z, lambda ids, db: [], [1], 5)

            mock_write.assert_called_once()
            args = mock_write.call_args[0]
            assert args[2] == []
