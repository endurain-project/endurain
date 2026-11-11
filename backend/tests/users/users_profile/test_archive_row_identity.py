"""An import drops the per-copy fields an archived row carries, so every section restores a fresh row."""

import modules.users.users_profile.contracts as users_profile_contracts


def test_the_id_owner_version_and_stamp_are_dropped_and_the_data_kept():
    row = {"id": 4, "user_id": 3, "version": 7, "updated_at": "2026-11-11T07:30:00Z", "weight_kg": 70}

    assert users_profile_contracts.without_row_identity(row) == {"weight_kg": 70}
