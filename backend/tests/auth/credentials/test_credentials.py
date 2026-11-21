"""A user's local credential: its row, the password-change flag and the policy settings, on the real database."""

import pytest
import sqlalchemy as sa

import core.exceptions as core_exceptions
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.crud as credentials_crud
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.credentials.models as credentials_models
import modules.auth.credentials.service as credentials_service
import modules.users.users.crud as users_crud
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import PASSWORD, make_user


class TestCredentialRow:
    def test_a_user_made_with_a_password_has_a_credential_that_verifies(self, db):
        user = make_user(db)

        credential = credentials_integration.get_credential(user.id, db)

        assert credential is not None
        assert credentials_integration.get_password_hasher().verify_password(PASSWORD, credential.password_hash)
        assert credentials_integration.has_local_password(user.id, db) is True
        assert credentials_integration.get_password_hash(user.id, db) == credential.password_hash

    def test_a_user_without_a_password_has_no_credential(self, db):
        user = make_user(db, with_password=False)

        assert credentials_integration.get_credential(user.id, db) is None
        assert credentials_integration.has_local_password(user.id, db) is False
        assert credentials_integration.get_password_hash(user.id, db) is None
        assert credentials_integration.is_password_change_required(user.id, db) is False

    def test_a_row_inserted_without_the_flag_starts_false(self, db):
        user = make_user(db, with_password=False)
        db.execute(sa.insert(credentials_models.LocalCredential).values(user_id=user.id, password_hash="hash"))

        credential = credentials_integration.get_credential(user.id, db)

        assert credential is not None
        assert credential.password_change_required is False

    def test_each_write_of_the_hash_sets_the_flag_it_says(self, db):
        user = make_user(db, with_password=False)

        credentials_integration.set_local_password_hash(user.id, "set-by-admin", db, change_required=True)
        assert credentials_integration.is_password_change_required(user.id, db) is True

        credentials_integration.set_local_password_hash(user.id, "chosen-by-owner", db, change_required=False)
        credential = credentials_integration.get_credential(user.id, db)

        assert credential is not None
        assert (credential.password_hash, credential.password_change_required) == ("chosen-by-owner", False)
        count = db.scalar(sa.select(sa.func.count()).where(credentials_models.LocalCredential.user_id == user.id))
        assert count == 1

    def test_requiring_a_change_keeps_the_hash(self, db):
        user = make_user(db)
        before = credentials_integration.get_password_hash(user.id, db)

        credentials_integration.require_password_change(user.id, db)

        assert credentials_integration.is_password_change_required(user.id, db) is True
        assert credentials_integration.get_password_hash(user.id, db) == before

    def test_requiring_a_change_of_an_account_without_a_password_is_a_conflict(self, db):
        user = make_user(db, with_password=False)

        with pytest.raises(core_exceptions.ConflictError):
            credentials_integration.require_password_change(user.id, db)

        assert credentials_integration.has_local_password(user.id, db) is False

    def test_clearing_the_password_removes_only_that_users_credential(self, db):
        user, other = make_user(db), make_user(db)

        credentials_service.clear_local_password(user.id, db)

        assert credentials_integration.has_local_password(user.id, db) is False
        assert credentials_integration.has_local_password(other.id, db) is True

    def test_the_credential_goes_with_its_user(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        with committed_sessions() as db:
            db.execute(sa.text("DELETE FROM users WHERE id = :u"), {"u": user.id})
            db.commit()
        with committed_sessions() as db:
            assert credentials_integration.get_credential(user.id, db) is None

    def test_a_credential_needs_an_existing_user(self, db):
        user = make_user(db, with_password=False)
        users_crud.delete_user(user.id, db)

        with pytest.raises(sa.exc.IntegrityError):
            credentials_crud.upsert_password_hash(user.id, "hash", False, db)

    def test_the_credentialed_user_ids_select_lists_exactly_the_users_with_a_password(self, db):
        with_password, without = make_user(db), make_user(db, with_password=False)

        ids = set(db.scalars(credentials_integration.select_credentialed_user_ids()))

        assert with_password.id in ids
        assert without.id not in ids


class TestPolicySettings:
    def test_the_minimum_length_follows_the_account_type(self, db):
        settings = edit_server_settings(db, password_length_regular_users=9, password_length_admin_users=17)

        assert credentials_service.resolve_password_min_length(settings, "regular") == 9
        assert credentials_service.resolve_password_min_length(settings, "admin") == 17
        assert credentials_service.resolve_password_min_length(settings, "other") == 9

    def test_a_generated_password_meets_the_account_types_minimum(self, db):
        settings = edit_server_settings(db, password_length_regular_users=9, password_length_admin_users=40)

        regular = credentials_integration.generate_password_for_access_type(settings, "regular")
        admin = credentials_integration.generate_password_for_access_type(settings, "admin")

        assert len(regular) >= 9
        assert len(admin) == 40

    def test_validating_a_password_applies_the_account_types_minimum_and_hashes_it(self, db):
        settings = edit_server_settings(db, password_length_regular_users=8, password_length_admin_users=20)
        hasher = credentials_integration.get_password_hasher()

        stored = credentials_integration.validate_and_hash_password_for_user(
            settings, "regular", "secret-pass-1", db, username="alice", email="alice@example.com"
        )

        assert hasher.verify_password("secret-pass-1", stored)
        with pytest.raises(credentials_contracts.PasswordTooShortError):
            credentials_integration.validate_and_hash_password_for_user(
                settings, "admin", "secret-pass-1", db, username="root", email="root@example.com"
            )

    @pytest.mark.parametrize(
        ("local_login_enabled", "access_type", "allowed"),
        [(True, "regular", True), (True, "admin", True), (False, "regular", False), (False, "admin", True)],
    )
    def test_local_sign_in_off_still_lets_an_administrator_in(self, db, local_login_enabled, access_type, allowed):
        settings = edit_server_settings(db, local_login_enabled=local_login_enabled)

        assert credentials_integration.allows_password_sign_in(settings, access_type) is allowed
