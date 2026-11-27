"""The activity files revision adds the retained files table and the activity reference; the downgrade drops both."""

import pytest
import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "5b8e2d4f6a13"
_REVISION = "7d4a9c1e6b52"


def _table_names(engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _activity_columns(engine) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(engine).get_columns("activities")}


def test_the_upgrade_creates_the_table_with_its_indexes_and_the_nullable_reference(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    assert "activity_files" not in _table_names(upgrade_db)
    assert "file_id" not in _activity_columns(upgrade_db)

    alembic_chain.upgrade(upgrade_db, _REVISION)

    inspector = sa.inspect(upgrade_db)
    columns = {column["name"]: column for column in inspector.get_columns("activity_files")}
    assert set(columns) == {
        "id",
        "user_id",
        "sha256",
        "storage_key",
        "extension",
        "size_bytes",
        "state",
        "created_at",
        "updated_at",
    }
    assert all(column["comment"] for name, column in columns.items() if name != "id")
    indexes = {index["name"]: index for index in inspector.get_indexes("activity_files")}
    assert indexes["uq_activity_files_user_sha256_live"]["unique"] is True
    assert indexes["uq_activity_files_user_sha256_live"]["column_names"] == ["user_id", "sha256"]
    assert indexes["ix_activity_files_state_updated_at"]["column_names"] == ["state", "updated_at"]
    reference = _activity_columns(upgrade_db)["file_id"]
    assert reference["nullable"] is True
    assert reference["comment"]
    assert any(
        foreign_key["referred_table"] == "activity_files" and foreign_key["constrained_columns"] == ["file_id"]
        for foreign_key in inspector.get_foreign_keys("activities")
    )


def test_the_unique_index_ignores_a_row_being_deleted(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)
    user_id = _insert_user(upgrade_db)

    def insert(state: str, key: str) -> None:
        with upgrade_db.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO activity_files (id, user_id, sha256, storage_key, extension, size_bytes, state) "
                    "VALUES (gen_random_uuid(), :user_id, :sha, :key, '.fit', 1, :state)"
                ),
                {"user_id": user_id, "sha": "a" * 64, "key": key, "state": state},
            )

    insert("deleting", "files/one.fit")
    insert("attached", "files/two.fit")
    insert("deleting", "files/three.fit")
    with pytest.raises(sa.exc.IntegrityError):
        insert("pending", "files/four.fit")


def test_the_downgrade_drops_the_column_and_the_table(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    assert "activity_files" not in _table_names(upgrade_db)
    assert "file_id" not in _activity_columns(upgrade_db)


def _insert_user(engine) -> str:
    user_id = "00000000-0000-0000-0000-000000000001"
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, name, username, email, preferred_language, email_verified, "
                "pending_admin_approval, active, gender, access_type, first_day_of_week, units, currency) "
                "VALUES (:user_id, 'Ada', 'ada', 'ada@example.com', 'us', true, false, "
                "true, 'female', 'regular', 'monday', 'metric', 'euro')"
            ),
            {"user_id": user_id},
        )
    return user_id
