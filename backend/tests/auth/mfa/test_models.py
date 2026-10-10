"""Tests for auth.mfa.models — UsersMFA ORM model.

Covers:
- Table and column definitions.
- UniqueConstraint / index metadata.
"""

from modules.auth.mfa.models import UsersMFA


class TestUsersMFAModel:
    """Tests for UsersMFA ORM model structure."""

    def test_tablename(self):
        """UsersMFA maps to the correct table name."""
        assert UsersMFA.__tablename__ == "users_mfa"

    def test_has_id_column(self):
        """Model exposes an auto-increment primary key."""
        col = UsersMFA.__table__.c["id"]
        assert col.primary_key
        assert col.autoincrement

    def test_has_user_id_column(self):
        """user_id column exists and is not nullable."""
        col = UsersMFA.__table__.c["user_id"]
        assert not col.nullable

    def test_user_id_has_fk_to_users(self):
        """user_id carries a FK to users.id."""
        col = UsersMFA.__table__.c["user_id"]
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "users.id" in fk_targets

    def test_has_mfa_enabled_column(self):
        """mfa_enabled column exists and is not nullable."""
        col = UsersMFA.__table__.c["mfa_enabled"]
        assert not col.nullable

    def test_mfa_enabled_default_false(self):
        """mfa_enabled defaults to False."""
        col = UsersMFA.__table__.c["mfa_enabled"]
        assert col.default.arg is False

    def test_has_mfa_secret_column(self):
        """mfa_secret column exists and is nullable."""
        col = UsersMFA.__table__.c["mfa_secret"]
        assert col.nullable

    def test_unique_constraint_on_user_id(self):
        """UniqueConstraint uq_users_mfa_user_id is present."""
        constraint_names = {c.name for c in UsersMFA.__table__.constraints}
        assert "uq_users_mfa_user_id" in constraint_names

    def test_index_on_user_id(self):
        """Index ix_users_mfa_user_id is defined on the table."""
        index_names = {idx.name for idx in UsersMFA.__table__.indexes}
        assert "ix_users_mfa_user_id" in index_names
