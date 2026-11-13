"""An import drops the per-copy fields an archived row carries, so every section restores a fresh row."""

import uuid

import pytest

import modules.users.users_profile.contracts as users_profile_contracts


def test_the_id_owner_version_and_stamp_are_dropped_and_the_data_kept():
    row = {"id": 4, "user_id": 3, "version": 7, "updated_at": "2026-11-11T07:30:00Z", "weight_kg": 70}

    assert users_profile_contracts.without_row_identity(row) == {"weight_kg": 70}


def test_an_archived_uuid_string_is_keyed_by_its_uuid():
    assert users_profile_contracts.archived_id("c0ffee00-0000-4000-8000-000000000001") == uuid.UUID(
        "c0ffee00-0000-4000-8000-000000000001"
    )


@pytest.mark.parametrize("value", [True, 4, None, 1.5, "not-a-uuid", ""])
def test_a_boolean_an_integer_or_a_malformed_string_is_not_an_archived_id(value):
    assert users_profile_contracts.archived_id(value) is None
