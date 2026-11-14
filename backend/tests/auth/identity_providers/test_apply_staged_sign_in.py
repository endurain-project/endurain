"""The completion of an SSO sign-in applies what its callback staged: the link, the profile sync and the last login.

Against real SQLite rows, so the links, the account and the audit rows are the ones the completion leaves.
"""

import uuid
from unittest.mock import patch

import jasil.testing as jasil_testing
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import core.exceptions as core_exceptions
import modules.auth.identity_provider_links.integration_service as links_integration
import modules.auth.identity_provider_links.models as links_models
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.contracts as contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.identity_providers.user_provisioning_service as provisioning
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.integration_service as users_integration
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import create_sqlite_session_factory, ensure_user

_LINK = idp_audit_actions.IDENTITY_LINK_LINK.id
_EMAIL_CHANGE = users_audit_actions.USER_EMAIL_CHANGE.id
_PUBLISH_NOTICE = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"
_CLAIMS = contracts.SyncedClaims(name="Synced Name", email="synced@example.com", email_verified=True)


@pytest.fixture
def factory() -> sessionmaker:
    factory = create_sqlite_session_factory()
    ensure_user(factory, MOCK_USER_ID)
    ensure_user(factory, OTHER_USER_ID)
    yield factory
    factory.kw["bind"].dispose()


def _provider(factory, **switches) -> uuid.UUID:
    values = {"link_by_email": True, "sync_user_info": True, "sync_email": True, **switches}
    with factory() as db:
        idp = idp_crud.create_identity_provider(
            idp_schema.IdentityProviderCreate(
                name="Keycloak",
                slug="keycloak",
                issuer_url="https://idp.example.com",
                client_id="endurain",
                client_secret="secret",
                enabled=True,
                **values,
            ),
            db,
        )
        db.commit()
        return idp.id


def _staged(idp_id, *, create_link=True, user_id=MOCK_USER_ID, subject="subject-1", claims=_CLAIMS):
    return contracts.StagedSignIn(
        user_id=user_id, idp_id=idp_id, subject=subject, create_link=create_link, claims=claims
    )


def _link(factory, user_id, idp_id, subject="subject-1") -> None:
    with factory() as db:
        links_integration.create_user_identity_provider(user_id, idp_id, subject, db)
        db.commit()


def _links(factory) -> set[tuple[uuid.UUID, str]]:
    with factory() as db:
        rows = db.execute(select(links_models.IdentityLink.user_id, links_models.IdentityLink.idp_subject)).all()
        return {(row.user_id, row.idp_subject) for row in rows}


def _apply(factory, idp_id, staged, *, user_id=MOCK_USER_ID):
    """Apply the staged sign-in and commit it, as the completion does; return the account and what was recorded."""
    with (
        factory() as db,
        jasil_testing.capture_audit() as audit,
        patch.object(provisioning.idp_event_publishers, "publish_idp_linked") as linked,
        patch(_PUBLISH_NOTICE),
    ):
        try:
            user = provisioning.apply_staged_sign_in(users_integration.require_user(user_id, db), idp_id, staged, db)
        except core_exceptions.SessionEndedError as err:
            db.rollback()
            return err, audit, linked
        db.commit()
    return user, audit, linked


def _account(factory, user_id=MOCK_USER_ID):
    with factory() as db:
        return users_integration.require_user(user_id, db)


class TestAnEmailMatch:
    def test_the_link_is_made_audited_and_announced_then_the_profile_synced_and_the_login_stamped(self, factory):
        idp_id = _provider(factory)

        user, audit, linked = _apply(factory, idp_id, _staged(idp_id))

        assert _links(factory) == {(MOCK_USER_ID, "subject-1")}
        entry = audit.assert_audited(_LINK, outcome="success", target_id=str(MOCK_USER_ID))
        assert entry.details == {"idp_id": str(idp_id), "reason": None}
        linked.assert_called_once()
        assert linked.call_args.args[:2] == (MOCK_USER_ID, idp_id)
        assert (user.name, user.email, user.email_verified) == ("Synced Name", "synced@example.com", True)
        audit.assert_audited(_EMAIL_CHANGE, target_id=str(MOCK_USER_ID))
        with factory() as db:
            link = links_integration.get_user_identity_provider_by_user_id_and_idp_id(MOCK_USER_ID, idp_id, db)
        assert link is not None
        assert link.last_login is not None

    def test_the_provider_switches_of_the_completion_decide_the_sync(self, factory):
        idp_id = _provider(factory, sync_user_info=False, sync_email=False)
        before = _account(factory)

        user, audit, _ = _apply(factory, idp_id, _staged(idp_id))

        assert (user.name, user.email) == (before.name, before.email)
        audit.assert_not_audited(_EMAIL_CHANGE)
        assert _links(factory) == {(MOCK_USER_ID, "subject-1")}

    def test_a_provider_that_stopped_linking_by_email_ends_the_sign_in_and_writes_nothing(self, factory):
        idp_id = _provider(factory, link_by_email=False)
        before = _account(factory)

        error, audit, linked = _apply(factory, idp_id, _staged(idp_id))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(factory) == set()
        assert _account(factory) == before
        entry = audit.assert_audited(_LINK, outcome="denied", target_id=str(MOCK_USER_ID))
        assert entry.details == {"idp_id": str(idp_id), "reason": "link_by_email_disabled"}
        linked.assert_not_called()

    def test_a_subject_another_account_linked_meanwhile_ends_the_sign_in(self, factory):
        idp_id = _provider(factory)
        _link(factory, OTHER_USER_ID, idp_id)
        before = _account(factory)

        error, audit, linked = _apply(factory, idp_id, _staged(idp_id))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(factory) == {(OTHER_USER_ID, "subject-1")}
        assert _account(factory) == before
        entry = audit.assert_audited(_LINK, outcome="denied", target_id=str(MOCK_USER_ID))
        assert entry.details == {"idp_id": str(idp_id), "reason": "linked_to_another_account"}
        linked.assert_not_called()

    def test_an_account_linked_meanwhile_to_another_identity_at_the_provider_ends_the_sign_in(self, factory):
        idp_id = _provider(factory)
        _link(factory, MOCK_USER_ID, idp_id, subject="subject-other")

        error, audit, linked = _apply(factory, idp_id, _staged(idp_id))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(factory) == {(MOCK_USER_ID, "subject-other")}
        audit.assert_not_audited(_LINK)
        linked.assert_not_called()

    def test_a_link_the_unique_key_refuses_ends_the_sign_in(self, factory):
        idp_id = _provider(factory)

        with patch.object(
            provisioning.identity_provider_links_integration,
            "create_user_identity_provider",
            side_effect=core_exceptions.ConflictError("Identity provider already linked"),
        ):
            error, audit, linked = _apply(factory, idp_id, _staged(idp_id))

        assert isinstance(error, core_exceptions.SessionEndedError)
        entry = audit.assert_audited(_LINK, outcome="denied", target_id=str(MOCK_USER_ID))
        assert entry.details == {"idp_id": str(idp_id), "reason": "linked_to_another_account"}
        linked.assert_not_called()

    def test_a_subject_another_session_already_linked_to_this_account_is_not_linked_again(self, factory):
        idp_id = _provider(factory)
        _link(factory, MOCK_USER_ID, idp_id)

        user, audit, linked = _apply(factory, idp_id, _staged(idp_id))

        assert _links(factory) == {(MOCK_USER_ID, "subject-1")}
        audit.assert_not_audited(_LINK)
        linked.assert_not_called()
        assert user.name == "Synced Name"


class TestALinkedSubject:
    def test_the_profile_is_synced_and_the_login_stamped_without_a_new_link(self, factory):
        idp_id = _provider(factory)
        _link(factory, MOCK_USER_ID, idp_id)

        user, audit, linked = _apply(factory, idp_id, _staged(idp_id, create_link=False))

        assert user.name == "Synced Name"
        assert _links(factory) == {(MOCK_USER_ID, "subject-1")}
        audit.assert_not_audited(_LINK)
        linked.assert_not_called()

    def test_a_subject_no_longer_linked_to_the_account_ends_the_sign_in(self, factory):
        idp_id = _provider(factory)
        before = _account(factory)

        error, audit, _ = _apply(factory, idp_id, _staged(idp_id, create_link=False))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _account(factory) == before
        assert _links(factory) == set()
        audit.assert_not_audited(_LINK)


class TestAMissingOrForeignRecord:
    def test_a_missing_record_completes_an_account_already_linked_to_the_provider_with_nothing_applied(self, factory):
        idp_id = _provider(factory)
        _link(factory, MOCK_USER_ID, idp_id)
        before = _account(factory)

        user, audit, _ = _apply(factory, idp_id, None)

        assert user == before
        assert _account(factory) == before
        audit.assert_not_audited(_LINK)
        audit.assert_not_audited(_EMAIL_CHANGE)

    def test_a_missing_record_of_an_account_that_needed_its_link_fails_closed(self, factory):
        idp_id = _provider(factory)
        before = _account(factory)

        error, audit, linked = _apply(factory, idp_id, None)

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(factory) == set()
        assert _account(factory) == before
        audit.assert_not_audited(_LINK)
        linked.assert_not_called()

    @pytest.mark.parametrize("foreign", ["user", "provider"])
    def test_a_record_for_another_account_or_provider_ends_the_sign_in(self, factory, foreign):
        idp_id = _provider(factory)
        staged = _staged(uuid.uuid4()) if foreign == "provider" else _staged(idp_id, user_id=OTHER_USER_ID)

        error, _, _ = _apply(factory, idp_id, staged)

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(factory) == set()

    def test_a_deleted_provider_ends_the_sign_in(self, factory):
        idp_id = uuid.uuid4()

        error, _, _ = _apply(factory, idp_id, _staged(idp_id))

        assert isinstance(error, core_exceptions.SessionEndedError)
        assert _links(factory) == set()
