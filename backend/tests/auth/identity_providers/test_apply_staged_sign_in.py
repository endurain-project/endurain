"""The completion of an SSO sign-in applies what its callback staged: the link, the profile sync and the last login.

On the real database, so the links, the account and the audit rows are the ones the completion leaves.
"""

import uuid
from types import SimpleNamespace

import jasil.runtime as platform_runtime
import jasil.testing as jasil_testing
import pytest
from sqlalchemy import event, select

import core.exceptions as core_exceptions
import modules.auth.identity_provider_links.integration_service as links_integration
import modules.auth.identity_provider_links.models as links_models
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.contracts as contracts
import modules.auth.identity_providers.events as idp_events
import modules.auth.identity_providers.user_provisioning_service as provisioning
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.integration_service as users_integration
from tests._factories.identity_links import make_identity_link, make_oidc_provider
from tests._factories.users import make_user

_LINK = idp_audit_actions.IDENTITY_LINK_LINK.id
_EMAIL_CHANGE = users_audit_actions.USER_EMAIL_CHANGE.id
_CLAIMS = contracts.SyncedClaims(name="Synced Name", email="synced@example.com", email_verified=True)


@pytest.fixture
def world(committed_sessions):
    """Two accounts, and the events the completion announces."""
    announced: list[object] = []
    platform_runtime.get_active_platform().events.subscribe(idp_events.IDP_LINKED, announced.append)
    with committed_sessions() as db:
        mine = make_user(db, email="mine@example.com")
        other = make_user(db, email="other@example.com")
        db.commit()
    return SimpleNamespace(mine=mine, other=other, announced=announced, sessions=committed_sessions)


def _provider(world, **switches) -> uuid.UUID:
    values = {"link_by_email": True, "sync_user_info": True, "sync_email": True, **switches}
    with world.sessions() as db:
        idp_id = make_oidc_provider(db, "keycloak", "https://idp.example.com", **values)
        db.commit()
    return idp_id


def _staged(world, idp_id, *, create_link=True, user=None, subject="subject-1", claims=_CLAIMS):
    return contracts.StagedSignIn(
        user_id=(user or world.mine).id, idp_id=idp_id, subject=subject, create_link=create_link, claims=claims
    )


def _link(world, user, idp_id, subject="subject-1") -> None:
    with world.sessions() as db:
        make_identity_link(db, user.id, idp_id, subject)
        db.commit()


def _links(world) -> set[tuple[uuid.UUID, str]]:
    with world.sessions() as db:
        rows = db.execute(select(links_models.IdentityLink.user_id, links_models.IdentityLink.idp_subject)).all()
        return {(row.user_id, row.idp_subject) for row in rows}


def _apply(world, idp_id, staged, *, before_flush=None):
    """Apply the staged sign-in and commit it, as the completion does; return the account and the audit rows."""
    with world.sessions() as db, jasil_testing.capture_audit() as audit:
        if before_flush is not None:
            event.listen(db, "before_flush", before_flush, once=True)
        try:
            user = provisioning.apply_staged_sign_in(
                users_integration.require_user(world.mine.id, db), idp_id, staged, db
            )
        except core_exceptions.SessionEndedError as err:
            db.rollback()
            return err, audit
        db.commit()
    return user, audit


def _account(world, user=None):
    with world.sessions() as db:
        return users_integration.require_user((user or world.mine).id, db)


class TestAnEmailMatch:
    def test_the_link_is_made_audited_and_announced_then_the_profile_synced_and_the_login_stamped(self, world):
        idp_id = _provider(world)

        user, audit = _apply(world, idp_id, _staged(world, idp_id))

        assert _links(world) == {(world.mine.id, "subject-1")}
        entry = audit.assert_audited(_LINK, outcome="success", target_id=str(world.mine.id))
        assert entry.details == {"idp_id": str(idp_id), "reason": None}
        assert len(world.announced) == 1
        assert world.announced[0].payload["user_id"] == str(world.mine.id)
        assert (user.name, user.email, user.email_verified) == ("Synced Name", "synced@example.com", True)
        audit.assert_audited(_EMAIL_CHANGE, target_id=str(world.mine.id))
        with world.sessions() as db:
            link = links_integration.get_user_identity_provider_by_user_id_and_idp_id(world.mine.id, idp_id, db)
        assert link.last_login is not None

    def test_the_provider_switches_of_the_completion_decide_the_sync(self, world):
        idp_id = _provider(world, sync_user_info=False, sync_email=False)
        before = _account(world)

        user, audit = _apply(world, idp_id, _staged(world, idp_id))

        assert (user.name, user.email) == (before.name, before.email)
        audit.assert_not_audited(_EMAIL_CHANGE)
        assert _links(world) == {(world.mine.id, "subject-1")}

    def test_a_provider_that_stopped_linking_by_email_ends_the_sign_in_and_writes_nothing(self, world):
        idp_id = _provider(world, link_by_email=False)
        before = _account(world)

        error, audit = _apply(world, idp_id, _staged(world, idp_id))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(world) == set()
        assert _account(world) == before
        entry = audit.assert_audited(_LINK, outcome="denied", target_id=str(world.mine.id))
        assert entry.details == {"idp_id": str(idp_id), "reason": "link_by_email_disabled"}
        assert world.announced == []

    def test_a_subject_another_account_linked_meanwhile_ends_the_sign_in(self, world):
        idp_id = _provider(world)
        _link(world, world.other, idp_id)
        before = _account(world)

        error, audit = _apply(world, idp_id, _staged(world, idp_id))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(world) == {(world.other.id, "subject-1")}
        assert _account(world) == before
        entry = audit.assert_audited(_LINK, outcome="denied", target_id=str(world.mine.id))
        assert entry.details == {"idp_id": str(idp_id), "reason": "linked_to_another_account"}
        assert world.announced == []

    def test_an_account_linked_meanwhile_to_another_identity_at_the_provider_ends_the_sign_in(self, world):
        idp_id = _provider(world)
        _link(world, world.mine, idp_id, subject="subject-other")

        error, audit = _apply(world, idp_id, _staged(world, idp_id))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(world) == {(world.mine.id, "subject-other")}
        audit.assert_not_audited(_LINK)
        assert world.announced == []

    def test_a_link_the_unique_key_refuses_ends_the_sign_in(self, world):
        """Another sign-in commits the same subject between the check and the insert; the unique key decides."""
        idp_id = _provider(world)

        def competing_sign_in(session, flush_context, instances):
            _link(world, world.other, idp_id)

        error, audit = _apply(world, idp_id, _staged(world, idp_id), before_flush=competing_sign_in)

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(world) == {(world.other.id, "subject-1")}
        entry = audit.assert_audited(_LINK, outcome="denied", target_id=str(world.mine.id))
        assert entry.details == {"idp_id": str(idp_id), "reason": "linked_to_another_account"}
        assert world.announced == []

    def test_a_subject_another_session_already_linked_to_this_account_is_not_linked_again(self, world):
        idp_id = _provider(world)
        _link(world, world.mine, idp_id)

        user, audit = _apply(world, idp_id, _staged(world, idp_id))

        assert _links(world) == {(world.mine.id, "subject-1")}
        audit.assert_not_audited(_LINK)
        assert world.announced == []
        assert user.name == "Synced Name"


class TestALinkedSubject:
    def test_the_profile_is_synced_and_the_login_stamped_without_a_new_link(self, world):
        idp_id = _provider(world)
        _link(world, world.mine, idp_id)

        user, audit = _apply(world, idp_id, _staged(world, idp_id, create_link=False))

        assert user.name == "Synced Name"
        assert _links(world) == {(world.mine.id, "subject-1")}
        audit.assert_not_audited(_LINK)
        assert world.announced == []

    def test_a_subject_no_longer_linked_to_the_account_ends_the_sign_in(self, world):
        idp_id = _provider(world)
        before = _account(world)

        error, audit = _apply(world, idp_id, _staged(world, idp_id, create_link=False))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _account(world) == before
        assert _links(world) == set()
        audit.assert_not_audited(_LINK)


class TestAMissingOrForeignRecord:
    def test_a_missing_record_completes_an_account_already_linked_to_the_provider_with_nothing_applied(self, world):
        idp_id = _provider(world)
        _link(world, world.mine, idp_id)
        before = _account(world)

        user, audit = _apply(world, idp_id, None)

        assert user == before
        assert _account(world) == before
        audit.assert_not_audited(_LINK)
        audit.assert_not_audited(_EMAIL_CHANGE)

    def test_a_missing_record_of_an_account_that_needed_its_link_fails_closed(self, world):
        idp_id = _provider(world)
        before = _account(world)

        error, audit = _apply(world, idp_id, None)

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(world) == set()
        assert _account(world) == before
        audit.assert_not_audited(_LINK)
        assert world.announced == []

    @pytest.mark.parametrize("foreign", ["user", "provider"])
    def test_a_record_for_another_account_or_provider_ends_the_sign_in(self, world, foreign):
        idp_id = _provider(world)
        staged = _staged(world, uuid.uuid4()) if foreign == "provider" else _staged(world, idp_id, user=world.other)

        error, _ = _apply(world, idp_id, staged)

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(world) == set()

    def test_a_deleted_provider_ends_the_sign_in(self, world):
        idp_id = uuid.uuid4()

        error, _ = _apply(world, idp_id, _staged(world, idp_id))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(world) == set()
