"""The links between users and identity providers, and the provider sign-in each session keeps, on the real database."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.auth.identity_provider_links.crud as links_crud
import modules.auth.identity_provider_links.integration_service as links_integration
import modules.auth.identity_provider_links.models as links_models
from tests._factories.identity_links import make_identity_link, make_identity_provider, make_idp_session
from tests._factories.users import make_user


@pytest.fixture
def world(db):
    """Two users and three providers."""
    return {
        "alice": make_user(db),
        "bob": make_user(db),
        "idps": [make_identity_provider(db, f"p{n}") for n in range(3)],
    }


class TestLinks:
    def test_a_created_link_reads_back_by_user_and_provider_and_by_subject(self, db, world):
        alice, (idp, *_) = world["alice"], world["idps"]

        created = make_identity_link(db, alice.id, idp, "subject-1")

        by_user = links_crud.get_user_identity_provider_by_user_id_and_idp_id(alice.id, idp, db)
        by_subject = links_crud.get_user_identity_provider_by_subject_and_idp_id(idp, "subject-1", db)
        assert by_user == by_subject == created
        assert (created.user_id, created.idp_id, created.idp_subject) == (alice.id, idp, "subject-1")
        assert links_crud.get_user_identity_provider_by_subject_and_idp_id(idp, "other", db) is None
        assert links_crud.get_user_identity_provider_by_user_id_and_idp_id(world["bob"].id, idp, db) is None

    def test_a_subject_of_a_provider_can_be_linked_to_one_account_only(self, db, world):
        idp = world["idps"][0]
        make_identity_link(db, world["alice"].id, idp, "same-subject")

        with pytest.raises(core_exceptions.ConflictError):
            links_crud.create_user_identity_provider(world["bob"].id, idp, "same-subject", db)

    def test_an_account_has_one_link_per_provider(self, db, world):
        idp = world["idps"][0]
        make_identity_link(db, world["alice"].id, idp, "one")

        with pytest.raises(core_exceptions.ConflictError):
            links_crud.create_user_identity_provider(world["alice"].id, idp, "two", db)

    def test_the_same_subject_at_two_providers_is_two_links(self, db, world):
        first, second, _ = world["idps"]

        make_identity_link(db, world["alice"].id, first, "s")
        make_identity_link(db, world["bob"].id, second, "s")

        assert links_crud.count_identity_links(world["alice"].id, db) == 1

    def test_the_last_login_is_stamped_and_a_missing_link_is_none(self, db, world):
        idp = world["idps"][0]
        make_identity_link(db, world["alice"].id, idp, "s")

        stamped = links_crud.update_user_identity_provider_last_login(world["alice"].id, idp, db)

        assert stamped.last_login is not None
        assert links_crud.update_user_identity_provider_last_login(world["bob"].id, idp, db) is None

    def test_a_link_is_deleted_by_its_owner_only(self, db, world):
        idp = world["idps"][0]
        make_identity_link(db, world["alice"].id, idp, "s")

        assert links_crud.delete_user_identity_provider(world["bob"].id, idp, db) is False
        assert links_crud.delete_user_identity_provider(world["alice"].id, idp, db) is True
        assert links_crud.get_user_identity_providers_by_user_id(world["alice"].id, db) == []

    def test_deleting_every_link_of_a_user_leaves_the_others(self, db, world):
        first, second, third = world["idps"]
        make_identity_link(db, world["alice"].id, first, "a")
        make_identity_link(db, world["alice"].id, second, "b")
        make_identity_link(db, world["bob"].id, third, "c")

        assert links_crud.delete_all_user_identity_providers(world["alice"].id, db) == 2
        assert len(links_crud.get_user_identity_providers_by_user_id(world["bob"].id, db)) == 1
        assert links_crud.delete_all_user_identity_providers(world["alice"].id, db) == 0

    def test_a_provider_with_links_is_reported_and_the_counts_are_per_user(self, db, world):
        first, second, third = world["idps"]
        make_identity_link(db, world["alice"].id, first, "a")
        make_identity_link(db, world["alice"].id, second, "b")

        assert links_crud.check_user_identity_providers_by_idp_id(first, db) is True
        assert links_crud.check_user_identity_providers_by_idp_id(third, db) is False
        assert links_crud.get_identity_link_counts_for_users([world["alice"].id, world["bob"].id], db) == {
            world["alice"].id: 2
        }
        linked = set(db.scalars(links_crud.select_linked_user_ids()))
        assert world["alice"].id in linked and world["bob"].id not in linked

    def test_a_page_holds_only_the_users_links_oldest_first_and_windowed(self, db, world):
        first, second, third = world["idps"]
        for idp, user, day in ((first, world["alice"], 3), (second, world["alice"], 1), (third, world["bob"], 2)):
            db.add(
                links_models.IdentityLink(
                    user_id=user.id, idp_id=idp, idp_subject=f"s-{idp}", linked_at=datetime(2026, 1, day, tzinfo=UTC)
                )
            )
        extra = make_identity_provider(db, "p-extra")
        db.add(
            links_models.IdentityLink(
                user_id=world["alice"].id,
                idp_id=extra,
                idp_subject="s-extra",
                linked_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )
        db.flush()

        page_one = links_crud.get_identity_links_page(world["alice"].id, db, limit=2, offset=0)
        page_two = links_crud.get_identity_links_page(world["alice"].id, db, limit=2, offset=2)

        assert [link.idp_id for link in page_one] == [second, extra]
        assert [link.idp_id for link in page_two] == [first]
        assert links_crud.count_identity_links(world["alice"].id, db) == 3

    def test_the_integration_surface_gives_the_same_answers(self, db, world):
        idp = world["idps"][0]
        links_integration.create_user_identity_provider(world["alice"].id, idp, "s", db)

        assert links_integration.check_user_identity_providers_by_idp_id(idp, db) is True
        assert links_integration.count_identity_links(world["alice"].id, db) == 1
        assert links_integration.get_identity_link_counts_for_users([world["alice"].id], db) == {world["alice"].id: 1}
        assert links_integration.update_user_identity_provider_last_login(world["alice"].id, idp, db) is not None
        assert links_integration.delete_user_identity_provider(world["alice"].id, idp, db) is True
        assert links_integration.delete_all_user_identity_providers(world["alice"].id, db) == 0


class TestSessionSignIns:
    @pytest.fixture(autouse=True)
    def _fernet_key(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())

    def test_a_sign_in_keeps_its_tokens_encrypted_and_its_provider_session_id(self, db, world):
        idp = world["idps"][0]

        session_id = make_idp_session(db, world["alice"], idp, id_token="header.payload.signature", sid="sid-1")

        stored = links_crud.get_idp_session_token(session_id, db)
        assert (stored.user_id, stored.idp_id, stored.idp_sid) == (world["alice"].id, idp, "sid-1")
        assert stored.refresh_token != "provider-refresh-token"
        assert core_cryptography.decrypt_token_fernet(stored.refresh_token) == "provider-refresh-token"
        assert core_cryptography.decrypt_token_fernet(stored.id_token) == "header.payload.signature"
        assert stored.access_token_expires_at > datetime.now(UTC) + timedelta(minutes=30)

    def test_a_provider_that_issued_no_token_still_leaves_a_row(self, db, world):
        session_id = make_idp_session(db, world["alice"], world["idps"][0], issues_refresh_token=False)

        stored = links_crud.get_idp_session_token(session_id, db)

        assert (stored.refresh_token, stored.id_token, stored.access_token_expires_at) == (None, None, None)

    def test_a_session_that_signed_in_through_no_provider_has_no_row(self, db):
        assert links_crud.get_idp_session_token(uuid.uuid4(), db) is None

    def test_the_sessions_of_one_user_and_provider_are_listed_and_so_are_the_owners_of_a_provider(self, db, world):
        first, second, _ = world["idps"]
        mine = [make_idp_session(db, world["alice"], first) for _ in range(2)]
        elsewhere = make_idp_session(db, world["alice"], second)
        theirs = make_idp_session(db, world["bob"], first)

        assert sorted(links_crud.get_idp_session_token_ids_by_user_and_idp(world["alice"].id, first, db)) == sorted(
            mine
        )
        assert sorted(links_crud.get_idp_session_owners(first, db)) == sorted(
            [(sid, world["alice"].id) for sid in mine] + [(theirs, world["bob"].id)]
        )
        assert links_crud.get_idp_session_owners(second, db) == [(elsewhere, world["alice"].id)]

    def test_the_owners_by_provider_session_id_can_be_narrowed_to_one_user(self, db, world):
        idp = world["idps"][0]
        a = make_idp_session(db, world["alice"], idp, sid="shared")
        b = make_idp_session(db, world["bob"], idp, sid="shared")
        make_idp_session(db, world["bob"], idp, sid="other")

        assert sorted(links_crud.get_idp_session_owners_by_sid(idp, "shared", db)) == sorted(
            [(a, world["alice"].id), (b, world["bob"].id)]
        )
        assert links_crud.get_idp_session_owners_by_sid(idp, "shared", db, user_id=world["bob"].id) == [
            (b, world["bob"].id)
        ]

    def test_a_page_walks_the_rows_in_id_order_and_can_be_one_users(self, db, world):
        idp = world["idps"][0]
        for _ in range(3):
            make_idp_session(db, world["alice"], idp)
        make_idp_session(db, world["bob"], idp)

        first = links_crud.get_idp_session_tokens_page(None, 2, db)
        rest = links_crud.get_idp_session_tokens_page(first[-1].id, 10, db)
        only_bob = links_crud.get_idp_session_tokens_page(None, 10, db, user_id=world["bob"].id)

        assert len(first) == 2 and len(rest) == 2
        assert [row.id for row in first + rest] == sorted(row.id for row in first + rest)
        assert [row.user_id for row in only_bob] == [world["bob"].id]

    def test_a_replace_over_the_token_read_is_applied_and_over_another_is_dropped(self, db, world):
        session_id = make_idp_session(db, world["alice"], world["idps"][0], id_token="old.id.token")
        read = links_crud.get_idp_session_token(session_id, db)
        expires = datetime.now(UTC) + timedelta(hours=2)

        applied = links_crud.replace_refresh_token_if_unchanged(
            session_id, read.refresh_token, core_cryptography.encrypt_token_fernet("rotated"), expires, db
        )
        dropped = links_crud.replace_refresh_token_if_unchanged(
            session_id, read.refresh_token, core_cryptography.encrypt_token_fernet("late"), expires, db
        )

        assert (applied, dropped) == (True, False)
        stored = links_crud.get_idp_session_token(session_id, db)
        assert core_cryptography.decrypt_token_fernet(stored.refresh_token) == "rotated"
        assert core_cryptography.decrypt_token_fernet(stored.id_token) == "old.id.token"

    def test_a_replace_with_an_id_token_replaces_the_stored_one(self, db, world):
        session_id = make_idp_session(db, world["alice"], world["idps"][0], id_token="old.id.token")
        read = links_crud.get_idp_session_token(session_id, db)

        links_crud.replace_refresh_token_if_unchanged(
            session_id,
            read.refresh_token,
            core_cryptography.encrypt_token_fernet("rotated"),
            datetime.now(UTC) + timedelta(hours=1),
            db,
            encrypted_id_token=core_cryptography.encrypt_token_fernet("new.id.token"),
        )

        stored = links_crud.get_idp_session_token(session_id, db)
        assert core_cryptography.decrypt_token_fernet(stored.id_token) == "new.id.token"

    def test_a_replace_of_a_missing_session_changes_nothing(self, db):
        assert (
            links_crud.replace_refresh_token_if_unchanged(
                uuid.uuid4(), "x", "y", datetime.now(UTC) + timedelta(hours=1), db
            )
            is False
        )

    def test_a_clear_of_the_token_read_is_applied_and_never_wipes_another(self, db, world):
        session_id = make_idp_session(db, world["alice"], world["idps"][0])
        read = links_crud.get_idp_session_token(session_id, db)

        wrong = links_crud.clear_refresh_token_if_unchanged(session_id, "another-token", db)
        right = links_crud.clear_refresh_token_if_unchanged(session_id, read.refresh_token, db)

        assert (wrong, right) == (False, True)
        assert links_crud.get_idp_session_token(session_id, db).refresh_token is None

    def test_a_token_no_key_decrypts_is_cleared_by_its_own_ciphertext(self, db, world):
        session_id = make_idp_session(db, world["alice"], world["idps"][0])
        db.execute(sa.update(links_models.IdpSessionToken).values(refresh_token="not-a-fernet-token"))
        db.flush()

        assert links_crud.clear_refresh_token_if_unchanged(session_id, "not-a-fernet-token", db) is True

    def test_a_delete_of_the_token_read_removes_the_row_and_never_one_another_refresh_stored(self, db, world):
        session_id = make_idp_session(db, world["alice"], world["idps"][0])
        read = links_crud.get_idp_session_token(session_id, db)

        refused = links_crud.delete_idp_session_token_if_unchanged(session_id, "another", db)
        removed = links_crud.delete_idp_session_token_if_unchanged(session_id, read.refresh_token, db)

        assert (refused, removed) == (False, True)
        assert links_crud.get_idp_session_token(session_id, db) is None

    def test_a_row_that_holds_no_token_and_a_missing_row_are_deleted_without_a_fuss(self, db, world):
        session_id = make_idp_session(db, world["alice"], world["idps"][0], issues_refresh_token=False)

        assert links_crud.delete_idp_session_token_if_unchanged(session_id, None, db) is True
        assert links_crud.delete_idp_session_token_if_unchanged(uuid.uuid4(), None, db) is False

    def test_the_integration_surface_reads_and_changes_the_same_rows(self, db, world):
        session_id = make_idp_session(db, world["alice"], world["idps"][0])
        read = links_integration.get_idp_session_token(session_id, db)

        assert links_integration.clear_idp_session_refresh_token_if_unchanged(session_id, read.refresh_token, db)
        assert links_integration.delete_idp_session_token_if_unchanged(session_id, None, db)


class TestSecretsThatCannotBeEncrypted:
    def test_a_token_no_key_can_encrypt_is_not_stored_but_the_sign_in_is_recorded(self, db, world, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", "not a fernet key")

        session_id = make_idp_session(db, world["alice"], world["idps"][0], id_token="a.b.c")

        stored = links_crud.get_idp_session_token(session_id, db)
        assert (stored.user_id, stored.refresh_token, stored.id_token) == (world["alice"].id, None, None)


class TestRotation:
    def test_a_session_token_under_an_old_key_is_rewritten_under_the_first_one(self, db, world, monkeypatch):
        import modules.auth.identity_provider_links.service as links_service

        old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        monkeypatch.setenv("FERNET_KEY", old)
        session_id = make_idp_session(db, world["alice"], world["idps"][0], id_token="a.b.c")
        before = links_crud.get_idp_session_token(session_id, db)
        monkeypatch.setenv("FERNET_KEY", f"{new},{old}")

        links_service.reencrypt_stored_secrets(db)

        monkeypatch.setenv("FERNET_KEY", new)
        after = links_crud.get_idp_session_token(session_id, db)
        assert after.refresh_token != before.refresh_token
        assert core_cryptography.decrypt_token_fernet(after.refresh_token) == "provider-refresh-token"
        assert core_cryptography.decrypt_token_fernet(after.id_token) == "a.b.c"


def test_the_rotation_job_re_encrypts_a_session_token_under_the_first_key(committed_sessions, monkeypatch):
    import modules.auth.identity_provider_links.scheduled_jobs as links_scheduled_jobs

    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEY", old)
    with committed_sessions() as db:
        alice = make_user(db)
        session_id = make_idp_session(db, alice, make_identity_provider(db, "acme"))
        db.commit()
    monkeypatch.setenv("FERNET_KEY", f"{new},{old}")

    links_scheduled_jobs.reencrypt_stored_secrets()

    monkeypatch.setenv("FERNET_KEY", new)
    with committed_sessions() as db:
        stored = links_crud.get_idp_session_token(session_id, db)
        assert core_cryptography.decrypt_token_fernet(stored.refresh_token) == "provider-refresh-token"
