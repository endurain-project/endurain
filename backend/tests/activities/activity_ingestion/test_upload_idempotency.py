"""Tests for Idempotency-Key handling on activity upload."""

from unittest.mock import ANY, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.service as ingestion_jobs
import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service

_UPLOAD = activity_ingestion_constants.IngestionJobKind.UPLOAD


def _upload(filename: str = "ride.gpx") -> tuple[str, MagicMock]:
    """The client filename and the router-bound saver ``accept_upload`` takes."""
    return filename, MagicMock()


def _received(fingerprint: str = "hash-of-this-file") -> upload_entry_service.ReceivedUpload:
    return upload_entry_service.ReceivedUpload(
        incoming_path="/incoming/x.gpx", storage_key="abc.gpx", fingerprint=fingerprint
    )


def _integrity_error() -> IntegrityError:
    return IntegrityError("insert", {}, Exception("duplicate key"))


class TestReplay:
    def test_a_replay_returns_the_original_job_without_storing_or_parsing_again(self):
        """The content dedup would catch the duplicate, but only after both costs."""
        db = MagicMock()
        original = MagicMock(id="job-1")
        with (
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received()
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud,
                "get_job_for_idempotency",
                return_value=(original, "hash-of-this-file"),
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload") as store,
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_received_upload") as discard,
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
        ):
            result = ingestion_jobs.accept_upload(7, *_upload(), "storage", db, idempotency_key="key-1")

        assert result is original
        store.assert_not_called()
        create.assert_not_called()
        # The received bytes are dropped rather than left in the incoming dir.
        discard.assert_called_once()

    def test_the_lookup_is_scoped_to_the_caller_and_the_job_kind(self):
        """Otherwise one user could discover another's job, or a refresh key could collide."""
        db = MagicMock()
        with (
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received()
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "get_job_for_idempotency", return_value=None
            ) as lookup,
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            ingestion_jobs.accept_upload(7, *_upload(), "storage", db, idempotency_key="key-1")

        assert lookup.call_args.args == ("key-1", 7, _UPLOAD, db)

    def test_the_key_and_fingerprint_are_both_stored(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received("fp-1")
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_for_idempotency", return_value=None),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(ingestion_jobs.activity_ingestion_event_publishers.platform_publisher, "publish_committing"),
        ):
            ingestion_jobs.accept_upload(7, *_upload(), "storage", db, idempotency_key="key-1")

        assert create.call_args.kwargs["idempotency_key"] == "key-1"
        assert create.call_args.kwargs["request_fingerprint"] == "fp-1"


class TestKeyReuseWithDifferentContent:
    def test_is_rejected_rather_than_silently_dropping_the_file(self):
        """Returning the first job would report success for a file never imported."""
        db = MagicMock()
        with (
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service,
                "receive_upload",
                return_value=_received("fp-second"),
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud,
                "get_job_for_idempotency",
                return_value=(MagicMock(id="job-1"), "fp-first"),
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_received_upload") as discard,
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload") as store,
            pytest.raises(core_exceptions.ConflictError),
        ):
            ingestion_jobs.accept_upload(7, *_upload(), "storage", db, idempotency_key="key-1")

        store.assert_not_called()
        discard.assert_called_once()

    def test_the_conflict_maps_to_409(self):
        assert core_exceptions.ConflictError.status_code == 409


class TestDeletedActivities:
    def _accept(self, original, existing_ids, fingerprint="hash-of-this-file", release=None):
        db = MagicMock()
        release = release or MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received()
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud,
                "get_job_for_idempotency",
                return_value=(original, fingerprint),
            ),
            patch.object(
                ingestion_jobs.activity_integration, "filter_existing_activity_ids", return_value=existing_ids
            ) as existing,
            patch.object(ingestion_jobs.activity_ingestion_crud, "release_idempotency_key", release),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_received_upload"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job"),
            patch.object(ingestion_jobs.activity_ingestion_dispatch_service, "commit_or_publish"),
            patch.object(ingestion_jobs.activity_ingestion_dispatch_service, "run_in_background"),
        ):
            ingestion_jobs.accept_upload(7, *_upload(), "storage", db, idempotency_key="key-1")
        return existing, release, create

    @staticmethod
    def _job(status, activity_ids):
        return MagicMock(id="job-1", status=status, activity_ids=activity_ids)

    def test_the_key_is_released_and_the_file_imported_again(self):
        original = self._job(activity_ingestion_constants.IngestionJobStatus.COMPLETED, [1, 2])
        _, release, create = self._accept(original, set())

        release.assert_called_once_with("job-1", ANY)
        create.assert_called_once()

    def test_a_surviving_activity_keeps_the_replay(self):
        original = self._job(activity_ingestion_constants.IngestionJobStatus.COMPLETED, [1, 2])
        _, release, create = self._accept(original, {2})

        release.assert_not_called()
        create.assert_not_called()

    def test_different_content_conflicts_instead_of_releasing_the_key(self):
        original = self._job(activity_ingestion_constants.IngestionJobStatus.COMPLETED, [1, 2])
        release = MagicMock()
        with pytest.raises(core_exceptions.ConflictError):
            self._accept(original, set(), fingerprint="hash-of-another-file", release=release)

        release.assert_not_called()

    @pytest.mark.parametrize(
        ("status", "activity_ids"),
        [
            (activity_ingestion_constants.IngestionJobStatus.PENDING, None),
            (activity_ingestion_constants.IngestionJobStatus.FAILED, None),
            (activity_ingestion_constants.IngestionJobStatus.COMPLETED, []),
        ],
    )
    def test_a_job_that_created_nothing_is_not_checked(self, status, activity_ids):
        existing, release, create = self._accept(self._job(status, activity_ids), set())

        existing.assert_not_called()
        release.assert_not_called()
        create.assert_not_called()


class TestConcurrentSameKey:
    def test_the_loser_reports_the_winners_job(self):
        """The constraint decides, not the read-then-write check above it."""
        db = MagicMock()
        winner = MagicMock(id="job-1")
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received("fp-1")
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud,
                "get_job_for_idempotency",
                side_effect=[None, (winner, "fp-1")],
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "create_ingestion_job", side_effect=_integrity_error()
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload") as discard,
        ):
            result = ingestion_jobs.accept_upload(7, *_upload(), "storage", db, idempotency_key="key-1")

        assert result is winner
        discard.assert_called_once_with("abc.gpx", ANY)
        db.rollback.assert_called_once()

    def test_a_racing_key_reuse_with_different_content_still_conflicts(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service,
                "receive_upload",
                return_value=_received("fp-second"),
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud,
                "get_job_for_idempotency",
                side_effect=[None, (MagicMock(id="job-1"), "fp-first")],
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "create_ingestion_job", side_effect=_integrity_error()
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload"),
            pytest.raises(core_exceptions.ConflictError),
        ):
            ingestion_jobs.accept_upload(7, *_upload(), "storage", db, idempotency_key="key-1")

    def test_an_integrity_error_without_a_key_still_propagates(self):
        """Only a key collision is recoverable; anything else is a real failure."""
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received()
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "create_ingestion_job", side_effect=_integrity_error()
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload"),
            pytest.raises(IntegrityError),
        ):
            ingestion_jobs.accept_upload(7, *_upload(), "storage", db)


class TestWithoutAKey:
    def test_no_lookup_happens_and_nothing_is_stored_on_the_job(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received("fp-1")
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_for_idempotency") as lookup,
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            ingestion_jobs.accept_upload(7, *_upload(), "storage", db)

        lookup.assert_not_called()
        assert create.call_args.kwargs["idempotency_key"] is None
        # The fingerprint is still recorded, so a later key could be validated.
        assert create.call_args.kwargs["request_fingerprint"] == "fp-1"


class TestRefreshIsUnaffected:
    def test_a_refresh_never_carries_an_idempotency_key(self):
        """The header is upload-only; a refresh has no body to replay."""
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(ingestion_jobs.activity_ingestion_event_publishers.platform_publisher, "publish_committing"),
        ):
            ingestion_jobs.accept_refresh(7, "storage", db)

        assert create.call_args.args[2] == activity_ingestion_constants.IngestionJobKind.REFRESH
        assert "idempotency_key" not in create.call_args.kwargs


class TestReceivedUploadIsNeverLeftBehind:
    def test_a_failing_idempotency_lookup_discards_the_received_upload(self):
        from unittest.mock import MagicMock, patch

        import pytest

        import modules.activities.activity_ingestion.service as ingestion_jobs

        received = _received()
        with (
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=received
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "get_job_for_idempotency", side_effect=RuntimeError("db down")
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_received_upload") as discard,
            pytest.raises(RuntimeError),
        ):
            ingestion_jobs.accept_upload(7, "ride.gpx", MagicMock(), "storage", MagicMock(), idempotency_key="k")

        discard.assert_called_once_with(received)
