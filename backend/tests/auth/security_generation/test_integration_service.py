"""Tests for the security-generation surface other modules call."""

from unittest.mock import patch

import pytest

import modules.auth.security_generation.integration_service as security_generation_integration


def test_current_generation_returns_what_read_returns(mock_db):
    with patch("modules.auth.security_generation.crud.read", return_value=5) as read:
        assert security_generation_integration.current_generation(3, mock_db) == 5
    read.assert_called_once_with(3, mock_db)


def test_stage_bump_stages_through_crud_without_committing(mock_db):
    with patch("modules.auth.security_generation.crud.bump") as bump:
        security_generation_integration.stage_bump(3, mock_db)
    bump.assert_called_once_with(3, mock_db)
    mock_db.commit.assert_not_called()


@pytest.mark.parametrize(
    ("stamped", "locked", "expected"),
    [(2, 2, True), (0, 0, True), (1, 2, False), (2, 1, False)],
)
def test_matches_locked_compares_the_stamp_with_the_locked_generation(mock_db, stamped, locked, expected):
    with patch("modules.auth.security_generation.crud.lock", return_value=locked) as lock:
        assert security_generation_integration.matches_locked(3, stamped, mock_db) is expected
    lock.assert_called_once_with(3, mock_db)


def test_matches_locked_refuses_a_proof_without_a_stamp_without_locking(mock_db):
    with patch("modules.auth.security_generation.crud.lock") as lock:
        assert security_generation_integration.matches_locked(3, None, mock_db) is False
    lock.assert_not_called()
