"""Ending the sessions of a provider's sign-ins, finding the sign-ins whose session is gone, and the link listing."""

import uuid

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet

import modules.auth.identity_provider_links.integration_service as links_integration
import modules.auth.identity_provider_links.service as links_service
import modules.auth.sessions.models as sessions_models
from tests._factories.identity_links import make_identity_link, make_identity_provider, make_idp_session
from tests._factories.users import make_user


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.fixture
def world(db):
    return {
        "alice": make_user(db),
        "bob": make_user(db),
        "first": make_identity_provider(db, "first"),
        "second": make_identity_provider(db, "second"),
    }


def _sessions(db) -> set[uuid.UUID]:
    return set(db.scalars(sa.select(sessions_models.UsersSessions.id)))


class TestEndingSessions:
    def test_the_sessions_a_user_signed_in_through_a_provider_end_and_no_others(self, db, world):
        mine = [make_idp_session(db, world["alice"], world["first"]) for _ in range(2)]
        other_provider = make_idp_session(db, world["alice"], world["second"])
        other_user = make_idp_session(db, world["bob"], world["first"])

        ended = links_service.end_idp_sessions(world["alice"].id, world["first"], db)

        assert ended == 2
        assert _sessions(db) == {other_provider, other_user}
        assert not set(mine) & _sessions(db)

    def test_every_session_signed_in_through_a_provider_ends(self, db, world):
        make_idp_session(db, world["alice"], world["first"])
        make_idp_session(db, world["bob"], world["first"])
        kept = make_idp_session(db, world["alice"], world["second"])

        assert links_service.end_all_idp_sessions(world["first"], db) == 2
        assert _sessions(db) == {kept}

    def test_a_provider_session_id_names_the_sessions_that_end_and_how_many_per_user(self, db, world):
        make_idp_session(db, world["alice"], world["first"], sid="shared")
        make_idp_session(db, world["alice"], world["first"], sid="shared")
        make_idp_session(db, world["bob"], world["first"], sid="shared")
        kept = make_idp_session(db, world["bob"], world["first"], sid="other")

        ended = links_service.end_idp_sessions_by_sid(world["first"], "shared", db)

        assert ended == {world["alice"].id: 2, world["bob"].id: 1}
        assert _sessions(db) == {kept}

    def test_a_provider_session_id_can_be_narrowed_to_one_user(self, db, world):
        make_idp_session(db, world["alice"], world["first"], sid="shared")
        kept = make_idp_session(db, world["bob"], world["first"], sid="shared")

        ended = links_service.end_idp_sessions_by_sid(world["first"], "shared", db, user_id=world["alice"].id)

        assert ended == {world["alice"].id: 1}
        assert _sessions(db) == {kept}

    def test_a_sign_in_whose_session_is_already_gone_is_skipped_and_not_counted(self, db, world):
        gone = make_idp_session(db, world["alice"], world["first"])
        make_idp_session(db, world["alice"], world["first"])
        db.execute(sa.delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == gone))
        db.flush()

        assert links_service.end_idp_sessions(world["alice"].id, world["first"], db) == 1

    def test_the_integration_surface_ends_the_same_sessions(self, db, world):
        make_idp_session(db, world["alice"], world["first"], sid="s")
        make_idp_session(db, world["alice"], world["first"], sid="s")

        assert links_integration.end_idp_sessions_by_sid(world["first"], "s", db) == {world["alice"].id: 2}
        assert links_integration.end_idp_sessions(world["alice"].id, world["first"], db) == 0
        assert links_integration.end_all_idp_sessions(world["first"], db) == 0


class TestOrphans:
    def test_the_sign_ins_without_a_session_come_back_with_the_windows_last_id(self, db, world):
        kept = make_idp_session(db, world["alice"], world["first"])
        orphan = make_idp_session(db, world["alice"], world["first"])
        db.execute(sa.delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == orphan))
        db.flush()

        orphans, last_id = links_service.get_orphaned_idp_session_tokens_page(None, 100, db)

        assert [row.session_id for row in orphans] == [orphan]
        assert last_id is not None
        assert kept not in {row.session_id for row in orphans}
        assert links_service.get_orphaned_idp_session_tokens_page(last_id, 100, db) == ([], None)

    def test_a_window_without_any_sign_in_has_no_last_id(self, db):
        assert links_integration.get_orphaned_idp_session_tokens_page(None, 10, db) == ([], None)

    def test_the_window_can_be_one_users(self, db, world):
        mine = make_idp_session(db, world["alice"], world["first"])
        theirs = make_idp_session(db, world["bob"], world["first"])
        db.execute(sa.delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id.in_([mine, theirs])))
        db.flush()

        orphans, _ = links_service.get_orphaned_idp_session_tokens_page(None, 100, db, user_id=world["bob"].id)

        assert [row.session_id for row in orphans] == [theirs]


class TestEnrichment:
    def _provider(self, db, idp_id):
        from modules.auth.identity_providers import crud as idp_crud

        return idp_crud.get_identity_provider(idp_id, db)

    def test_a_link_is_listed_with_the_name_slug_and_type_of_its_provider(self, db, world):
        link = make_identity_link(db, world["alice"].id, world["first"], "sub-123")
        provider = self._provider(db, world["first"])

        (item,) = links_service.enrich_user_identity_providers([link], [provider], world["alice"].id)

        assert (item.idp_id, item.idp_name, item.idp_slug, item.idp_provider_type) == (
            world["first"],
            provider.name,
            "first",
            provider.provider_type,
        )
        assert item.idp_subject == "sub-123"
        assert item.last_login_at == link.last_login

    def test_nothing_to_list_is_an_empty_list_and_a_link_whose_provider_is_missing_is_left_out(self, db, world):
        link = make_identity_link(db, world["alice"].id, world["first"], "s")

        assert links_service.enrich_user_identity_providers([], [], world["alice"].id) == []
        assert links_service.enrich_user_identity_providers([link], [], world["alice"].id) == []
