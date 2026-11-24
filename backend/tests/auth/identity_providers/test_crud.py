"""Identity-provider rows on the real database: reading, the unique rules, versioned writes and the icon flag."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.schema as idp_schema
from tests._factories.identity_links import make_identity_provider, make_oidc_provider


def _create(db, slug, **fields) -> uuid.UUID:
    """Stage an OAuth2 provider, which has no issuer."""
    return make_oidc_provider(db, slug, None, provider_type="oauth2", scopes="profile", **fields)


class TestReading:
    def test_a_provider_is_read_by_id_slug_and_issuer_with_its_credentials_still_encrypted(self, db):
        idp_id = make_oidc_provider(db, "acme", "https://idp.example.com/")

        by_id = idp_crud.get_identity_provider(idp_id, db)

        assert by_id == idp_crud.get_identity_provider_by_slug("acme", db)
        assert by_id == idp_crud.get_identity_provider_by_issuer("https://idp.example.com", db)
        assert by_id.client_id != "endurain-client"
        assert core_cryptography.decrypt_token_fernet(by_id.client_id) == "endurain-client"
        assert core_cryptography.decrypt_token_fernet(by_id.client_secret) == "endurain-secret"
        assert idp_crud.get_identity_provider(uuid.uuid4(), db) is None
        assert idp_crud.get_identity_provider_by_slug("nobody", db) is None

    def test_the_issuer_lookup_ignores_trailing_slashes_and_can_leave_one_provider_out(self, db):
        idp_id = make_oidc_provider(db, "acme", "https://idp.example.com")

        assert idp_crud.get_identity_provider_by_issuer("https://idp.example.com///", db).id == idp_id
        assert idp_crud.get_identity_provider_by_issuer("https://idp.example.com", db, exclude_id=idp_id) is None

    def test_a_page_is_ordered_by_name_and_windowed_and_enabled_only_leaves_the_disabled_out(self, db):
        for slug, name, enabled in (("c", "Charlie", True), ("a", "Alpha", False), ("b", "Bravo", True)):
            _create(db, slug, name=name, enabled=enabled)

        page = idp_crud.get_identity_providers_page(db, enabled_only=False, limit=2, offset=1)
        enabled = idp_crud.get_identity_providers_page(db, enabled_only=True, limit=10, offset=0)

        assert [state.name for state in page] == ["Bravo", "Charlie"]
        assert [state.name for state in enabled] == ["Bravo", "Charlie"]
        assert idp_crud.count_identity_providers(db, enabled_only=False) == 3
        assert idp_crud.count_identity_providers(db, enabled_only=True) == 2

    def test_providers_are_read_by_a_batch_of_ids(self, db):
        first, second = _create(db, "one"), _create(db, "two")

        found = idp_crud.get_identity_providers_by_ids([first, second, uuid.uuid4()], db)

        assert {state.id for state in found} == {first, second}
        assert idp_crud.get_identity_providers_by_ids([], db) == []

    def test_existence_is_reported(self, db):
        idp_id = make_identity_provider(db, "here")

        assert idp_crud.identity_provider_exists(idp_id, db) is True
        assert idp_crud.identity_provider_exists(uuid.uuid4(), db) is False

    def test_the_lock_reports_whether_the_provider_exists_and_is_enabled(self, db):
        on = _create(db, "on")
        off = _create(db, "off", enabled=False)

        assert idp_crud.lock_provider_enabled(on, db) is True
        assert idp_crud.lock_provider_enabled(off, db) is False
        assert idp_crud.lock_provider_enabled(uuid.uuid4(), db) is False


class TestUniqueRules:
    def test_a_second_provider_with_the_same_issuer_is_refused_whatever_the_trailing_slash(self, db):
        make_oidc_provider(db, "first", "https://idp.example.com")

        with pytest.raises(core_exceptions.IssuerInUseError):
            make_oidc_provider(db, "second", "https://idp.example.com/")

    def test_a_provider_cannot_take_the_issuer_another_provider_has(self, db):
        make_oidc_provider(db, "first", "https://one.example.com")
        second = make_oidc_provider(db, "second", "https://two.example.com")

        with pytest.raises(core_exceptions.IssuerInUseError):
            idp_crud.update_identity_provider(
                second, idp_schema.IdentityProviderUpdate(issuer_url="https://one.example.com/"), db, if_match='"1"'
            )

    def test_providers_without_an_issuer_do_not_conflict(self, db):
        _create(db, "one")
        _create(db, "two")

        assert idp_crud.count_identity_providers(db, enabled_only=False) == 2

    def test_another_integrity_error_is_not_reported_as_a_shared_issuer(self, db):
        _create(db, "same")

        with pytest.raises(IntegrityError):
            _create(db, "same")


class TestVersionedWrites:
    def test_an_update_applies_the_given_fields_encrypts_credentials(self, db):
        idp_id = make_oidc_provider(db, "acme", "https://idp.example.com")

        updated = idp_crud.update_identity_provider(
            idp_id,
            idp_schema.IdentityProviderUpdate(name="Renamed", slug="new-slug", client_secret="rotated"),
            db,
            if_match='"1"',
        )

        assert (updated.name, updated.slug) == ("Renamed", "new-slug")
        assert core_cryptography.decrypt_token_fernet(updated.client_secret) == "rotated"
        assert core_cryptography.decrypt_token_fernet(updated.client_id) == "endurain-client"

    def test_an_update_without_credentials_keeps_the_stored_ones(self, db):
        idp_id = make_oidc_provider(db, "acme", "https://idp.example.com")
        before = idp_crud.get_identity_provider(idp_id, db)

        after = idp_crud.update_identity_provider(
            idp_id, idp_schema.IdentityProviderUpdate(name="Renamed"), db, if_match='"1"'
        )

        assert (after.client_id, after.client_secret) == (before.client_id, before.client_secret)

    def test_an_update_needs_the_version_the_client_read_and_a_missing_row_is_none(self, db):
        idp_id = make_identity_provider(db, "acme")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            idp_crud.update_identity_provider(idp_id, idp_schema.IdentityProviderUpdate(name="x"), db, if_match='"9"')
        assert (
            idp_crud.update_identity_provider(
                uuid.uuid4(), idp_schema.IdentityProviderUpdate(name="x"), db, if_match='"1"'
            )
            is None
        )
        assert idp_crud.get_identity_provider(idp_id, db).name != "x"

    def test_a_delete_needs_the_version_the_client_read_and_reports_whether_the_row_existed(self, db):
        idp_id = make_identity_provider(db, "acme")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            idp_crud.delete_identity_provider(idp_id, db, if_match='"9"')
        assert idp_crud.identity_provider_exists(idp_id, db) is True
        assert idp_crud.delete_identity_provider(idp_id, db, if_match='"1"') is True
        assert idp_crud.delete_identity_provider(idp_id, db, if_match='"1"') is False


class TestIcon:
    def test_the_icon_flag_is_set_with_the_version_it_gives_and_whether_an_icon_was_there_before(self, db):
        idp_id = make_identity_provider(db, "acme")

        first = idp_crud.set_icon_uploaded(idp_id, True, db)
        second = idp_crud.set_icon_uploaded(idp_id, True, db)
        cleared = idp_crud.set_icon_uploaded(idp_id, False, db)

        assert first[1] is False and second[1] is True and cleared[1] is True
        assert first[0] < second[0] < cleared[0]
        assert idp_crud.get_identity_provider(idp_id, db).icon_uploaded is False

    def test_a_missing_provider_is_none(self, db):
        assert idp_crud.set_icon_uploaded(uuid.uuid4(), True, db) is None

    def test_only_the_given_providers_that_have_an_uploaded_icon_are_returned(self, db):
        with_icon, without = make_identity_provider(db, "has"), make_identity_provider(db, "hasnt")
        elsewhere = make_identity_provider(db, "elsewhere")
        for idp_id in (with_icon, elsewhere):
            idp_crud.set_icon_uploaded(idp_id, True, db)

        assert idp_crud.get_ids_with_icon([with_icon, without, uuid.uuid4()], db) == {with_icon}


class TestSecretsRotation:
    def test_the_rotation_job_leaves_secrets_alone_while_one_key_is_configured(self, committed_sessions):
        import modules.auth.identity_providers.scheduled_jobs as idp_scheduled_jobs

        with committed_sessions() as db:
            idp_id = make_oidc_provider(db, "acme", "https://idp.example.com")
            db.commit()
        with committed_sessions() as db:
            before = idp_crud.get_identity_provider(idp_id, db)

        idp_scheduled_jobs.reencrypt_stored_secrets()

        with committed_sessions() as db:
            after = idp_crud.get_identity_provider(idp_id, db)
        assert (after.client_id, after.client_secret) == (before.client_id, before.client_secret)

    def test_a_secret_under_an_old_key_is_rewritten_under_the_first_one(self, committed_sessions, monkeypatch):
        import sqlalchemy as sa
        from cryptography.fernet import Fernet

        import modules.auth.identity_providers.models as idp_models
        import modules.auth.identity_providers.scheduled_jobs as idp_scheduled_jobs

        old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        monkeypatch.setenv("FERNET_KEY", old)
        with committed_sessions() as db:
            idp_id = make_oidc_provider(db, "acme", "https://idp.example.com")
            db.commit()
        monkeypatch.setenv("FERNET_KEY", f"{new},{old}")

        idp_scheduled_jobs.reencrypt_stored_secrets()

        monkeypatch.setenv("FERNET_KEY", new)
        with committed_sessions() as db:
            stored = db.scalar(sa.select(idp_models.IdentityProvider).where(idp_models.IdentityProvider.id == idp_id))
            assert core_cryptography.decrypt_token_fernet(stored.client_id) == "endurain-client"
            assert core_cryptography.decrypt_token_fernet(stored.client_secret) == "endurain-secret"
