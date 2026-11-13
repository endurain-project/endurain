"""Tests for the activities' section of the profile data export."""

import uuid
from collections.abc import Iterable, Sequence
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.storage_local import LocalStorage
from jasil.providers import StorageBackendUnavailableError
from pydantic import BaseModel
from sqlalchemy.orm import Session

import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_profile_transfer.export_service as export_service
import modules.users.users_profile.contracts as users_profile_contracts
from modules.users.users_profile.exceptions import MemoryAllocationError

_A, _B, _C = (uuid.UUID(int=n) for n in (1, 2, 3))


class _Row(BaseModel):
    id: uuid.UUID | None = None


class _FakeArchive:
    """Record what a section writes, with the counting rule of the real archive writer."""

    def __init__(self, counts: dict[str, int]) -> None:
        self.entries: dict[str, list[dict] | bytes] = {}
        self._counts = counts

    def _record(self, path: str, rows: list[dict]) -> None:
        self.entries[path] = rows
        self._counts[path.split("/")[-1].replace(".json", "")] = len(rows)

    def write_json(self, path: str, records: Sequence[BaseModel]) -> None:
        self._record(path, [r.model_dump(mode="json") for r in records])

    def write_json_stream(self, path: str, batches: Iterable[Sequence[BaseModel]]) -> None:
        self._record(path, [r.model_dump(mode="json") for batch in batches for r in batch])

    def write_bytes(self, path: str, data: bytes) -> None:
        self.entries[path] = data


def _ctx(batch_size: int = 10, storage=None, db=None, check_memory=None, check_timeout=None):
    counts: dict[str, int] = {}
    archive = _FakeArchive(counts)
    ctx = users_profile_contracts.ProfileExportContext(
        user_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        db=db or MagicMock(spec=Session),
        storage=storage or MagicMock(),
        archive=archive,
        counts=counts,
        batch_size=batch_size,
        check_memory=check_memory or MagicMock(),
        check_timeout=check_timeout if check_timeout is not None else MagicMock(),
    )
    return ctx, archive


def _no_contributors():
    return (
        patch.object(export_service.activities_contributor_registry, "profile_activity_contributors", return_value=()),
        patch.object(export_service.activities_contributor_registry, "profile_global_contributors", return_value=()),
    )


class TestExportProfile:
    def test_no_activities_writes_an_empty_array_and_no_files_step(self) -> None:
        ctx, archive = _ctx()
        activity_patch, global_patch = _no_contributors()
        with (
            patch.object(export_service, "_get_activities_batch", return_value=[]),
            activity_patch,
            global_patch,
        ):
            files = export_service.export_profile(ctx)

        assert files is None
        assert archive.entries["data/activities.json"] == []
        assert ctx.counts["activities"] == 0

    def test_the_section_reports_every_count_it_owns_even_when_empty(self) -> None:
        import module_registry
        import modules.activities.contributor_registry as registry

        module_registry.configure_activity_contributors()
        ctx, _ = _ctx()
        with patch.object(export_service, "_get_activities_batch", return_value=[]):
            export_service.export_profile(ctx)

        expected = {"activities", "activity_files", "media"}
        expected |= {c.count_key for c in registry.profile_activity_contributors()}
        expected |= {c.count_key for c in registry.profile_global_contributors()}
        assert expected <= set(ctx.counts)
        assert all(ctx.counts[key] == 0 for key in expected)

    def test_activities_are_streamed_in_batches_and_files_are_deferred(self) -> None:
        ctx, archive = _ctx(batch_size=2)
        batches = [[_Row(id=_A), _Row(id=_B)], [_Row(id=_C)], []]
        activity_patch, global_patch = _no_contributors()
        with (
            patch.object(export_service, "_get_activities_batch", side_effect=batches),
            patch.object(export_service, "_write_activity_components") as components,
            patch.object(export_service, "_write_activity_files") as files,
            patch.object(export_service, "_write_activity_media") as media,
            activity_patch,
            global_patch,
        ):
            after_commit = export_service.export_profile(ctx)

            assert archive.entries["data/activities.json"] == [{"id": str(_A)}, {"id": str(_B)}, {"id": str(_C)}]
            assert ctx.counts["activities"] == 3
            components.assert_called_once_with(ctx, [_A, _B, _C])
            files.assert_not_called()
            assert after_commit is not None
            after_commit()
            files.assert_called_once_with(ctx, [_A, _B, _C])
            media.assert_called_once_with(ctx, [_A, _B, _C])

    def test_the_time_limit_is_checked_between_the_files_and_the_media(self) -> None:
        calls = MagicMock()
        ctx, _ = _ctx(check_timeout=calls.check_timeout)
        activity_patch, global_patch = _no_contributors()
        with (
            patch.object(export_service, "_get_activities_batch", side_effect=[[_Row(id=_A)], []]),
            patch.object(export_service, "_write_activity_components"),
            patch.object(export_service, "_write_activity_files", calls.files),
            patch.object(export_service, "_write_activity_media", calls.media),
            activity_patch,
            global_patch,
        ):
            after_commit = export_service.export_profile(ctx)
            assert after_commit is not None
            after_commit()

        assert [name for name, *_ in calls.mock_calls] == ["files", "check_timeout", "media"]

    def test_the_first_memory_check_keeps_its_operation_name(self) -> None:
        check_memory = MagicMock()
        ctx, _ = _ctx(check_memory=check_memory)
        activity_patch, global_patch = _no_contributors()
        with patch.object(export_service, "_get_activities_batch", return_value=[]), activity_patch, global_patch:
            export_service.export_profile(ctx)

        check_memory.assert_called_once_with("activity collection start")

    def test_a_batch_is_written_before_the_next_one_is_read(self) -> None:
        order: list[str] = []
        ctx, archive = _ctx(batch_size=1)

        def fetch(user_id, offset, limit, db):
            order.append(f"fetch{offset}")
            return [_Row(id=uuid.UUID(int=offset + 1))] if offset < 2 else []

        original = archive.write_json_stream

        def stream(path, batches):
            def tracked():
                for batch in batches:
                    order.append(f"batch{batch[0].id.int}")
                    yield batch

            original(path, tracked())

        archive.write_json_stream = stream  # type: ignore[method-assign]
        activity_patch, global_patch = _no_contributors()
        with (
            patch.object(export_service, "_get_activities_batch", side_effect=fetch),
            patch.object(export_service, "_write_activity_components"),
            activity_patch,
            global_patch,
        ):
            export_service.export_profile(ctx)

        assert order == ["fetch0", "batch1", "fetch1", "batch2", "fetch2"]

    def test_get_activities_batch_pages_through_the_activity_surface(self) -> None:
        with patch(
            "modules.activities.activity_profile_transfer.export_service.activity_integration.list_user_activities_page",
            return_value=[_Row(id=_A)],
        ) as listing:
            result = export_service._get_activities_batch(1, 4, 2, MagicMock(spec=Session))

        assert result[0].id == _A
        assert listing.call_args.kwargs == {"page_number": 3, "num_records": 2}

    def test_a_failing_batch_fails_the_export_instead_of_dropping_its_activities(self) -> None:
        ctx, _ = _ctx(batch_size=2)
        with (
            patch.object(
                export_service,
                "_get_activities_batch",
                side_effect=[[_Row(id=_A), _Row(id=_B)], ValueError("bad page")],
            ),
            patch.object(export_service, "_write_activity_components") as components,
            pytest.raises(ValueError, match="bad page"),
        ):
            export_service.export_profile(ctx)

        components.assert_not_called()

    def test_a_memory_error_from_the_check_propagates(self) -> None:
        ctx, _ = _ctx(check_memory=MagicMock(side_effect=MemoryAllocationError("oom")))
        with pytest.raises(MemoryAllocationError):
            export_service.export_profile(ctx)

    def test_activities_without_an_id_are_exported_but_get_no_components_or_files(self) -> None:
        ctx, archive = _ctx()
        activity_patch, global_patch = _no_contributors()
        with (
            patch.object(export_service, "_get_activities_batch", side_effect=[[_Row(id=None)], []]),
            patch.object(export_service, "_write_activity_components") as components,
            activity_patch,
            global_patch,
        ):
            files = export_service.export_profile(ctx)

        assert files is None
        assert ctx.counts["activities"] == 1
        assert archive.entries["data/activities.json"] == [{"id": None}]
        components.assert_not_called()

    def test_global_components_are_written_and_counted(self) -> None:
        ctx, archive = _ctx()
        contributor = MagicMock(
            key="exercise_titles", archive_path="data/activity_exercise_titles.json", count_key="titles"
        )
        contributor.export.return_value = [_Row(id=_A), _Row(id=_B)]
        with (
            patch.object(export_service, "_get_activities_batch", side_effect=[[_Row(id=_A)], []]),
            patch.object(export_service, "_write_activity_components"),
            patch.object(
                export_service.activities_contributor_registry, "profile_activity_contributors", return_value=()
            ),
            patch.object(
                export_service.activities_contributor_registry,
                "profile_global_contributors",
                return_value=(contributor,),
            ),
        ):
            export_service.export_profile(ctx)

        contributor.export.assert_called_once_with(ctx.db)
        assert len(archive.entries["data/activity_exercise_titles.json"]) == 2
        assert ctx.counts["titles"] == 2

    def test_a_failing_global_component_propagates_to_the_orchestrator(self) -> None:
        ctx, _ = _ctx()
        contributor = MagicMock(key="x", archive_path="data/x.json", count_key="x")
        contributor.export.side_effect = RuntimeError("boom")
        with (
            patch.object(export_service, "_get_activities_batch", return_value=[]),
            patch.object(
                export_service.activities_contributor_registry, "profile_activity_contributors", return_value=()
            ),
            patch.object(
                export_service.activities_contributor_registry,
                "profile_global_contributors",
                return_value=(contributor,),
            ),
            pytest.raises(RuntimeError, match="boom"),
        ):
            export_service.export_profile(ctx)


class TestWriteActivityComponents:
    def test_components_loop_calls_chunked_and_simple(self) -> None:
        import module_registry

        module_registry.configure_activity_contributors()
        ctx, _ = _ctx()
        with (
            patch.object(export_service, "_write_component_chunked") as chunked,
            patch.object(export_service, "_write_component_simple") as simple,
        ):
            export_service._write_activity_components(ctx, [_A])

        assert chunked.call_count == 3
        assert simple.call_count == 2


def _rows(n: int) -> list[_Row]:
    return [_Row(id=uuid.UUID(int=i + 1)) for i in range(n)]


def _chunked(ctx, export, activity_ids, batch_size):
    export_service._write_component_chunked(ctx, "laps", "data/activity_laps.json", export, activity_ids, batch_size)


class TestWriteComponentChunked:
    def test_a_single_batch_is_written_under_the_plain_name(self) -> None:
        ctx, archive = _ctx()
        _chunked(ctx, lambda ids, db: _rows(len(ids)), [_A, _B], 5)

        assert list(archive.entries) == ["data/activity_laps.json"]
        assert ctx.counts["laps"] == 2

    def test_full_chunks_and_the_remainder_are_numbered(self) -> None:
        ctx, archive = _ctx()
        _chunked(ctx, lambda ids, db: _rows(len(ids)), [_A, _B, _C], 2)

        assert list(archive.entries) == ["data/activity_laps_000.json", "data/activity_laps_001.json"]
        assert len(archive.entries["data/activity_laps_000.json"]) == 2
        assert len(archive.entries["data/activity_laps_001.json"]) == 1
        assert ctx.counts["laps"] == 3
        # Each part also counts under its own stem, as the legacy writer did.
        assert ctx.counts["activity_laps_000"] == 2

    def test_buffer_overflow_across_batches_writes_several_chunks(self) -> None:
        ctx, archive = _ctx()
        _chunked(ctx, lambda ids, db: _rows(len(ids) + 1) if ids else [], [_A, _B], 2)

        assert len(archive.entries) >= 2

    def test_an_empty_result_writes_an_empty_file(self) -> None:
        ctx, archive = _ctx()
        _chunked(ctx, lambda ids, db: [], [_A, _B], 5)

        assert archive.entries == {"data/activity_laps.json": []}
        assert ctx.counts["laps"] == 0

    def test_a_reader_failure_propagates(self) -> None:
        ctx, _ = _ctx()

        def fail(ids, db):
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError, match="fail"):
            _chunked(ctx, fail, [_A, _B, _C], 2)

    def test_a_memory_error_propagates_with_the_batch_operation_name(self) -> None:
        check_memory = MagicMock(side_effect=MemoryAllocationError("oom"))
        ctx, _ = _ctx(check_memory=check_memory)
        with pytest.raises(MemoryAllocationError):
            _chunked(ctx, lambda ids, db: [], [_A, _B], 5)

        check_memory.assert_called_once_with("laps batch 1")


def _simple(ctx, export, activity_ids, batch_size):
    export_service._write_component_simple(
        ctx, "steps", "data/activity_workout_steps.json", export, activity_ids, batch_size
    )


class TestWriteComponentSimple:
    def test_the_records_of_every_batch_are_written_as_one_file(self) -> None:
        ctx, archive = _ctx()
        reader = MagicMock(return_value=_rows(2))
        _simple(ctx, reader, [_A], 5)

        reader.assert_called_once()
        assert len(archive.entries["data/activity_workout_steps.json"]) == 2
        assert ctx.counts["activity_workout_steps"] == 2

    def test_a_reader_failure_propagates(self) -> None:
        ctx, _ = _ctx()

        def fail(ids, db):
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError, match="fail"):
            _simple(ctx, fail, [_A, _B, _C], 2)

    def test_a_memory_error_propagates(self) -> None:
        ctx, _ = _ctx(check_memory=MagicMock(side_effect=MemoryAllocationError("oom")))
        with pytest.raises(MemoryAllocationError):
            _simple(ctx, lambda ids, db: [], [_A], 5)

    def test_an_empty_result_writes_an_empty_file(self) -> None:
        ctx, archive = _ctx()
        _simple(ctx, lambda ids, db: [], [_A], 5)

        assert archive.entries == {"data/activity_workout_steps.json": []}


class TestActivityFiles:
    def test_none_stored(self) -> None:
        ctx, archive = _ctx()
        ctx.counts["activity_files"] = 0
        with patch.object(export_service.activity_file_storage_integration, "get_activity_file", return_value=None):
            export_service._write_activity_files(ctx, [_A])

        assert ctx.counts["activity_files"] == 0
        assert archive.entries == {}

    def test_with_files(self) -> None:
        ctx, archive = _ctx()
        ctx.counts["activity_files"] = 0
        with patch.object(
            export_service.activity_file_storage_integration,
            "get_activity_file",
            return_value=(f"{_A}.gpx", b"<gpx></gpx>"),
        ):
            export_service._write_activity_files(ctx, [_A])

        assert ctx.counts["activity_files"] == 1
        assert archive.entries[f"activity_files/{_A}.gpx"] == b"<gpx></gpx>"

    def test_reads_retained_files_from_the_plain_local_layout(self, tmp_path) -> None:
        storage = LocalStorage(
            str(tmp_path),
            plain_areas=frozenset({activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA}),
        )
        storage.save(activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, f"processed/{_A}.gpx", b"<gpx/>")
        ctx, archive = _ctx(storage=storage)
        ctx.counts["activity_files"] = 0
        export_service._write_activity_files(ctx, [_A])

        assert ctx.counts["activity_files"] == 1
        assert archive.entries[f"activity_files/{_A}.gpx"] == b"<gpx/>"

    def test_a_read_error_skips_only_that_activity(self) -> None:
        ctx, archive = _ctx()
        ctx.counts["activity_files"] = 0
        with patch.object(
            export_service.activity_file_storage_integration,
            "get_activity_file",
            side_effect=[OSError("read failed"), (f"{_B}.gpx", b"<gpx></gpx>")],
        ):
            export_service._write_activity_files(ctx, [_A, _B])

        assert ctx.counts["activity_files"] == 1
        assert list(archive.entries) == [f"activity_files/{_B}.gpx"]


class TestActivityMedia:
    def test_no_blobs(self) -> None:
        storage = MagicMock()
        storage.list_keys.return_value = []
        ctx, archive = _ctx(storage=storage)
        ctx.counts["media"] = 0
        export_service._write_activity_media(ctx, [_A])

        assert ctx.counts["media"] == 0
        assert archive.entries == {}

    def test_with_files(self) -> None:
        storage = MagicMock()
        storage.list_keys.return_value = [f"{_A}_image.jpg"]
        storage.get.return_value = b"image-bytes"
        ctx, archive = _ctx(storage=storage)
        ctx.counts["media"] = 0
        export_service._write_activity_media(ctx, [_A])

        assert ctx.counts["media"] == 1
        assert archive.entries[f"activity_media/{_A}_image.jpg"] == b"image-bytes"

    def test_a_missing_blob_is_skipped(self) -> None:
        storage = MagicMock()
        storage.list_keys.return_value = [f"{_A}_image.jpg"]
        storage.get.return_value = None
        ctx, _ = _ctx(storage=storage)
        ctx.counts["media"] = 0
        export_service._write_activity_media(ctx, [_A])

        assert ctx.counts["media"] == 0

    def test_a_failing_blob_does_not_abort_the_rest(self) -> None:
        storage = MagicMock()
        storage.list_keys.return_value = [f"{_A}_bad.jpg", f"{_A}_good.jpg"]
        storage.get.side_effect = [StorageBackendUnavailableError("backend down"), b"good-bytes"]
        ctx, archive = _ctx(storage=storage)
        ctx.counts["media"] = 0
        export_service._write_activity_media(ctx, [_A])

        assert ctx.counts["media"] == 1
        assert archive.entries[f"activity_media/{_A}_good.jpg"] == b"good-bytes"

    def test_a_listing_failure_skips_that_activity_only(self) -> None:
        storage = MagicMock()
        storage.list_keys.side_effect = StorageBackendUnavailableError("permission denied")
        ctx, _ = _ctx(storage=storage)
        ctx.counts["media"] = 0
        export_service._write_activity_media(ctx, [_A])

        assert ctx.counts["media"] == 0
