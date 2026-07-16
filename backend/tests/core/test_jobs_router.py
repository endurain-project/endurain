"""Tests for the durable-jobs admin route handlers."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import infra.jobs.router as jobs_router


class TestReadJobsSummary:
    def test_delegates_to_crud_with_hours(self):
        fake_db = MagicMock()
        sentinel = MagicMock()
        with patch("infra.jobs.router.jobs_crud.get_jobs_summary", return_value=sentinel) as get_summary:
            result = jobs_router.read_jobs_summary(_check_scopes=None, db=fake_db, hours=12)
        assert result is sentinel
        get_summary.assert_called_once_with(fake_db, hours=12)

    def test_defaults_to_24_hours(self):
        fake_db = MagicMock()
        with patch("infra.jobs.router.jobs_crud.get_jobs_summary") as get_summary:
            jobs_router.read_jobs_summary(_check_scopes=None, db=fake_db)
        get_summary.assert_called_once_with(fake_db, hours=24)


class TestReplayDeadLetterJob:
    def test_returns_result_when_replayed(self):
        fake_db = MagicMock()
        with patch("infra.jobs.router.jobs_crud.replay_dead_letter_job", return_value=True) as replay:
            result = jobs_router.replay_dead_letter_job(job_id="j1", _check_scopes=None, db=fake_db)
        assert result.replayed is True
        assert replay.call_args.args[0] == "j1"
        assert replay.call_args.kwargs["db"] is fake_db

    def test_404_when_not_found(self):
        fake_db = MagicMock()
        with (
            patch("infra.jobs.router.jobs_crud.replay_dead_letter_job", return_value=False),
            pytest.raises(HTTPException) as excinfo,
        ):
            jobs_router.replay_dead_letter_job(job_id="nope", _check_scopes=None, db=fake_db)
        assert excinfo.value.status_code == 404
