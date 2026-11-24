"""The provider tokens a sign-in keeps: refreshing them, ending the provider's session and revoking them at logout."""

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa

import core.config as core_config
import core.cryptography as core_cryptography
import modules.auth.identity_provider_links.models as links_models
import modules.auth.identity_providers.models as idp_models
import modules.auth.identity_providers.refresh_claim_store as refresh_claim_store
import modules.auth.identity_providers.scheduled_jobs as idp_scheduled_jobs
import modules.auth.identity_providers.subscriber_registry as idp_subscriber_registry
import modules.auth.identity_providers.subscribers as idp_subscribers
from tests.auth.identity_providers.conftest import API
from tests.auth.identity_providers.sso_helpers import audit

NATIVE = "com.endurain.endurain:/auth/sso/callback"
REVOKE = "auth.session.revoke"
MOBILE = {"X-Client-Type": "mobile"}


@pytest.fixture(autouse=True)
def _wired(sso_sign_up) -> None:
    """Let accounts be created, and run the provider token subscribers as the application's worker does."""
    idp_subscriber_registry.register_bus_subscribers(platform_runtime.get_active_platform().events)


@pytest.fixture
def idp_id(make_provider):
    return make_provider("acme")


class Mobile:
    """A native client signed in through the provider, which holds its tokens in the body."""

    def __init__(self, browser, tokens) -> None:
        self.browser = browser
        self.tokens = tokens

    def refresh(self):
        return self.browser.client.post(
            f"{API}/auth/refresh", json={"refresh_token": self.tokens["refresh_token"]}, headers=MOBILE
        )

    def logout(self):
        return self.browser.client.post(
            f"{API}/auth/logout", json={"refresh_token": self.tokens["refresh_token"]}, headers=MOBILE
        )

    def alive(self) -> bool:
        return (
            self.browser.client.get(
                f"{API}/profile", headers={"Authorization": f"Bearer {self.tokens['access_token']}", **MOBILE}
            ).status_code
            == 200
        )


@pytest.fixture
def sign_in_mobile(browser, idp_id):
    def sign_in(slug="acme", **claims) -> Mobile:
        claims.setdefault("email", f"{uuid.uuid4().hex[:8]}@example.com")
        claims.setdefault("email_verified", True)
        _, finished = browser.sign_in(slug, redirect=NATIVE, **claims)
        from modules.auth.constants import ClientType

        exchanged = browser.exchange(finished.session_id, client_type=ClientType.MOBILE)
        assert exchanged.status_code == 200, exchanged.text
        return Mobile(browser, exchanged.json())

    return sign_in


def _stored(sessions) -> list[links_models.IdpSessionToken]:
    with sessions() as db:
        return list(db.scalars(sa.select(links_models.IdpSessionToken)))


def _age(sessions, **changes) -> None:
    with sessions() as db:
        db.execute(sa.update(links_models.IdpSessionToken).values(**changes))
        db.commit()


def _due(sessions) -> None:
    """Make the stored token one a refresh is due for: it expires within minutes and was last set minutes ago."""
    _age(
        sessions,
        access_token_expires_at=datetime.now(UTC) + timedelta(seconds=60),
        refresh_token_updated_at=datetime.now(UTC) - timedelta(minutes=10),
    )


def _grants(provider, grant) -> list[dict[str, str]]:
    return [form for _, _, form, _ in provider.requests_to("/token") if form.get("grant_type") == grant]


class TestStoredTokens:
    def test_a_sign_in_keeps_the_encrypted_tokens_and_the_provider_session_id(
        self, browser, sign_in_mobile, committed_sessions, provider
    ):
        provider.expires_in = 600

        sign_in_mobile(sid="provider-session")

        (row,) = _stored(committed_sessions)
        assert row.idp_sid == "provider-session"
        assert row.refresh_token and "rt-" not in row.refresh_token
        assert row.id_token and row.id_token.count(".") != 2
        assert row.access_token_expires_at > datetime.now(UTC) + timedelta(minutes=5)

    def test_a_provider_that_issues_no_refresh_token_still_records_which_provider_signed_in(
        self, browser, sign_in_mobile, committed_sessions, provider
    ):
        provider.token_body = None
        original = provider._token

        def without_refresh_token(form, headers):
            status, body, extra = original(form, headers)
            if isinstance(body, dict):
                body.pop("refresh_token", None)
            return status, body, extra

        provider._token = without_refresh_token

        sign_in_mobile()

        (row,) = _stored(committed_sessions)
        assert row.refresh_token is None

    def test_an_expires_in_sent_as_a_numeric_string_is_read(self, sign_in_mobile, committed_sessions, provider):
        provider.expires_in = "900"

        sign_in_mobile()

        assert _stored(committed_sessions)[0].access_token_expires_at > datetime.now(UTC) + timedelta(minutes=10)


class TestRefresh:
    def test_a_token_about_to_expire_is_refreshed_with_the_stored_refresh_token_and_replaced(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        provider.expires_in = 3600

        assert client.refresh().status_code == 200

        (grant,) = _grants(provider, "refresh_token")
        assert grant["refresh_token"].startswith("rt-")
        (after,) = _stored(committed_sessions)
        assert after.refresh_token != before.refresh_token
        assert after.refresh_token_updated_at is not None
        assert after.access_token_expires_at > datetime.now(UTC) + timedelta(minutes=30)

    def test_a_token_that_is_not_close_to_expiry_is_left_alone(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        (before,) = _stored(committed_sessions)

        assert client.refresh().status_code == 200

        assert _grants(provider, "refresh_token") == []
        assert _stored(committed_sessions)[0].refresh_token == before.refresh_token

    def test_a_token_refreshed_a_moment_ago_is_not_refreshed_again(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        _due(committed_sessions)

        first = client.refresh()
        client.tokens["refresh_token"] = first.json()["refresh_token"]
        second = client.refresh()

        assert (first.status_code, second.status_code) == (200, 200)
        assert len(_grants(provider, "refresh_token")) == 1

    def test_a_refresh_token_older_than_ninety_days_is_cleared_not_used(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _age(committed_sessions, refresh_token_updated_at=datetime.now(UTC) - timedelta(days=91))

        assert client.refresh().status_code == 200

        assert _stored(committed_sessions)[0].refresh_token is None
        assert _grants(provider, "refresh_token") == []

    def test_a_provider_that_refuses_the_refresh_token_ends_the_session(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _due(committed_sessions)
        provider.refresh_status = 400

        assert client.refresh().status_code == 200

        assert not client.alive()
        rows = audit(committed_sessions, REVOKE)
        assert [row.details for row in rows] == [{"sessions_revoked": 1}]
        assert _stored(committed_sessions) == []
        assert provider.revoked == []

    def test_a_provider_that_fails_keeps_the_session_and_the_token(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        provider.refresh_status = 503

        assert client.refresh().status_code == 200

        assert client.alive()
        assert _stored(committed_sessions)[0].refresh_token == before.refresh_token

    def test_a_provider_that_cannot_be_reached_keeps_the_token(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        with committed_sessions() as db:
            db.execute(sa.update(idp_models.IdentityProvider).values(token_endpoint="http://127.0.0.1:9/token"))
            db.commit()

        assert client.refresh().status_code == 200

        assert _stored(committed_sessions)[0].refresh_token == before.refresh_token

    def test_a_refresh_another_worker_is_running_is_skipped(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        _due(committed_sessions)
        (row,) = _stored(committed_sessions)
        claims = refresh_claim_store.IdpRefreshClaimStore(platform_runtime.get_state())
        assert claims.claim(row.session_id)

        assert client.refresh().status_code == 200

        assert _grants(provider, "refresh_token") == []
        claims.release(row.session_id)

    def test_a_stored_token_the_key_cannot_decrypt_is_cleared_and_the_session_lives_on(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _due(committed_sessions)
        _age(committed_sessions, refresh_token="not-a-fernet-token")

        assert client.refresh().status_code == 200

        assert _stored(committed_sessions)[0].refresh_token is None
        assert _grants(provider, "refresh_token") == []

    def test_a_disabled_provider_is_not_asked_to_refresh(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        _due(committed_sessions)
        with committed_sessions() as db:
            db.execute(sa.update(idp_models.IdentityProvider).values(enabled=False))
            db.commit()

        assert client.refresh().status_code == 200

        assert _grants(provider, "refresh_token") == []

    def test_a_malformed_refresh_response_keeps_the_token(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        provider.expires_in = "soon"

        assert client.refresh().status_code == 200

        assert _stored(committed_sessions)[0].refresh_token == before.refresh_token

    def test_the_id_token_of_a_refresh_replaces_the_stored_one_when_it_verifies(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile(sub="alice")
        _due(committed_sessions)
        provider.sub = "alice"
        (before,) = _stored(committed_sessions)
        provider.refresh_id_token_claims = {}
        provider.expires_in = 3600

        client.refresh()

        assert _stored(committed_sessions)[0].id_token != before.id_token

    @pytest.mark.parametrize("claims", [{"sub": "someone-else"}, {"aud": "another-client"}])
    def test_an_id_token_of_a_refresh_that_does_not_verify_is_dropped_and_the_stored_one_stays(
        self, claims, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile(sub="alice")
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        provider.refresh_id_token_claims = claims
        provider.expires_in = 3600

        client.refresh()

        (after,) = _stored(committed_sessions)
        assert after.id_token == before.id_token
        assert after.refresh_token != before.refresh_token


class TestEndSession:
    def test_a_mobile_logout_returns_the_providers_end_session_url_with_the_id_token_hint(
        self, sign_in_mobile, provider
    ):
        client = sign_in_mobile()

        response = client.logout()

        assert response.status_code == 200, response.text
        url = urlsplit(response.json()["idp_logout_url"])
        query = parse_qs(url.query)
        assert url.path == "/logout"
        assert query["id_token_hint"][0].count(".") == 2
        assert query["client_id"] == ["endurain-client"]
        assert "post_logout_redirect_uri" not in query
        assert not client.alive()

    def test_a_web_logout_also_names_the_login_page_to_return_to(self, browser, sso_account):
        import modules.auth.authentication.dependencies as authentication_dependencies

        response = browser.client.post(
            f"{API}/auth/logout",
            headers={
                "X-Client-Type": "web",
                "Origin": core_config.settings.ENDURAIN_HOST,
                "Cookie": f"{authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME}={sso_account.refresh_cookie}",
            },
        )

        assert response.status_code == 200, response.text
        query = parse_qs(urlsplit(response.json()["idp_logout_url"]).query)
        assert query["post_logout_redirect_uri"][0].endswith("/login")

    def test_a_provider_without_an_end_session_endpoint_leaves_the_provider_session_alone(
        self, sign_in_mobile, provider
    ):
        provider.discovery = {"end_session_endpoint": None}
        client = sign_in_mobile()

        response = client.logout()

        assert response.status_code == 200
        assert response.json()["idp_logout_url"] is None
        assert not client.alive()

    def test_an_end_session_endpoint_on_a_private_address_is_not_followed_unless_allowed(
        self, sign_in_mobile, provider, monkeypatch
    ):
        import core.config as core_config

        client = sign_in_mobile()
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", [])

        response = client.logout()

        assert response.status_code == 200
        assert response.json()["idp_logout_url"] is None

    def test_a_session_that_signed_in_without_a_provider_has_no_provider_logout(self, sign_in, committed_sessions):
        from tests._factories.users import make_user

        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        signed_in = sign_in(user)
        import modules.auth.authentication.dependencies as authentication_dependencies

        signed_in.client.cookies.set(authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME, signed_in.refresh_token)

        response = signed_in.client.post(f"{API}/auth/logout", headers={"Origin": core_config.settings.ENDURAIN_HOST})

        assert response.status_code == 200
        assert response.json()["idp_logout_url"] is None


class TestRevocationAtLogout:
    def test_logging_out_revokes_the_refresh_token_at_the_provider_and_forgets_the_sign_in(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()

        client.logout()

        assert len(provider.revoked) == 1 and provider.revoked[0].startswith("rt-")
        (_, _, form, headers) = provider.requests_to("/revoke")[0]
        assert form["token_type_hint"] == "refresh_token"
        assert headers["authorization"].startswith("Basic ")
        assert _stored(committed_sessions) == []

    def test_a_provider_that_cannot_revoke_now_keeps_the_sign_in_for_the_sweep(
        self, sign_in_mobile, committed_sessions, provider
    ):
        provider.revoke_status = 503
        client = sign_in_mobile()
        client.logout()
        assert len(_stored(committed_sessions)) == 1
        provider.revoke_status = 200

        idp_scheduled_jobs.revoke_ended_session_tokens()

        assert len(provider.revoked) == 2
        assert _stored(committed_sessions) == []

    def test_a_rate_limited_provider_is_retried_by_the_sweep(self, sign_in_mobile, committed_sessions, provider):
        provider.revoke_status = 429
        sign_in_mobile().logout()

        assert len(_stored(committed_sessions)) == 1

    @pytest.mark.parametrize("status", [400, 401, 404])
    def test_a_provider_that_refuses_the_revocation_for_good_is_not_asked_again(
        self, status, sign_in_mobile, committed_sessions, provider
    ):
        provider.revoke_status = status
        sign_in_mobile().logout()

        assert _stored(committed_sessions) == []

    def test_a_provider_without_a_revocation_endpoint_only_forgets_the_token(
        self, sign_in_mobile, committed_sessions, provider
    ):
        provider.discovery = {"revocation_endpoint": None}
        sign_in_mobile().logout()

        assert provider.requests_to("/revoke") == []
        assert _stored(committed_sessions) == []

    def test_a_provider_that_cannot_be_reached_keeps_the_sign_in(self, sign_in_mobile, committed_sessions, provider):
        provider.discovery = {"revocation_endpoint": "http://127.0.0.1:9/revoke"}
        sign_in_mobile().logout()

        assert len(_stored(committed_sessions)) == 1

    def test_an_unreachable_provider_holds_back_the_rest_of_its_sign_ins(
        self, sign_in_mobile, committed_sessions, provider
    ):
        provider.discovery = {"revocation_endpoint": "http://127.0.0.1:9/revoke"}
        first, second = sign_in_mobile(), sign_in_mobile()
        first.logout()
        second.logout()

        idp_scheduled_jobs.revoke_ended_session_tokens()

        assert len(_stored(committed_sessions)) == 2

    def test_a_token_the_key_cannot_decrypt_is_forgotten_without_a_request(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _age(committed_sessions, refresh_token="not-a-fernet-token")
        client.logout()

        assert provider.requests_to("/revoke") == []
        assert _stored(committed_sessions) == []

    def test_a_sign_in_without_a_refresh_token_is_forgotten(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        _age(committed_sessions, refresh_token=None)
        client.logout()

        assert provider.requests_to("/revoke") == []
        assert _stored(committed_sessions) == []

    def test_a_deleted_provider_leaves_nothing_to_revoke_at(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        with committed_sessions() as db:
            db.execute(sa.delete(idp_models.IdentityProvider))
            db.commit()
        client.logout()
        idp_scheduled_jobs.revoke_ended_session_tokens()

        assert provider.requests_to("/revoke") == []

    def test_the_sweep_revokes_the_tokens_of_sessions_that_expired_without_a_logout(
        self, sign_in_mobile, committed_sessions, provider
    ):
        import modules.auth.sessions.models as sessions_models

        sign_in_mobile()
        with committed_sessions() as db:
            db.execute(sa.delete(sessions_models.UsersSessions))
            db.commit()

        idp_scheduled_jobs.revoke_ended_session_tokens()

        assert len(provider.revoked) == 1
        assert _stored(committed_sessions) == []

    def test_unlinking_the_provider_revokes_its_tokens(self, sign_in_mobile, committed_sessions, provider):
        from tests._factories.users import PASSWORD

        client = sign_in_mobile(email="member@example.com")
        with committed_sessions() as db:
            user_id = db.scalar(sa.select(links_models.IdentityLink.user_id))
            # give the SSO account a password so that it may drop its only provider
            import modules.auth.credentials.integration_service as credentials_integration

            credentials_integration.set_local_password_hash(
                user_id,
                credentials_integration.get_password_hasher().hash_password(PASSWORD),
                db,
                change_required=False,
            )
            db.commit()

        response = client.browser.client.post(
            f"{API}/profile/identity-providers/{_idp_of(committed_sessions)}/unlink",
            json={"step_up": {"current_password": PASSWORD}},
            headers={"Authorization": f"Bearer {client.tokens['access_token']}", **MOBILE},
        )

        assert response.status_code == 204, response.text
        assert len(provider.revoked) == 1
        assert _stored(committed_sessions) == []


def _idp_of(sessions) -> uuid.UUID:
    with sessions() as db:
        return db.scalar(sa.select(links_models.IdentityLink.idp_id))


class TestRefreshWhileOtherThingsHappen:
    """The provider is called with no database session open, so the stored token can change meanwhile."""

    def test_a_refresh_whose_token_another_refresh_replaced_meanwhile_keeps_the_newer_token(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _due(committed_sessions)
        newer = core_cryptography.encrypt_token_fernet("stored-by-another-refresh")
        provider.on_token_request = lambda: _age(committed_sessions, refresh_token=newer)

        assert client.refresh().status_code == 200

        assert _stored(committed_sessions)[0].refresh_token == newer

    def test_a_refused_refresh_token_replaced_meanwhile_does_not_end_the_session(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _due(committed_sessions)
        provider.refresh_status = 400
        newer = core_cryptography.encrypt_token_fernet("stored-by-another-refresh")
        provider.on_token_request = lambda: _age(committed_sessions, refresh_token=newer)

        client.refresh()

        assert client.alive()
        assert _stored(committed_sessions)[0].refresh_token == newer

    def test_a_refused_refresh_token_of_a_session_that_ended_meanwhile_ends_nothing_twice(
        self, sign_in_mobile, committed_sessions, provider
    ):
        import modules.auth.sessions.models as sessions_models

        client = sign_in_mobile()
        _due(committed_sessions)
        provider.refresh_status = 400

        def end_the_session() -> None:
            with committed_sessions() as db:
                db.execute(sa.delete(sessions_models.UsersSessions))
                db.commit()

        provider.on_token_request = end_the_session

        client.refresh()

        assert audit(committed_sessions, REVOKE) == []

    def test_a_provider_that_refuses_the_refresh_for_another_reason_keeps_the_session_and_the_token(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        provider.refresh_status, provider.refresh_error = 400, "invalid_client"

        assert client.refresh().status_code == 200

        assert client.alive()
        assert _stored(committed_sessions)[0].refresh_token == before.refresh_token

    def test_a_provider_that_answers_the_refresh_too_slowly_keeps_the_token(
        self, sign_in_mobile, committed_sessions, provider, monkeypatch
    ):
        import modules.auth.identity_providers.oidc_client_service as oidc_client_service

        client = sign_in_mobile()
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        original = oidc_client_service.OidcClientService.create_oauth_client

        def impatient(self, *args, **kwargs):
            oauth_client = original(self, *args, **kwargs)
            oauth_client.timeout = 0.2
            return oauth_client

        monkeypatch.setattr(oidc_client_service.OidcClientService, "create_oauth_client", impatient)
        provider.delays = {"/token": 0.6}

        assert client.refresh().status_code == 200

        assert _stored(committed_sessions)[0].refresh_token == before.refresh_token

    def test_a_refresh_that_returns_no_new_refresh_token_keeps_the_stored_one(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        provider.refresh_issues_refresh_token = False

        assert client.refresh().status_code == 200

        assert len(_grants(provider, "refresh_token")) == 1
        assert _stored(committed_sessions)[0].refresh_token == before.refresh_token

    def test_a_stored_token_that_decrypts_to_nothing_is_cleared(self, sign_in_mobile, committed_sessions, provider):
        client = sign_in_mobile()
        _due(committed_sessions)
        _age(committed_sessions, refresh_token=core_cryptography.encrypt_token_fernet(""))

        assert client.refresh().status_code == 200

        assert _stored(committed_sessions)[0].refresh_token is None
        assert _grants(provider, "refresh_token") == []

    def test_a_refresh_for_a_sign_in_that_holds_no_token_does_nothing(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _age(committed_sessions, refresh_token=None)

        assert client.refresh().status_code == 200

        assert _grants(provider, "refresh_token") == []

    @pytest.mark.parametrize("raw", [12345, "not.a.verifiable.token"])
    def test_an_id_token_of_a_refresh_that_is_not_a_token_is_dropped_and_the_stored_one_stays(
        self, raw, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        provider.refresh_raw_id_token = raw

        client.refresh()

        (after,) = _stored(committed_sessions)
        assert after.id_token == before.id_token
        assert after.refresh_token != before.refresh_token

    def test_an_id_token_of_a_refresh_for_an_account_no_longer_linked_is_dropped(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile(sub="alice")
        _due(committed_sessions)
        (before,) = _stored(committed_sessions)
        with committed_sessions() as db:
            db.execute(sa.delete(links_models.IdentityLink))
            db.commit()
        provider.sub = "alice"
        provider.refresh_id_token_claims = {}

        client.refresh()

        assert _stored(committed_sessions)[0].id_token == before.id_token


class TestRefreshEvents:
    def _publish(self, **payload):
        import jasil.events as platform_events

        import modules.auth.identity_providers.events as idp_events

        platform_runtime.get_active_platform().events.publish(
            platform_events.new_event(idp_events.IDP_TOKEN_REFRESH_REQUESTED, payload, source="test")
        )

    def test_an_event_that_names_no_session_is_dropped(self, provider):
        self._publish(user_id=str(uuid.uuid4()), session_id=None)

        assert provider.requests == []

    def test_an_event_for_a_session_without_a_sign_in_is_dropped(self, provider):
        self._publish(user_id=str(uuid.uuid4()), session_id=str(uuid.uuid4()))

        assert provider.requests == []

    def test_an_event_for_a_token_that_is_not_due_asks_the_provider_for_nothing(
        self, sign_in_mobile, committed_sessions, provider
    ):
        sign_in_mobile()
        (row,) = _stored(committed_sessions)

        self._publish(user_id=str(row.user_id), session_id=str(row.session_id))

        assert _grants(provider, "refresh_token") == []

    def test_the_subscribers_are_registered_for_the_bus_and_for_durable_delivery(self):
        from jasil.jobs.registry import JobHandlerRegistry

        import modules.auth.identity_providers.events as idp_events
        import modules.auth.identity_providers.subscriber_registry as idp_subscriber_registry
        import modules.auth.sessions.events as sessions_events

        registry = JobHandlerRegistry()

        idp_subscriber_registry.register_durable_handlers(registry)

        assert registry.subscribers_for(idp_events.IDP_TOKEN_REFRESH_REQUESTED) == (
            idp_subscribers.IDP_TOKEN_REFRESH_SUBSCRIBER_ID,
        )
        assert registry.subscribers_for(sessions_events.SESSIONS_REVOKED) == (
            idp_subscribers.IDP_TOKEN_REVOKE_SUBSCRIBER_ID,
        )
        handler = registry.get(idp_subscribers.IDP_TOKEN_REFRESH_SUBSCRIBER_ID)
        assert handler is idp_subscribers.refresh_idp_tokens_for_event

    def test_the_recurring_jobs_are_the_icon_sweep_and_the_token_revocation_sweep(self):
        import modules.auth.identity_providers.constants as idp_constants

        jobs = idp_scheduled_jobs.recurring_jobs()

        assert {job.minutes for job in jobs} == {
            idp_constants.ICON_SWEEP_INTERVAL_MINUTES,
            idp_constants.TOKEN_REVOCATION_SWEEP_INTERVAL_MINUTES,
        }
        assert len({job.lock_name for job in jobs}) == 2


class TestRevocationEdgeCases:
    def test_a_provider_whose_discovery_document_is_unavailable_keeps_the_sign_in_for_a_later_pass(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _forget_discovery(client)
        provider.discovery_status = 500

        client.logout()

        assert provider.revoked == []
        assert len(_stored(committed_sessions)) == 1
        provider.discovery_status = 200
        idp_scheduled_jobs.revoke_ended_session_tokens()
        assert len(provider.revoked) == 1
        assert _stored(committed_sessions) == []

    def test_a_revocation_endpoint_on_a_private_address_is_not_called_and_the_token_is_forgotten(
        self, sign_in_mobile, committed_sessions, provider, monkeypatch
    ):
        import core.config as core_config

        client = sign_in_mobile()
        provider.discovery = {"revocation_endpoint": "http://10.0.0.5/revoke"}
        _forget_discovery(client)
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", ["127.0.0.1"])

        client.logout()

        assert provider.revoked == []
        assert _stored(committed_sessions) == []

    def test_a_provider_whose_credentials_cannot_be_read_keeps_the_sign_in(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        with committed_sessions() as db:
            db.execute(sa.update(idp_models.IdentityProvider).values(client_secret="not-encrypted"))
            db.commit()

        client.logout()

        assert provider.revoked == []
        assert len(_stored(committed_sessions)) == 1

    def test_a_sign_in_whose_token_was_replaced_during_the_revocation_is_kept(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        newer = core_cryptography.encrypt_token_fernet("stored-by-another-refresh")
        original = provider._route

        def replace_then_revoke(path, form, headers):
            if path == "/revoke":
                _age(committed_sessions, refresh_token=newer)
            return original(path, form, headers)

        provider._route = replace_then_revoke

        client.logout()

        assert len(provider.revoked) == 1
        assert _stored(committed_sessions)[0].refresh_token == newer

    def test_a_token_that_decrypts_to_nothing_is_forgotten_without_a_request(
        self, sign_in_mobile, committed_sessions, provider
    ):
        client = sign_in_mobile()
        _age(committed_sessions, refresh_token=core_cryptography.encrypt_token_fernet(""))

        client.logout()

        assert provider.requests_to("/revoke") == []
        assert _stored(committed_sessions) == []


def _forget_discovery(client) -> None:
    """Drop the cached discovery documents, so the next use reads the provider's current one."""
    state = platform_runtime.get_state()
    for key in list(state.iter_keys("endurain:idp:oidc-discovery")):
        state.delete(key)
