"""An import drops the per-copy fields an archived row carries, so every section restores a fresh row."""

import modules.users.users_profile.contracts as users_profile_contracts


def test_the_id_owner_version_and_stamp_are_dropped_and_the_data_kept():
    row = {"id": 4, "user_id": 3, "version": 7, "updated_at": "2026-11-11T07:30:00Z", "weight_kg": 70}

    assert users_profile_contracts.without_row_identity(row) == {"weight_kg": 70}


def test_an_archived_integer_or_text_id_is_keyed_by_its_text():
    assert users_profile_contracts.archived_id(4) == "4"
    assert users_profile_contracts.archived_id("c0ffee00-0000-4000-8000-000000000001") == (
        "c0ffee00-0000-4000-8000-000000000001"
    )


def test_a_boolean_or_other_value_is_not_an_archived_id():
    assert users_profile_contracts.archived_id(True) is None
    assert users_profile_contracts.archived_id(None) is None
    assert users_profile_contracts.archived_id(1.5) is None
