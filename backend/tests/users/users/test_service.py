"""The users' account rules, on the real database: creation, sign-up, administrative edits, approval and timezones."""

import uuid
from datetime import UTC, datetime

import jasil.runtime as jasil_runtime
import pytest
import sqlalchemy as sa

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.account_security.events as account_security_events
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.schema as auth_schema
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sign_up_tokens.events as sign_up_tokens_events
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.health.health_weight.models as health_weight_models
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.crud as users_crud
import modules.users.users.events as users_events
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_profile.service as users_profile_service
from tests._factories.health import make_health_weight
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.server_settings import edit_server_settings
from tests._factories.tokens import make_mfa, make_reset_token, make_sign_up_token
from tests._factories.users import PASSWORD, audit_rows_of, make_admin, make_sign_up, make_user

_NEW_PASSWORD = "Another-Strong-Password-1!"
_Change = account_security_events.AccountSecurityChange


def _payloads(published, channel: str) -> list[dict]:
    return [event.payload for event in published if event.event_type == channel]


def _changes(published) -> list[tuple[str, str | None]]:
    """The account security notices as ``(user id, change)`` pairs, in order."""
    return [
        (payload["user_id"], payload["change"])
        for payload in _payloads(published, account_security_events.ACCOUNT_SECURITY_CHANGED)
    ]


def _stored(db, user_id) -> users_models.Users:
    row = db.get(users_models.Users, user_id)
    db.refresh(row)
    return row


def _step_up(**fields) -> auth_schema.StepUpVerification:
    return auth_schema.StepUpVerification(**({"current_password": PASSWORD} | fields))


@pytest.fixture
def actor(db):
    """The administrator who makes the changes."""
    created = make_admin(db)
    db.commit()
    return created


@pytest.fixture
def subject(db, actor):
    """A regular user the administrator changes."""
    created = make_user(db)
    db.commit()
    return created


def _edit(db, store, actor, subject, *, step_up=None, if_match=None, **changes):
    """Edit ``subject`` as ``actor`` with the version read now, after the step-up the call names."""
    return users_service.edit_user(
        subject.id,
        users_schema.UserEdit(**changes),
        step_up,
        actor.id,
        uuid.uuid4(),
        store,
        db,
        if_match=if_match or f'"{_stored(db, subject.id).version}"',
    )


class TestRequirements:
    def test_a_user_is_required_to_exist(self, db, subject):
        assert users_service.require_user(subject.id, db).id == subject.id
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_user(uuid.uuid4(), db)

    def test_an_inactive_user_is_refused_and_an_active_one_passes(self, db):
        users_service.require_active_user(make_user(db))
        with pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.require_active_user(make_user(db, active=False))

    def test_the_administrators_are_required_to_exist(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_admin_users(db)

        admin = make_admin(db)
        make_user(db)

        assert [user.id for user in users_service.require_admin_users(db)] == [admin.id]

    def test_an_administrator_cannot_act_on_their_own_account(self, subject, actor):
        users_service.require_other_user(subject.id, actor.id, "do it")
        with pytest.raises(core_exceptions.PermissionDeniedError, match="Use your account settings to do it"):
            users_service.require_other_user(actor.id, actor.id, "do it")


class TestPublicProjection:
    def test_an_active_user_is_projected_without_personal_or_account_fields(self, db, subject):
        profile = users_service.get_public_profile(subject.id, db)

        assert profile.id == subject.id
        assert not {"email", "access_type", "active", "height"} & set(profile.model_dump())

    @pytest.mark.parametrize("state", ["inactive", "pending", "missing"])
    def test_an_inactive_pending_or_missing_user_is_not_found(self, db, state):
        user_id = uuid.uuid4()
        if state == "inactive":
            user_id = make_user(db, active=False).id
        if state == "pending":
            user_id = make_sign_up(db, pending_admin_approval=True).id

        with pytest.raises(core_exceptions.NotFoundError):
            users_service.get_public_profile(user_id, db)

    def test_several_profiles_are_keyed_by_id_and_leave_out_the_ones_a_viewer_could_not_look_up(self, db):
        visible = make_user(db)
        inactive = make_user(db, active=False)
        pending = make_sign_up(db, pending_admin_approval=True)

        profiles = users_service.list_public_profiles([visible.id, inactive.id, pending.id, uuid.uuid4()], db)

        assert list(profiles) == [visible.id]
        assert users_service.list_public_profiles([], db) == {}

    @pytest.mark.parametrize(
        ("shared", "user_info", "visible"), [(False, True, False), (True, False, False), (True, True, True)]
    )
    def test_an_anonymous_viewer_sees_a_user_only_when_sharing_the_links_and_the_user_info_is_on(
        self, db, subject, shared, user_info, visible
    ):
        edit_server_settings(db, public_shareable_links=shared, public_shareable_links_user_info=user_info)

        if visible:
            assert users_service.get_public_user(subject.id, db).id == subject.id
        else:
            with pytest.raises(core_exceptions.NotFoundError):
                users_service.get_public_user(subject.id, db)

    def test_the_public_list_is_a_page_that_leaves_out_inactive_pending_and_undiscoverable_users(self, db):
        found = [make_user(db, username=name) for name in ("anna", "bruno", "carla")]
        make_user(db, username="inactive", active=False)
        make_sign_up(db, username="pending", pending_admin_approval=True)
        hidden = make_user(db, username="hidden")
        users_profile_service.edit_privacy_settings(
            hidden.id, users_privacy_settings_schema.UserPrivacySettingsUpdate(discoverable=False), db, if_match='"1"'
        )

        page = users_service.list_public_users(core_pagination.PageParams(1, 2), db)

        assert [item.username for item in page.items] == ["anna", "bruno"]
        assert (page.total, page.page, page.num_records) == (len(found), 1, 2)
        assert users_privacy_settings_integration.list_undiscoverable_user_ids(db) == [hidden.id]

    def test_the_public_list_narrows_by_username(self, db):
        make_user(db, username="anna")
        make_user(db, username="annabel")

        exact = users_service.list_public_users(core_pagination.PageParams(1, 10), db, username="ANNA")
        contains = users_service.list_public_users(core_pagination.PageParams(1, 10), db, username_contains="nab")

        assert ([i.username for i in exact.items], [i.username for i in contains.items]) == (["anna"], ["annabel"])


class TestListUsers:
    def test_each_user_carries_the_authentication_status(self, db):
        with_mfa = make_user(db, username="with-mfa")
        make_mfa(db, with_mfa)
        linked = make_user(db, username="linked")
        make_identity_link(db, linked.id, make_identity_provider(db, "list-idp"), "subject")

        page = users_service.list_users(db)

        by_name = {user.username: user for user in page.items}
        assert (by_name["with-mfa"].mfa_enabled, by_name["linked"].mfa_enabled) == (True, False)
        assert (by_name["linked"].external_auth_count, by_name["with-mfa"].external_auth_count) == (1, 0)
        assert page.total == 2

    def test_each_user_carries_the_email_change_waiting_for_confirmation(
        self, db, mail_configured, step_up_store, actor, subject
    ):
        _edit(db, step_up_store, actor, subject, step_up=_step_up(), email="changed@example.com")

        by_name = {user.username: user for user in users_service.list_users(db).items}

        assert by_name[subject.username].pending_email == "changed@example.com"
        assert by_name[actor.username].pending_email is None

    def test_the_filters_narrow_the_page_and_the_total(self, db):
        make_user(db, username="anna")
        make_user(db, username="bruno", active=False)
        linked = make_user(db, username="carla")
        make_identity_link(db, linked.id, make_identity_provider(db, "filter-idp"), "subject")

        assert [u.username for u in users_service.list_users(db, active=False).items] == ["bruno"]
        external = users_service.list_users(db, external_auth=True)
        assert ([u.username for u in external.items], external.total) == (["carla"], 1)
        assert users_service.list_users(db, external_auth=False).total == 2

    @pytest.mark.parametrize("external_auth", [True, False])
    def test_every_page_of_the_external_auth_filter_is_full_and_the_filter_is_exact(self, db, external_auth):
        users = [make_user(db) for _ in range(6)]
        idp = make_identity_provider(db, "paging-idp")
        linked = {user.id for user in users[1::2]}
        for user in users[1::2]:
            make_identity_link(db, user.id, idp, f"subject-{user.id}")
        expected = linked if external_auth else {user.id for user in users} - linked

        seen: set[uuid.UUID] = set()
        for page_number in range(1, len(expected) + 1):
            page = users_service.list_users(db, page_number=page_number, num_records=1, external_auth=external_auth)

            assert (page.total, len(page.items)) == (len(expected), 1)
            seen.add(page.items[0].id)

        assert seen == expected
        assert (
            users_service.list_users(
                db, page_number=len(expected) + 1, num_records=1, external_auth=external_auth
            ).items
            == []
        )

    def test_a_page_beyond_the_last_is_empty_with_the_full_total(self, db):
        make_user(db)

        page = users_service.list_users(db, page_number=5, num_records=10)

        assert (page.items, page.total, page.page) == ([], 1, 5)


class TestPendingEmailChange:
    def test_an_admin_read_carries_the_change_waiting_for_confirmation(
        self, db, mail_configured, step_up_store, actor, subject
    ):
        edited = _edit(db, step_up_store, actor, subject, step_up=_step_up(), email="changed@example.com")

        read = users_service.require_user_with_pending_email(subject.id, db)

        assert (read.pending_email, edited.pending_email) == ("changed@example.com", "changed@example.com")
        assert read.pending_email_expires_at is not None
        assert read.email == subject.email

    def test_a_user_without_a_pending_change_reads_none(self, db, subject):
        read = users_service.require_user_with_pending_email(subject.id, db)

        assert (read.pending_email, read.pending_email_expires_at) == (None, None)

    def test_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_user_with_pending_email(uuid.uuid4(), db)

    def test_an_edit_built_from_a_read_carries_neither_the_pending_change_nor_the_deletion_marker(self, db, subject):
        users_crud.stage_deletion_request(subject.id, db)

        edit = users_schema.UserEdit.from_read(users_service.require_user_with_pending_email(subject.id, db))

        assert not {"pending_email", "pending_email_expires_at", "deletion_requested_at"} & set(edit.model_dump())


class TestEmailAvailability:
    def test_another_accounts_address_is_taken_whatever_its_case(self, db, subject):
        other = make_user(db)

        assert users_service.is_email_available(other.id, subject.email.upper(), db) is False
        with pytest.raises(core_exceptions.ConflictError, match="Email is already in use"):
            users_service.require_email_available(other.id, subject.email, db)

    def test_a_free_address_or_the_users_own_is_available(self, db, subject):
        assert users_service.is_email_available(subject.id, subject.email, db) is True
        assert users_service.is_email_available(None, "free@example.com", db) is True
        users_service.require_email_available(subject.id, subject.email, db)


class TestCreateUser:
    def _new(self, **fields) -> users_schema.UserCreate:
        values = {
            "name": "New User",
            "username": "NewUser",
            "email": "New.User@Example.com",
            "active": True,
            "access_type": "regular",
            "password": PASSWORD,
        } | fields
        return users_schema.UserCreate(**values)

    def _create(self, db, store, actor, user, step_up=None):
        return users_service.create_user(user, step_up, actor.id, uuid.uuid4(), store, db)

    def test_the_account_is_stored_normalized_with_its_default_rows_and_password(
        self, db, step_up_store, actor, published
    ):
        created = self._create(db, step_up_store, actor, self._new())

        row = _stored(db, created.id)
        assert (row.username, row.email, row.access_type, row.active) == (
            "newuser",
            "new.user@example.com",
            "regular",
            True,
        )
        assert user_integrations_integration.get_user_integrations(created.id, db) is not None
        assert users_privacy_settings_integration.get_privacy_settings(created.id, db) is not None
        assert credentials_integration.get_password_hash(created.id, db) is not None
        assert published == []

    def test_a_password_an_administrator_chose_must_be_replaced_at_the_first_sign_in(self, db, step_up_store, actor):
        created = self._create(db, step_up_store, actor, self._new())

        assert credentials_integration.is_password_change_required(created.id, db) is True

    def test_the_creation_is_audited_with_how_and_as_whom_and_no_value(self, db, step_up_store, actor):
        created = self._create(db, step_up_store, actor, self._new())

        [row] = audit_rows_of(db, users_audit_actions.USER_CREATE.id)
        assert (row.target_id, row.target_owner_id) == (str(created.id), str(created.id))
        assert row.details["method"] == "admin"
        assert row.details["access_type"] == "regular"
        assert row.details["invited"] is False
        assert "email" not in row.details

    def test_a_taken_username_or_email_is_a_conflict_that_stores_nothing(self, db, step_up_store, actor, subject):
        with pytest.raises(core_exceptions.ConflictError):
            self._create(db, step_up_store, actor, self._new(email=subject.email))
        with pytest.raises(core_exceptions.ConflictError):
            self._create(db, step_up_store, actor, self._new(username=subject.username))

        assert users_crud.get_user_by_username("newuser", db) is None
        assert audit_rows_of(db, users_audit_actions.USER_CREATE.id) == []

    def test_a_weak_password_is_refused(self, db, step_up_store, actor):
        with pytest.raises(credentials_contracts.PasswordPolicyError):
            self._create(db, step_up_store, actor, self._new(password="short"))

        assert users_crud.get_user_by_username("newuser", db) is None

    def test_an_inactive_account_is_stamped_deactivated_and_an_active_one_is_not(self, db, step_up_store, actor):
        inactive = self._create(db, step_up_store, actor, self._new(active=False))
        active = self._create(db, step_up_store, actor, self._new(username="other", email="other@example.com"))

        assert _stored(db, inactive.id).deactivated_at is not None
        assert _stored(db, active.id).deactivated_at is None

    def test_a_regular_account_needs_no_step_up(self, db, step_up_store, actor):
        created = self._create(db, step_up_store, actor, self._new(), step_up=None)

        assert _stored(db, created.id).access_type == "regular"

    @pytest.mark.parametrize("step_up", [None, auth_schema.StepUpVerification(current_password="wrong-password")])
    def test_an_administrator_account_is_refused_without_the_creating_administrators_step_up(
        self, db, step_up_store, actor, step_up
    ):
        with pytest.raises(core_exceptions.StepUpFailedError):
            self._create(db, step_up_store, actor, self._new(access_type="admin"), step_up=step_up)

        assert users_crud.get_user_by_username("newuser", db) is None

    def test_an_administrator_account_is_created_after_the_step_up_and_the_other_administrators_are_told(
        self, db, step_up_store, actor, published
    ):
        other = make_admin(db)
        make_admin(db, active=False)
        db.commit()

        created = self._create(db, step_up_store, actor, self._new(access_type="admin"), step_up=_step_up())

        assert _stored(db, created.id).access_type == "admin"
        told = _payloads(published, users_events.USERS_ADMIN_PROMOTED)
        assert sorted(p["admin_user_id"] for p in told) == sorted([str(actor.id), str(other.id)])
        assert {p["user_id"] for p in told} == {str(created.id)}

    def test_a_new_regular_user_tells_no_administrator(self, db, step_up_store, actor, published):
        self._create(db, step_up_store, actor, self._new())

        assert _payloads(published, users_events.USERS_ADMIN_PROMOTED) == []

    def test_a_missing_password_without_mail_is_refused_before_anything_is_stored(self, db, step_up_store, actor):
        with pytest.raises(core_exceptions.PasswordRequiredError):
            self._create(db, step_up_store, actor, self._new(password=None))

        assert users_crud.get_user_by_username("newuser", db) is None

    def test_an_invited_account_has_no_credential_and_its_owner_is_mailed_an_invitation(
        self, db, mail_configured, step_up_store, actor, published
    ):
        created = self._create(db, step_up_store, actor, self._new(password=None))

        assert credentials_integration.get_password_hash(created.id, db) is None
        [invitation] = _payloads(published, sign_up_tokens_events.ADMIN_INVITATION_REQUESTED)
        assert invitation["user_id"] == str(created.id)
        [row] = audit_rows_of(db, users_audit_actions.USER_CREATE.id)
        assert row.details["invited"] is True

    def test_an_invited_administrator_still_needs_the_step_up(self, db, mail_configured, step_up_store, actor):
        with pytest.raises(core_exceptions.StepUpFailedError):
            self._create(db, step_up_store, actor, self._new(password=None, access_type="admin"))

        assert users_crud.get_user_by_username("newuser", db) is None

    def test_a_password_is_stored_and_no_invitation_sent_even_when_mail_is_configured(
        self, db, mail_configured, step_up_store, actor, published
    ):
        created = self._create(db, step_up_store, actor, self._new())

        assert credentials_integration.get_password_hash(created.id, db) is not None
        assert _payloads(published, sign_up_tokens_events.ADMIN_INVITATION_REQUESTED) == []


class TestFirstAdministrator:
    def _admin(self, **fields) -> users_schema.FirstAdminCreate:
        values = {"name": "Owner", "username": "Owner", "email": "Owner@Example.com", "password": PASSWORD} | fields
        return users_schema.FirstAdminCreate(**values)

    def test_the_first_account_is_an_active_verified_administrator_audited_as_onboarding(self, db):
        created = users_service.stage_first_admin(self._admin(), db)
        db.commit()

        row = _stored(db, created.id)
        assert (row.username, row.email, row.access_type, row.active, row.email_verified) == (
            "owner",
            "owner@example.com",
            "admin",
            True,
            True,
        )
        assert credentials_integration.is_password_change_required(created.id, db) is False
        [audit] = audit_rows_of(db, users_audit_actions.USER_CREATE.id)
        assert (audit.details["method"], audit.details["access_type"]) == ("onboarding", "admin")

    def test_a_second_account_is_refused_and_nothing_is_stored(self, db, subject):
        with pytest.raises(core_exceptions.ConflictError, match="An account already exists"):
            users_service.stage_first_admin(self._admin(), db)

        assert users_crud.get_user_by_username("owner", db) is None

    def test_a_password_below_the_administrator_policy_is_refused(self, db):
        with pytest.raises(credentials_contracts.PasswordPolicyError):
            users_service.stage_first_admin(self._admin(password="Short-1!"), db)

        assert users_crud.any_user_exists(db) is False

    def test_the_request_carries_no_access_type_or_account_state(self):
        assert not {"access_type", "active", "email_verified"} & set(users_schema.FirstAdminCreate.model_fields)


class TestSignUp:
    @pytest.mark.parametrize(
        ("verification", "approval", "active"),
        [(False, False, True), (True, False, False), (False, True, False), (True, True, False)],
    )
    def test_the_accounts_state_follows_the_sign_up_policy(self, db, verification, approval, active):
        settings = edit_server_settings(
            db, signup_require_email_verification=verification, signup_require_admin_approval=approval
        )

        created = users_service.stage_signup_user(
            users_schema.UserSignup(name="Sam", username="Sam", email="Sam@Example.com", password=PASSWORD),
            settings,
            db,
        )

        row = _stored(db, created.id)
        assert (row.active, row.pending_admin_approval, row.email_verified) == (active, approval, False)
        assert (row.username, row.email) == ("sam", "sam@example.com")

    def test_the_account_takes_the_servers_units_and_currency_and_the_chosen_language(self, db):
        settings = edit_server_settings(db, units="imperial", currency="dollar")

        created = users_service.stage_signup_user(
            users_schema.UserSignup(
                name="Sam", username="sam", email="sam@example.com", password=PASSWORD, preferred_language="pt-PT"
            ),
            settings,
            db,
        )

        row = _stored(db, created.id)
        assert (row.units, row.currency, row.preferred_language, row.access_type) == (
            "imperial",
            "dollar",
            "pt-PT",
            "regular",
        )

    def test_a_sign_up_stores_the_chosen_password_without_forcing_a_change_and_is_audited(self, db):
        settings = server_settings_integration.get_server_settings(db)

        created = users_service.stage_signup_user(
            users_schema.UserSignup(name="Sam", username="sam", email="sam@example.com", password=PASSWORD),
            settings,
            db,
        )
        db.commit()

        assert credentials_integration.get_password_hash(created.id, db) is not None
        assert credentials_integration.is_password_change_required(created.id, db) is False
        [row] = audit_rows_of(db, users_audit_actions.USER_CREATE.id)
        assert row.details["method"] == "sign_up"

    def test_a_sign_up_without_a_password_stores_no_credential(self, db):
        settings = server_settings_integration.get_server_settings(db)

        created = users_service.stage_signup_user(
            users_schema.UserSignup(name="Sam", username="sam", email="sam@example.com"), settings, db
        )

        assert credentials_integration.get_password_hash(created.id, db) is None

    def test_a_taken_address_gets_an_abstract_conflict(self, db, subject):
        settings = server_settings_integration.get_server_settings(db)

        with pytest.raises(core_exceptions.ConflictError, match=r"Unable to create user\."):
            users_service.stage_signup_user(
                users_schema.UserSignup(name="Sam", username="sam", email=subject.email), settings, db
            )

    def test_a_signup_commits_nothing_itself(self, committed_sessions):
        with committed_sessions() as db:
            settings = server_settings_integration.get_server_settings(db)
            users_service.stage_signup_user(
                users_schema.UserSignup(name="Sam", username="sam", email="sam@example.com"), settings, db
            )
            db.rollback()

        with committed_sessions() as db:
            assert users_crud.get_user_by_username("sam", db) is None

    def test_an_sso_account_keeps_its_mapped_profile_and_has_no_credential(self, db):
        settings = edit_server_settings(db, units="imperial")

        created = users_service.create_sso_user(
            users_schema.UserBase(name="Sam", username="Sam", email="Sam@Example.com", city="Porto"),
            settings,
            db,
            email_verified=True,
        )
        db.commit()

        row = _stored(db, created.id)
        assert (row.city, row.units, row.email_verified, row.active) == ("Porto", "imperial", True, True)
        assert credentials_integration.get_password_hash(created.id, db) is None
        [audit] = audit_rows_of(db, users_audit_actions.USER_CREATE.id)
        assert audit.details["method"] == "identity_provider"

    @pytest.mark.parametrize("verified", [True, False])
    def test_an_sso_account_is_verified_only_when_the_provider_says_so(self, db, verified):
        settings = edit_server_settings(db, signup_require_email_verification=True)

        created = users_service.create_sso_user(
            users_schema.UserBase(name="Sam", username="sam", email="sam@example.com"),
            settings,
            db,
            email_verified=verified,
        )

        row = _stored(db, created.id)
        assert (row.email_verified, row.active) == (verified, verified)

    def test_an_sso_account_awaiting_approval_asks_every_administrator_to_approve_it(
        self, db, mail_configured, published
    ):
        first, second = make_admin(db), make_admin(db)
        settings = edit_server_settings(db, signup_require_admin_approval=True)

        created = users_service.create_sso_user(
            users_schema.UserBase(name="Sam", username="sam", email="sam@example.com"),
            settings,
            db,
            email_verified=True,
        )
        db.commit()

        asked = _payloads(published, sign_up_tokens_events.SIGN_UP_APPROVAL_REQUESTED)
        assert sorted(p["admin_user_id"] for p in asked) == sorted([str(first.id), str(second.id)])
        assert {p["user_id"] for p in asked} == {str(created.id)}

    def test_an_sso_account_taken_by_another_gets_an_abstract_conflict(self, db, subject):
        settings = server_settings_integration.get_server_settings(db)

        with pytest.raises(core_exceptions.ConflictError, match=r"Unable to create user\."):
            users_service.create_sso_user(
                users_schema.UserBase(name="Sam", username="sam", email=subject.email),
                settings,
                db,
                email_verified=True,
            )


class TestAdministrativeEdit:
    def test_the_username_and_email_are_stored_in_lower_case_and_only_the_submitted_fields_change(
        self, db, step_up_store, actor, subject
    ):
        edited = _edit(
            db,
            step_up_store,
            actor,
            subject,
            step_up=_step_up(),
            username="Renamed.User",
            email="Renamed@Example.com",
            email_verified=True,
        )

        row = _stored(db, subject.id)
        assert (row.username, row.email, row.name) == ("renamed.user", "renamed@example.com", subject.name)
        assert edited.version == row.version == subject.version + 1

    def test_an_edit_of_other_fields_needs_no_step_up_and_keeps_the_sessions_and_the_generation(
        self, db, step_up_store, actor, subject
    ):
        before = security_generation_integration.current_generation(subject.id, db)

        edited = _edit(db, step_up_store, actor, subject, city="Faro", height=181)

        assert (edited.city, edited.height) == ("Faro", 181)
        assert security_generation_integration.current_generation(subject.id, db) == before

    def test_an_edit_that_resubmits_the_stored_values_needs_no_step_up(self, db, step_up_store, actor, subject):
        edited = _edit(
            db,
            step_up_store,
            actor,
            subject,
            username=subject.username.upper(),
            email=subject.email.upper(),
            access_type=subject.access_type,
            active=True,
            email_verified=subject.email_verified,
        )

        assert edited.version == subject.version

    @pytest.mark.parametrize(
        "changes",
        [
            {"email": "other@example.com"},
            {"access_type": "admin"},
            {"active": False},
            {"username": "renamed"},
            {"email_verified": False},
        ],
        ids=["email", "access_type", "active", "username", "email_verified"],
    )
    @pytest.mark.parametrize("step_up", [None, auth_schema.StepUpVerification(current_password="wrong-password")])
    def test_a_security_field_is_refused_without_the_administrators_step_up_and_nothing_changes(
        self, db, step_up_store, actor, step_up, changes
    ):
        subject = make_user(db, email_verified=True)
        db.commit()

        with pytest.raises(core_exceptions.StepUpFailedError):
            _edit(db, step_up_store, actor, subject, step_up=step_up, **changes)

        row = _stored(db, subject.id)
        assert (row.email, row.access_type, row.active, row.username, row.email_verified) == (
            subject.email,
            "regular",
            True,
            subject.username,
            True,
        )

    def test_an_administrator_cannot_change_their_own_email_here(self, db, step_up_store, actor):
        with pytest.raises(core_exceptions.PermissionDeniedError, match="Use your account settings"):
            _edit(db, step_up_store, actor, actor, step_up=_step_up(), email="mine@example.com")

        assert _stored(db, actor.id).email == actor.email

    def test_a_user_that_does_not_exist_is_not_found(self, db, step_up_store, actor):
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.edit_user(
                uuid.uuid4(), users_schema.UserEdit(city="x"), None, actor.id, uuid.uuid4(), step_up_store, db,
                if_match='"1"',
            )  # fmt: skip

    def test_a_stale_version_is_refused_and_changes_nothing(self, db, step_up_store, actor, subject):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            _edit(db, step_up_store, actor, subject, if_match='"99"', city="Faro")

        assert _stored(db, subject.id).city is None

    def test_a_taken_username_or_email_is_a_conflict_that_changes_nothing(self, db, step_up_store, actor, subject):
        other = make_user(db)
        db.commit()

        with pytest.raises(core_exceptions.ConflictError):
            _edit(db, step_up_store, actor, subject, step_up=_step_up(), username=other.username)
        with pytest.raises(core_exceptions.ConflictError):
            _edit(db, step_up_store, actor, subject, step_up=_step_up(), email=other.email, email_verified=True)

        row = _stored(db, subject.id)
        assert (row.username, row.email) == (subject.username, subject.email)

    def test_the_edit_audit_names_the_fields_that_changed_and_never_their_values(
        self, db, step_up_store, actor, subject
    ):
        _edit(db, step_up_store, actor, subject, city="Faro", name=subject.name, height=181)

        [row] = audit_rows_of(db, users_audit_actions.USER_UPDATE.id)
        assert row.details["changed_fields"] == ["city", "height"]
        assert "Faro" not in str(row.details)
        assert (row.target_id, row.target_owner_id) == (str(subject.id), str(subject.id))

    def test_an_edit_that_changes_nothing_writes_no_audit_row(self, db, step_up_store, actor, subject):
        _edit(db, step_up_store, actor, subject, name=subject.name)

        assert audit_rows_of(db, users_audit_actions.USER_UPDATE.id) == []

    def test_a_height_change_recalculates_the_bmi_of_the_manual_weight_records(self, db, step_up_store, actor, subject):
        record = make_health_weight(db, subject.id, weight_kg=70)
        db.commit()

        _edit(db, step_up_store, actor, subject, height=175)

        assert float(db.get(health_weight_models.HealthWeight, record.id).bmi) == pytest.approx(22.86, abs=0.01)

    def test_an_edit_of_the_weight_units_override_is_stored_and_can_be_cleared(self, db, step_up_store, actor, subject):
        _edit(db, step_up_store, actor, subject, weight_units="imperial")
        assert _stored(db, subject.id).weight_units == "imperial"

        _edit(db, step_up_store, actor, subject, weight_units=None)
        assert _stored(db, subject.id).weight_units is None

    def test_an_edit_that_leaves_the_override_out_keeps_it(self, db, step_up_store, actor):
        subject = make_user(db, weight_units="imperial")
        db.commit()

        _edit(db, step_up_store, actor, subject, city="Faro")

        assert _stored(db, subject.id).weight_units == "imperial"


class TestEmailChangeByAdministrator:
    def test_an_address_not_marked_verified_is_requested_and_the_stored_one_is_kept(
        self, db, mail_configured, step_up_store, actor, published
    ):
        subject = make_user(db, email_verified=True)
        db.commit()

        edited = _edit(db, step_up_store, actor, subject, step_up=_step_up(), email="new@example.com")

        row = _stored(db, subject.id)
        assert (row.email, row.email_verified) == (subject.email, True)
        assert (edited.email, edited.pending_email) == (subject.email, "new@example.com")
        token = db.scalars(
            sa.select(sign_up_models.SignUpToken).where(sign_up_models.SignUpToken.user_id == subject.id)
        )
        assert [(t.email, t.previous_email, t.used) for t in token] == [("new@example.com", subject.email, False)]
        assert len(_payloads(published, sign_up_tokens_events.EMAIL_CHANGE_VERIFICATION_REQUESTED)) == 1

    def test_the_security_generation_does_not_move_while_the_address_is_only_requested(
        self, db, mail_configured, step_up_store, actor, subject
    ):
        before = security_generation_integration.current_generation(subject.id, db)

        _edit(db, step_up_store, actor, subject, step_up=_step_up(), email="new@example.com")

        assert security_generation_integration.current_generation(subject.id, db) == before

    def test_an_address_marked_verified_is_applied_at_once_and_the_previous_address_is_told(
        self, db, mail_configured, step_up_store, actor, subject, published
    ):
        edited = _edit(
            db, step_up_store, actor, subject, step_up=_step_up(), email="new@example.com", email_verified=True
        )

        row = _stored(db, subject.id)
        assert (row.email, row.email_verified, edited.pending_email) == ("new@example.com", True, None)
        [notice] = _payloads(published, sign_up_tokens_events.EMAIL_CHANGED)
        assert notice["user_id"] == str(subject.id)

    def test_without_mail_the_address_is_applied_unverified(self, db, step_up_store, actor):
        subject = make_user(db, email_verified=True)
        db.commit()

        edited = _edit(db, step_up_store, actor, subject, step_up=_step_up(), email="new@example.com")

        row = _stored(db, subject.id)
        assert (row.email, row.email_verified, edited.pending_email) == ("new@example.com", False, None)

    def test_an_address_applied_without_the_verified_flag_is_stored_unverified_whatever_the_edit_says(
        self, db, step_up_store, actor
    ):
        subject = make_user(db, email_verified=True)
        db.commit()

        _edit(db, step_up_store, actor, subject, step_up=_step_up(), email="new@example.com", email_verified=False)

        assert _stored(db, subject.id).email_verified is False

    def test_a_new_address_moves_the_security_generation_and_voids_the_reset_links(
        self, db, step_up_store, actor, subject
    ):
        token = make_reset_token(db, subject)
        before = security_generation_integration.current_generation(subject.id, db)

        _edit(db, step_up_store, actor, subject, step_up=_step_up(), email="new@example.com")

        assert security_generation_integration.current_generation(subject.id, db) == before + 1
        assert token
        used = db.scalars(
            sa.select(password_reset_models.PasswordResetToken.used).where(
                password_reset_models.PasswordResetToken.user_id == subject.id
            )
        ).all()
        assert used == [True]

    def test_an_edit_that_keeps_the_address_keeps_the_reset_links(self, db, step_up_store, actor, subject):
        make_reset_token(db, subject)

        _edit(db, step_up_store, actor, subject, city="Faro")

        used = db.scalars(
            sa.select(password_reset_models.PasswordResetToken.used).where(
                password_reset_models.PasswordResetToken.user_id == subject.id
            )
        ).all()
        assert used == [False]

    def test_an_address_taken_by_another_account_is_a_conflict_before_anything_is_requested(
        self, db, mail_configured, step_up_store, actor, subject
    ):
        other = make_user(db)
        db.commit()

        with pytest.raises(core_exceptions.ConflictError):
            _edit(db, step_up_store, actor, subject, step_up=_step_up(), email=other.email)

        assert db.scalars(sa.select(sa.func.count(sign_up_models.SignUpToken.id))).one() == 0

    def test_a_request_together_with_a_deactivation_revokes_the_new_link_with_the_old_ones(
        self, db, mail_configured, step_up_store, actor, subject
    ):
        _edit(db, step_up_store, actor, subject, step_up=_step_up(), email="new@example.com", active=False)

        assert _stored(db, subject.id).active is False
        used = db.scalars(
            sa.select(sign_up_models.SignUpToken.used).where(sign_up_models.SignUpToken.user_id == subject.id)
        ).all()
        assert used == [True]


class TestDeactivationAndRoleByAdministrator:
    def test_deactivating_stamps_the_time_moves_the_generation_revokes_the_links_and_tells_the_user(
        self, db, step_up_store, actor, subject, published
    ):
        make_sign_up_token(db, subject)
        before = security_generation_integration.current_generation(subject.id, db)

        edited = _edit(db, step_up_store, actor, subject, step_up=_step_up(), active=False)

        row = _stored(db, subject.id)
        assert (edited.active, row.active) == (False, False)
        assert row.deactivated_at is not None
        assert security_generation_integration.current_generation(subject.id, db) == before + 1
        used = db.scalars(
            sa.select(sign_up_models.SignUpToken.used).where(sign_up_models.SignUpToken.user_id == subject.id)
        ).all()
        assert used == [True]
        assert _changes(published) == [(str(subject.id), _Change.ACCOUNT_DEACTIVATED_BY_ADMIN)]

    def test_reactivating_clears_the_time_and_tells_nobody_and_keeps_the_generation(
        self, db, step_up_store, actor, published
    ):
        subject = make_user(db, active=False)
        db.commit()
        before = security_generation_integration.current_generation(subject.id, db)

        _edit(db, step_up_store, actor, subject, step_up=_step_up(), active=True)

        row = _stored(db, subject.id)
        assert (row.active, row.deactivated_at) == (True, None)
        assert security_generation_integration.current_generation(subject.id, db) == before
        assert _changes(published) == []

    def test_leaving_an_inactive_account_inactive_keeps_the_original_deactivation_time(self, db, step_up_store, actor):
        stamp = datetime(2024, 5, 1, tzinfo=UTC)
        subject = make_user(db, active=False, deactivated_at=stamp)
        db.commit()

        _edit(db, step_up_store, actor, subject, city="Faro")

        assert _stored(db, subject.id).deactivated_at == stamp

    def test_an_administrator_deactivating_themselves_is_not_told(self, db, step_up_store, actor, published):
        make_admin(db)
        db.commit()

        _edit(db, step_up_store, actor, actor, step_up=_step_up(), active=False)

        assert _changes(published) == []

    def test_a_promotion_tells_the_user_their_new_role_and_every_other_active_administrator(
        self, db, step_up_store, actor, subject, published
    ):
        other = make_admin(db)
        make_admin(db, active=False)
        db.commit()

        _edit(db, step_up_store, actor, subject, step_up=_step_up(), access_type="admin")

        assert _stored(db, subject.id).access_type == "admin"
        [change] = _payloads(published, account_security_events.ACCOUNT_SECURITY_CHANGED)
        assert (change["user_id"], change["change"], change["access_type"]) == (
            str(subject.id),
            _Change.ROLE_CHANGED_BY_ADMIN,
            "admin",
        )
        told = _payloads(published, users_events.USERS_ADMIN_PROMOTED)
        assert sorted(p["admin_user_id"] for p in told) == sorted([str(actor.id), str(other.id)])

    def test_a_demotion_tells_the_user_and_no_administrator(self, db, step_up_store, actor, published):
        demoted = make_admin(db)
        db.commit()

        _edit(db, step_up_store, actor, demoted, step_up=_step_up(), access_type="regular")

        [change] = _payloads(published, account_security_events.ACCOUNT_SECURITY_CHANGED)
        assert (change["change"], change["access_type"]) == (_Change.ROLE_CHANGED_BY_ADMIN, "regular")
        assert _payloads(published, users_events.USERS_ADMIN_PROMOTED) == []

    def test_a_user_the_edit_also_deactivates_is_told_of_the_deactivation_only(
        self, db, step_up_store, actor, published
    ):
        demoted = make_admin(db)
        db.commit()

        _edit(db, step_up_store, actor, demoted, step_up=_step_up(), access_type="regular", active=False)

        assert _changes(published) == [(str(demoted.id), _Change.ACCOUNT_DEACTIVATED_BY_ADMIN)]

    def test_an_edit_that_keeps_the_role_tells_nobody(self, db, step_up_store, actor, subject, published):
        _edit(db, step_up_store, actor, subject, city="Faro")

        assert _changes(published) == []

    def test_an_administrator_changing_their_own_role_is_not_told(self, db, step_up_store, actor, published):
        make_admin(db)
        db.commit()

        _edit(db, step_up_store, actor, actor, step_up=_step_up(), access_type="regular")

        assert _changes(published) == []

    def test_a_new_username_sends_the_user_a_notice_and_a_difference_of_case_only_does_not(
        self, db, step_up_store, actor, subject, published
    ):
        _edit(db, step_up_store, actor, subject, step_up=_step_up(), username=subject.username.upper())
        assert _changes(published) == []

        _edit(db, step_up_store, actor, subject, step_up=_step_up(), username="renamed")

        assert _changes(published) == [(str(subject.id), _Change.USERNAME_CHANGED)]

    def test_a_user_awaiting_approval_cannot_be_activated_by_an_edit(self, db, step_up_store, actor):
        waiting = make_sign_up(db, pending_admin_approval=True)
        db.commit()

        with pytest.raises(core_exceptions.ApprovalPendingError, match="approve them with POST"):
            _edit(db, step_up_store, actor, waiting, step_up=_step_up(), active=True)

        row = _stored(db, waiting.id)
        assert (row.active, row.pending_admin_approval) == (False, True)

    def test_the_refusal_to_activate_a_user_awaiting_approval_is_audited_as_denied(self, db, step_up_store, actor):
        waiting = make_sign_up(db, pending_admin_approval=True)
        db.commit()

        with pytest.raises(core_exceptions.ApprovalPendingError):
            _edit(db, step_up_store, actor, waiting, step_up=_step_up(), active=True)

        [denied] = audit_rows_of(db, users_audit_actions.USER_UPDATE.id)
        assert (denied.outcome, denied.details) == ("denied", {"changed_fields": ["active"]})

    def test_other_fields_of_a_user_awaiting_approval_are_edited_and_a_deactivated_user_is_activated(
        self, db, step_up_store, actor
    ):
        waiting = make_sign_up(db, pending_admin_approval=True)
        deactivated = make_user(db, active=False)
        db.commit()

        _edit(db, step_up_store, actor, waiting, city="Faro")
        _edit(db, step_up_store, actor, deactivated, step_up=_step_up(), active=True)

        assert _stored(db, waiting.id).city == "Faro"
        assert _stored(db, deactivated.id).active is True


class TestLastAdministrator:
    @pytest.mark.parametrize("changes", [{"access_type": "regular"}, {"active": False}], ids=["demote", "deactivate"])
    def test_the_only_administrator_cannot_be_demoted_or_deactivated(self, db, step_up_store, actor, changes):
        with pytest.raises(core_exceptions.LastAdministratorError):
            _edit(db, step_up_store, actor, actor, step_up=_step_up(), **changes)

        row = _stored(db, actor.id)
        assert (row.access_type, row.active) == ("admin", True)

    @pytest.mark.parametrize("changes", [{"access_type": "regular"}, {"active": False}], ids=["demote", "deactivate"])
    def test_one_of_several_administrators_can_be_demoted_or_deactivated(self, db, step_up_store, actor, changes):
        other = make_admin(db)
        db.commit()

        _edit(db, step_up_store, actor, other, step_up=_step_up(), **changes)

        assert users_crud.lock_active_admin_ids(db) == [actor.id]

    def test_an_inactive_administrator_does_not_count_as_one_that_remains(self, db, step_up_store, actor):
        make_admin(db, active=False)
        db.commit()

        with pytest.raises(core_exceptions.LastAdministratorError):
            _edit(db, step_up_store, actor, actor, step_up=_step_up(), access_type="regular")

    def test_an_edit_that_keeps_the_administrator_is_not_refused(self, db, step_up_store, actor):
        edited = _edit(db, step_up_store, actor, actor, city="Faro")

        assert edited.city == "Faro"

    def test_a_deletable_user_is_one_that_exists_at_the_version_read_and_is_not_the_only_administrator(
        self, db, actor, subject
    ):
        users_service.require_deletable_user(subject.id, db, if_match=f'"{subject.version}"')
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.require_deletable_user(uuid.uuid4(), db, if_match='"1"')
        with pytest.raises(core_exceptions.PreconditionFailedError):
            users_service.require_deletable_user(subject.id, db, if_match='"99"')
        with pytest.raises(core_exceptions.LastAdministratorError):
            users_service.require_deletable_user(actor.id, db, if_match=f'"{actor.version}"')

    def test_an_administrator_can_be_deleted_while_another_remains(self, db, actor):
        other = make_admin(db)

        users_service.require_deletable_user(other.id, db, if_match=f'"{other.version}"')

    def test_the_version_is_checked_before_the_administrator_rule(self, db, actor):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            users_service.require_deletable_user(actor.id, db, if_match='"99"')


class TestProfileEdit:
    def test_only_the_self_service_fields_are_applied(self, db, subject):
        edited = users_service.stage_profile_edit(
            subject.id,
            users_schema.ProfileUpdate(city="Faro", timezone="Europe/Lisbon", weight_units="imperial"),
            db,
            if_match=f'"{subject.version}"',
        )

        row = _stored(db, subject.id)
        assert (edited.city, row.timezone, row.weight_units, row.access_type) == (
            "Faro",
            "Europe/Lisbon",
            "imperial",
            "regular",
        )

    def test_a_field_outside_the_allow_list_is_dropped(self, db, subject):
        smuggled = users_schema.ProfileUpdate.model_construct(
            city="Faro", access_type="admin", active=False, email_verified=True
        )

        users_service.stage_profile_edit(subject.id, smuggled, db, if_match=f'"{subject.version}"')

        row = _stored(db, subject.id)
        assert (row.city, row.access_type, row.active, row.email_verified) == ("Faro", "regular", True, True)

    def test_a_height_change_recalculates_the_bmi_and_another_edit_does_not(self, db, subject):
        record = make_health_weight(db, subject.id, weight_kg=80)
        users_service.stage_profile_edit(
            subject.id, users_schema.ProfileUpdate(city="Faro"), db, if_match=f'"{subject.version}"'
        )
        assert db.get(health_weight_models.HealthWeight, record.id).bmi is None

        users_service.stage_profile_edit(subject.id, users_schema.ProfileUpdate(height=200), db, if_match="*")

        db.refresh(db.get(health_weight_models.HealthWeight, record.id))
        assert float(db.get(health_weight_models.HealthWeight, record.id).bmi) == pytest.approx(20.0, abs=0.01)

    def test_a_missing_user_is_not_found_and_a_stale_version_is_refused(self, db, subject):
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.stage_profile_edit(uuid.uuid4(), users_schema.ProfileUpdate(city="x"), db, if_match="*")
        with pytest.raises(core_exceptions.PreconditionFailedError):
            users_service.stage_profile_edit(subject.id, users_schema.ProfileUpdate(city="x"), db, if_match='"99"')


class TestStagedIdentityChanges:
    def test_a_username_is_stored_lower_case_and_the_same_one_changes_nothing(self, db, subject):
        assert users_service.stage_username_change(subject.id, "New.Name", db) is True
        assert users_service.stage_username_change(subject.id, "NEW.NAME", db) is False

        assert _stored(db, subject.id).username == "new.name"

    def test_a_username_change_keeps_the_security_generation(self, db, subject):
        before = security_generation_integration.current_generation(subject.id, db)

        users_service.stage_username_change(subject.id, "new.name", db)

        assert security_generation_integration.current_generation(subject.id, db) == before

    def test_a_taken_username_is_a_conflict(self, db, subject):
        other = make_user(db)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_username_change(subject.id, other.username.upper(), db)

    def test_the_username_of_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.stage_username_change(uuid.uuid4(), "x", db)

    def test_a_new_address_is_stored_lower_case_unverified_and_voids_the_links_and_moves_the_generation(self, db):
        subject = make_user(db, email_verified=True)
        make_reset_token(db, subject)
        make_sign_up_token(db, subject)
        before = security_generation_integration.current_generation(subject.id, db)

        assert users_service.stage_email_change(subject.id, "New@Example.com", db) is True

        row = _stored(db, subject.id)
        assert (row.email, row.email_verified) == ("new@example.com", False)
        assert security_generation_integration.current_generation(subject.id, db) == before + 1
        assert db.scalars(sa.select(password_reset_models.PasswordResetToken.used)).all() == [True]
        assert db.scalars(sa.select(sign_up_models.SignUpToken.used)).all() == [True]

    def test_resubmitting_the_current_address_keeps_it_verified_and_the_links(self, db):
        subject = make_user(db, email_verified=True)
        make_reset_token(db, subject)

        assert users_service.stage_email_change(subject.id, subject.email.upper(), db) is False

        assert _stored(db, subject.id).email_verified is True
        assert db.scalars(sa.select(password_reset_models.PasswordResetToken.used)).all() == [False]

    def test_a_taken_address_or_a_missing_user_is_refused(self, db, subject):
        other = make_user(db)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_email_change(subject.id, other.email, db)
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.stage_email_change(uuid.uuid4(), "x@example.com", db)

    def test_a_confirmed_address_is_verified_audited_without_the_value_and_voids_the_reset_links(self, db, subject):
        make_reset_token(db, subject)
        before = security_generation_integration.current_generation(subject.id, db)

        users_service.stage_confirmed_email_change(subject.id, "Confirmed@Example.com", db)
        db.commit()

        row = _stored(db, subject.id)
        assert (row.email, row.email_verified) == ("confirmed@example.com", True)
        assert security_generation_integration.current_generation(subject.id, db) == before + 1
        assert db.scalars(sa.select(password_reset_models.PasswordResetToken.used)).all() == [True]
        [audit] = audit_rows_of(db, users_audit_actions.USER_EMAIL_CHANGE.id)
        assert (audit.target_id, audit.details) == (str(subject.id), None)

    def test_confirming_the_current_address_marks_it_verified_without_moving_the_generation(self, db):
        subject = make_user(db, email_verified=False)
        before = security_generation_integration.current_generation(subject.id, db)

        users_service.stage_confirmed_email_change(subject.id, subject.email, db)

        assert _stored(db, subject.id).email_verified is True
        assert security_generation_integration.current_generation(subject.id, db) == before

    def test_a_confirmed_address_of_another_account_or_a_missing_user_is_refused(self, db, subject):
        other = make_user(db)

        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_confirmed_email_change(subject.id, other.email, db)
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.stage_confirmed_email_change(uuid.uuid4(), "x@example.com", db)

    def test_a_provider_verified_address_is_applied_as_confirmed_and_the_previous_address_is_told(
        self, db, subject, published
    ):
        users_service.stage_synced_email_change(subject.id, "Synced@Example.com", db)
        db.commit()

        row = _stored(db, subject.id)
        assert (row.email, row.email_verified) == ("synced@example.com", True)
        [notice] = _payloads(published, sign_up_tokens_events.EMAIL_CHANGED)
        assert notice["user_id"] == str(subject.id)
        token = db.scalars(sa.select(sign_up_models.SignUpToken)).one()
        assert (token.email, token.previous_email) == ("synced@example.com", subject.email)


class TestApproval:
    def test_a_waiting_user_is_approved_activated_audited_and_told_when_mail_is_configured(
        self, db, mail_configured, published
    ):
        waiting = make_sign_up(db, pending_admin_approval=True, email_verified=True)
        db.commit()

        users_service.approve_user(waiting.id, db)

        row = _stored(db, waiting.id)
        assert (row.active, row.pending_admin_approval, row.deactivated_at) == (True, False, None)
        [approved] = _payloads(published, sign_up_tokens_events.SIGN_UP_APPROVED)
        assert approved["user_id"] == str(waiting.id)
        [audit] = audit_rows_of(db, users_audit_actions.USER_APPROVE.id)
        assert audit.target_id == str(waiting.id)

    def test_without_mail_the_user_is_approved_and_nobody_is_told(self, db, published):
        waiting = make_sign_up(db, pending_admin_approval=True, email_verified=True)

        users_service.approve_user(waiting.id, db)

        assert _stored(db, waiting.id).active is True
        assert published == []

    def test_an_unverified_address_blocks_the_approval_while_verification_is_required(self, db):
        edit_server_settings(db, signup_require_email_verification=True)
        waiting = make_sign_up(db, pending_admin_approval=True)
        db.commit()

        with pytest.raises(core_exceptions.ConflictError, match="email is not verified"):
            users_service.approve_user(waiting.id, db)

        assert _stored(db, waiting.id).pending_admin_approval is True

    def test_an_unverified_address_does_not_block_the_approval_when_verification_is_off(self, db):
        edit_server_settings(db, signup_require_email_verification=False)
        waiting = make_sign_up(db, pending_admin_approval=True)

        users_service.approve_user(waiting.id, db)

        assert _stored(db, waiting.id).active is True

    @pytest.mark.parametrize("state", ["approved", "deactivated", "queued"])
    def test_a_user_not_waiting_deactivated_or_queued_for_deletion_is_refused_and_the_refusal_audited(self, db, state):
        fields = {
            "approved": {"active": True},
            "deactivated": {"pending_admin_approval": True, "deactivated_at": datetime.now(UTC)},
            "queued": {"pending_admin_approval": True, "deletion_requested_at": datetime.now(UTC)},
        }[state]
        user = make_user(db, **({"active": False, "email_verified": True} | fields))
        db.commit()

        with pytest.raises(core_exceptions.ConflictError, match="not awaiting approval"):
            users_service.approve_user(user.id, db)

        assert _stored(db, user.id).active is (state == "approved")
        [audit] = audit_rows_of(db, users_audit_actions.USER_APPROVE.id)
        assert audit.outcome == "denied"

    def test_approving_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_service.approve_user(uuid.uuid4(), db)


class TestEmailVerification:
    def test_a_sign_up_is_verified_and_activated_without_the_approval_policy(self, db):
        waiting = make_sign_up(db)

        users_service.stage_email_verification(
            waiting.id, edit_server_settings(db, signup_require_admin_approval=False), db
        )

        row = _stored(db, waiting.id)
        assert (row.email_verified, row.active, row.pending_admin_approval) == (True, True, False)

    def test_a_sign_up_stays_pending_under_the_approval_policy(self, db):
        waiting = make_sign_up(db, pending_admin_approval=True)

        users_service.stage_email_verification(
            waiting.id, edit_server_settings(db, signup_require_admin_approval=True), db
        )

        row = _stored(db, waiting.id)
        assert (row.email_verified, row.active, row.pending_admin_approval) == (True, False, True)

    def test_a_deactivated_account_is_verified_but_never_activated(self, db):
        deactivated = make_user(db, active=False, email_verified=False)

        users_service.stage_email_verification(
            deactivated.id, edit_server_settings(db, signup_require_admin_approval=False), db
        )

        row = _stored(db, deactivated.id)
        assert (row.email_verified, row.active) == (True, False)

    def test_an_account_is_deactivated_only_when_an_administrator_or_a_deletion_request_did_it(self, db):
        assert users_service.is_deactivated(make_user(db).id, db) is False
        assert users_service.is_deactivated(make_user(db, active=False).id, db) is True
        assert users_service.is_deactivated(make_sign_up(db).id, db) is False


class TestTimezone:
    def test_the_users_own_zone_is_preferred_and_the_server_default_is_the_fallback(self, db):
        zoned = make_user(db, timezone="Asia/Tokyo")
        unset = make_user(db)

        assert users_service.resolve_user_timezone(zoned.id, db) == "Asia/Tokyo"
        assert users_service.resolve_user_timezone(unset.id, db) == users_service.timezone_or_default(None)
        assert users_service.resolve_user_timezone(uuid.uuid4(), db) == users_service.timezone_or_default(None)
        assert users_service.timezone_or_default("Europe/Lisbon") == "Europe/Lisbon"

    def test_today_is_the_calendar_date_in_the_users_zone_on_the_platform_clock(self, db):
        clock = jasil_runtime.get_active_platform().clock
        clock.moment = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)
        far_east = make_user(db, timezone="Pacific/Kiritimati")
        far_west = make_user(db, timezone="Pacific/Pago_Pago")

        assert users_service.user_local_today(far_east.id, db).isoformat() == "2025-03-11"
        assert users_service.user_local_today(far_west.id, db).isoformat() == "2025-03-10"
        clock.advance(23 * 3600)
        assert users_service.user_local_today(far_west.id, db).isoformat() == "2025-03-11"


class TestAdministratorCredentialActions:
    def test_a_password_set_by_an_administrator_replaces_the_old_one_and_must_be_changed_at_the_next_sign_in(
        self, db, step_up_store, actor, subject, published
    ):
        users_service.change_user_password(
            subject.id,
            users_schema.UserAdminEditPassword(password=_NEW_PASSWORD, step_up=_step_up()),
            actor.id,
            uuid.uuid4(),
            step_up_store,
            db,
        )

        stored = credentials_integration.get_password_hash(subject.id, db)
        verified, _ = credentials_integration.verify_and_update_password(
            _NEW_PASSWORD, stored, credentials_integration.get_password_hasher()
        )
        assert verified is True
        assert credentials_integration.is_password_change_required(subject.id, db) is True

    def test_a_failed_step_up_changes_nothing(self, db, step_up_store, actor, subject):
        before = credentials_integration.get_password_hash(subject.id, db)

        with pytest.raises(core_exceptions.StepUpFailedError):
            users_service.change_user_password(
                subject.id,
                users_schema.UserAdminEditPassword(
                    password=_NEW_PASSWORD, step_up=auth_schema.StepUpVerification(current_password="wrong-password")
                ),
                actor.id,
                uuid.uuid4(),
                step_up_store,
                db,
            )

        assert credentials_integration.get_password_hash(subject.id, db) == before

    def test_a_password_below_the_policy_is_refused(self, db, step_up_store, actor, subject):
        with pytest.raises(credentials_contracts.PasswordPolicyError):
            users_service.change_user_password(
                subject.id,
                users_schema.UserAdminEditPassword(password="short", step_up=_step_up()),
                actor.id,
                uuid.uuid4(),
                step_up_store,
                db,
            )

    def test_an_administrator_cannot_use_the_administrative_routes_on_their_own_account(self, db, step_up_store, actor):
        session_id = uuid.uuid4()
        with pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.change_user_password(
                actor.id,
                users_schema.UserAdminEditPassword(password=_NEW_PASSWORD, step_up=_step_up()),
                actor.id,
                session_id,
                step_up_store,
                db,
            )
        with pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.reset_user_mfa(
                actor.id, auth_schema.StepUpRequest(step_up=_step_up()), actor.id, session_id, step_up_store, db
            )
        with pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.require_user_password_change(
                actor.id, auth_schema.StepUpRequest(step_up=_step_up()), actor.id, session_id, step_up_store, db
            )
        with pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.unlink_identity_provider(
                actor.id, uuid.uuid4(), actor.id, session_id, _step_up(), step_up_store, db
            )

    def test_an_mfa_reset_removes_the_factors_and_tells_the_user(self, db, step_up_store, actor, subject, published):
        make_mfa(db, subject)
        db.commit()

        users_service.reset_user_mfa(
            subject.id, auth_schema.StepUpRequest(step_up=_step_up()), actor.id, uuid.uuid4(), step_up_store, db
        )

        assert mfa_integration.is_mfa_enabled_for_user(subject.id, db) is False
        assert _changes(published) == [(str(subject.id), _Change.MFA_RESET_BY_ADMIN)]

    def test_resetting_the_mfa_of_a_user_without_it_is_a_conflict(self, db, step_up_store, actor, subject):
        with pytest.raises(core_exceptions.ConflictError):
            users_service.reset_user_mfa(
                subject.id, auth_schema.StepUpRequest(step_up=_step_up()), actor.id, uuid.uuid4(), step_up_store, db
            )

    def test_a_failed_step_up_leaves_the_mfa_in_place(self, db, step_up_store, actor, subject):
        make_mfa(db, subject)
        db.commit()

        with pytest.raises(core_exceptions.StepUpFailedError):
            users_service.reset_user_mfa(
                subject.id,
                auth_schema.StepUpRequest(step_up=auth_schema.StepUpVerification(current_password="wrong-password")),
                actor.id,
                uuid.uuid4(),
                step_up_store,
                db,
            )

        assert mfa_integration.is_mfa_enabled_for_user(subject.id, db) is True

    def test_requiring_a_password_change_keeps_the_password_and_tells_the_user(
        self, db, step_up_store, actor, published
    ):
        subject = make_user(db)
        db.commit()
        before = credentials_integration.get_password_hash(subject.id, db)

        users_service.require_user_password_change(
            subject.id, auth_schema.StepUpRequest(step_up=_step_up()), actor.id, uuid.uuid4(), step_up_store, db
        )

        assert credentials_integration.get_password_hash(subject.id, db) == before
        assert credentials_integration.is_password_change_required(subject.id, db) is True
        assert _changes(published) == [(str(subject.id), _Change.PASSWORD_CHANGE_REQUIRED_BY_ADMIN)]

    def test_requiring_a_password_change_of_a_user_without_a_password_is_a_conflict(self, db, step_up_store, actor):
        subject = make_user(db, with_password=False)
        db.commit()

        with pytest.raises(core_exceptions.ConflictError):
            users_service.require_user_password_change(
                subject.id, auth_schema.StepUpRequest(step_up=_step_up()), actor.id, uuid.uuid4(), step_up_store, db
            )


class TestIdentityProviderLinks:
    def test_a_users_links_are_listed_a_page_at_a_time(self, db, subject):
        for slug in ("one", "two", "three"):
            make_identity_link(db, subject.id, make_identity_provider(db, f"links-{slug}"), f"subject-{slug}")

        page = users_service.list_identity_provider_links(subject.id, core_pagination.PageParams(2, 2), db)

        assert (len(page.items), page.total, page.page) == (1, 3, 2)

    def test_an_administrator_unlinks_a_provider_after_the_step_up_and_the_user_is_told(
        self, db, step_up_store, actor, subject, published
    ):
        idp = make_identity_provider(db, "unlink-idp")
        make_identity_link(db, subject.id, idp, "subject")
        db.commit()

        users_service.unlink_identity_provider(subject.id, idp, actor.id, uuid.uuid4(), _step_up(), step_up_store, db)

        assert users_service.list_identity_provider_links(subject.id, core_pagination.PageParams(1, 10), db).total == 0
        assert _changes(published) == [(str(subject.id), _Change.IDENTITY_PROVIDER_UNLINKED)]

    def test_the_last_way_to_sign_in_cannot_be_unlinked(self, db, step_up_store, actor):
        subject = make_user(db, with_password=False)
        idp = make_identity_provider(db, "last-idp")
        make_identity_link(db, subject.id, idp, "subject")
        db.commit()

        with pytest.raises(core_exceptions.LastSignInMethodError):
            users_service.unlink_identity_provider(
                subject.id, idp, actor.id, uuid.uuid4(), _step_up(), step_up_store, db
            )

        assert users_service.list_identity_provider_links(subject.id, core_pagination.PageParams(1, 10), db).total == 1

    def test_a_failed_step_up_unlinks_nothing(self, db, step_up_store, actor, subject):
        idp = make_identity_provider(db, "refused-idp")
        make_identity_link(db, subject.id, idp, "subject")
        db.commit()

        with pytest.raises(core_exceptions.StepUpFailedError):
            users_service.unlink_identity_provider(
                subject.id,
                idp,
                actor.id,
                uuid.uuid4(),
                auth_schema.StepUpVerification(current_password="wrong-password"),
                step_up_store,
                db,
            )

        assert users_service.list_identity_provider_links(subject.id, core_pagination.PageParams(1, 10), db).total == 1
