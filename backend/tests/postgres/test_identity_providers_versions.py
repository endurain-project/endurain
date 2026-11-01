"""Identity-provider version checks against real PostgreSQL."""

import pytest
from sqlalchemy import event

import core.exceptions as core_exceptions
import modules.auth.identity_providers.models as idp_models
import modules.auth.identity_providers.provider_service as idp_provider_service
import modules.auth.identity_providers.schema as idp_schema
from modules.auth.identity_providers import crud as idp_crud
from modules.auth.identity_providers.serializers import to_read_schema


def _create_provider(factory) -> idp_schema.IdentityProviderRead:
    data = idp_schema.IdentityProviderCreate(
        name="Keycloak",
        slug="keycloak",
        client_id="endurain",
        client_secret="secret",
    )
    with factory() as db:
        state = idp_crud.create_identity_provider(data, db)
        db.commit()
        return to_read_schema(state)


def _edit(name: str = "Keycloak Updated") -> idp_schema.IdentityProviderUpdate:
    return idp_schema.IdentityProviderUpdate(name=name, slug="keycloak")


def test_a_provider_edit_requires_the_version_it_read_and_increments_it(pg_factory):
    created = _create_provider(pg_factory)
    with pg_factory() as db:
        updated = idp_provider_service.update_identity_provider(created.id, _edit(), db, if_match='"1"')
    assert (updated.name, updated.version) == ("Keycloak Updated", 2)

    with pg_factory() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        idp_provider_service.update_identity_provider(created.id, _edit("Stale update"), db, if_match='"1"')


def test_a_concurrent_provider_edit_is_refused_at_flush(pg_factory):
    created = _create_provider(pg_factory)
    with pg_factory() as db:

        def commit_competing_edit(session, flush_context, instances):
            with pg_factory() as competing_db:
                competing = competing_db.get(idp_models.IdentityProvider, created.id)
                competing.name = "Concurrent edit"
                competing_db.commit()

        event.listen(db, "before_flush", commit_competing_edit, once=True)
        with pytest.raises(core_exceptions.PreconditionFailedError):
            idp_provider_service.update_identity_provider(created.id, _edit(), db, if_match='"1"')


def test_a_provider_deleted_during_edit_returns_not_found(pg_factory):
    created = _create_provider(pg_factory)
    with pg_factory() as db:

        def delete_competing_provider(session, flush_context, instances):
            with pg_factory() as competing_db:
                competing_db.delete(competing_db.get(idp_models.IdentityProvider, created.id))
                competing_db.commit()

        event.listen(db, "before_flush", delete_competing_provider, once=True)
        with pytest.raises(core_exceptions.NotFoundError):
            idp_provider_service.update_identity_provider(created.id, _edit(), db, if_match='"1"')
