"""``PATCH /identity-providers/{id}`` on the real application: a field the client omits keeps its stored value."""

import socket
import uuid
from types import SimpleNamespace

import pytest

import core.config as core_config
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.schema as idp_schema
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.users import PASSWORD, make_admin, make_user

_API = core_config.ROOT_PATH
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_HOST = "idp.example.org"


@pytest.fixture(autouse=True)
def _host_resolves(monkeypatch) -> None:
    """Make the host a provider URL names resolve, as the DNS the check asks is a third party."""
    real = socket.getaddrinfo

    def resolve(name, *args, **kwargs):
        if name == _HOST:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real(name, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


@pytest.fixture
def ctx(app, committed_sessions, sign_in) -> SimpleNamespace:
    """An administrator signed in, and the factory of the providers the tests edit."""
    with committed_sessions() as db:
        admin = make_admin(db, timezone="UTC")
        db.commit()
    return SimpleNamespace(sessions=committed_sessions, admin=admin, client=sign_in(admin).client)


def _provider(ctx: SimpleNamespace, *, linked: bool = False) -> uuid.UUID:
    """Commit an enabled OAuth2 provider, optionally with a linked user, and return its id."""
    with ctx.sessions() as db:
        idp_id = make_identity_provider(db, f"p-{uuid.uuid4().hex[:10]}")
        if linked:
            make_identity_link(db, make_user(db).id, idp_id, "subject")
        db.commit()
    return idp_id


def _oidc_provider(ctx: SimpleNamespace, issuer_url: str) -> uuid.UUID:
    """Commit an OIDC provider with an issuer and return its id."""
    with ctx.sessions() as db:
        state = idp_crud.create_identity_provider(
            idp_schema.IdentityProviderCreate(
                name="Issuer",
                slug=f"i-{uuid.uuid4().hex[:10]}",
                issuer_url=issuer_url,
                client_id="client-id",
                client_secret="client-secret",
            ),
            db,
        )
        db.commit()
    return state.id


def _stored(ctx: SimpleNamespace, idp_id: uuid.UUID):
    with ctx.sessions() as db:
        state = idp_crud.get_identity_provider(idp_id, db)
    assert state is not None
    return state


def _patch(ctx: SimpleNamespace, idp_id: uuid.UUID, body: dict, version: int = 1):
    return ctx.client.patch(
        f"{_API}/identity-providers/{idp_id}", json={**body, **_STEP_UP}, headers={"If-Match": f'"{version}"'}
    )


def _problem_type(response) -> str:
    return response.json()["type"].rsplit(":", 1)[-1]


class TestOmittedFieldsAreKept:
    def test_enabling_a_provider_keeps_its_name_slug_and_settings(self, ctx):
        idp_id = _provider(ctx)
        before = _stored(ctx, idp_id)

        response = _patch(ctx, idp_id, {"enabled": False})

        assert response.status_code == 200, response.text
        assert response.headers["ETag"] == '"2"'
        after = _stored(ctx, idp_id)
        assert after.enabled is False
        for field in ("name", "slug", "provider_type", "scopes", "token_endpoint", "link_by_email", "sync_email"):
            assert getattr(after, field) == getattr(before, field), field

    def test_a_nullable_field_is_cleared_with_null(self, ctx):
        idp_id = _provider(ctx)

        response = _patch(ctx, idp_id, {"userinfo_endpoint": None})

        assert response.status_code == 200, response.text
        after = _stored(ctx, idp_id)
        assert after.userinfo_endpoint is None
        assert after.token_endpoint == "https://idp.example.com/token"

    def test_the_stored_credentials_are_kept_when_omitted(self, ctx):
        idp_id = _provider(ctx)
        before = _stored(ctx, idp_id)

        assert _patch(ctx, idp_id, {"name": "Renamed"}).status_code == 200

        after = _stored(ctx, idp_id)
        assert after.client_id == before.client_id
        assert after.name == "Renamed"


class TestFieldRules:
    @pytest.mark.parametrize(
        "field",
        [
            "name",
            "slug",
            "provider_type",
            "enabled",
            "scopes",
            "auto_create_users",
            "link_by_email",
            "sync_user_info",
            "sync_email",
            "client_id",
            "client_secret",
        ],
    )
    def test_null_on_a_field_the_provider_always_has_is_422(self, ctx, field):
        idp_id = _provider(ctx)

        response = _patch(ctx, idp_id, {field: None})

        assert response.status_code == 422, response.text
        assert _stored(ctx, idp_id).version == 1

    @pytest.mark.parametrize(
        "body", [{"slug": "Bad Slug"}, {"slug": "login"}, {"icon": "no-such-icon"}, {"name": ""}, {"scopes": "x" * 501}]
    )
    def test_the_field_rules_still_apply_to_the_fields_sent(self, ctx, body):
        idp_id = _provider(ctx)

        response = _patch(ctx, idp_id, body)

        assert response.status_code == 422, response.text


class TestRulesAcrossFields:
    def test_a_partial_change_to_oidc_without_an_issuer_gets_the_status_a_full_update_gets(self, ctx):
        partial_id, full_id = _provider(ctx), _provider(ctx)
        full = _stored(ctx, full_id)

        partial = _patch(ctx, partial_id, {"provider_type": "oidc"})
        complete = _patch(ctx, full_id, {"name": full.name, "slug": full.slug, "provider_type": "oidc"})

        assert partial.status_code == complete.status_code == 400
        assert _problem_type(partial) == _problem_type(complete)
        assert "issuer_url" in partial.json()["detail"]
        assert _stored(ctx, partial_id).provider_type == "oauth2"

    def test_removing_the_openid_scope_from_an_oidc_provider_is_refused(self, ctx):
        idp_id = _oidc_provider(ctx, f"https://{_HOST}/a")

        response = _patch(ctx, idp_id, {"scopes": "profile email"})

        assert response.status_code == 400, response.text
        assert "openid" in response.json()["detail"]

    def test_clearing_the_issuer_of_an_oidc_provider_is_refused(self, ctx):
        idp_id = _oidc_provider(ctx, f"https://{_HOST}/b")

        response = _patch(ctx, idp_id, {"issuer_url": None})

        assert response.status_code == 400, response.text
        assert _stored(ctx, idp_id).issuer_url == f"https://{_HOST}/b"

    def test_an_issuer_another_provider_uses_is_refused_as_issuer_in_use(self, ctx):
        taken = f"https://{_HOST}/{uuid.uuid4().hex[:8]}"
        _oidc_provider(ctx, taken)
        idp_id = _oidc_provider(ctx, f"https://{_HOST}/{uuid.uuid4().hex[:8]}")

        response = _patch(ctx, idp_id, {"issuer_url": taken})

        assert response.status_code == 409
        assert _problem_type(response) == "issuer-in-use"

    def test_a_provider_with_linked_users_refuses_a_locked_field_but_accepts_the_others(self, ctx):
        idp_id = _provider(ctx, linked=True)

        locked = _patch(ctx, idp_id, {"token_endpoint": f"https://{_HOST}/token"})
        allowed = _patch(ctx, idp_id, {"name": "Renamed", "enabled": False})

        assert locked.status_code == 409
        assert _problem_type(locked) == "identity-provider-locked"
        assert "token_endpoint" in locked.json()["detail"]
        assert allowed.status_code == 200, allowed.text
        assert _stored(ctx, idp_id).name == "Renamed"

    def test_a_locked_field_sent_with_its_stored_value_is_not_a_change(self, ctx):
        idp_id = _provider(ctx, linked=True)
        slug = _stored(ctx, idp_id).slug

        assert _patch(ctx, idp_id, {"slug": slug}).status_code == 200


class TestVersioning:
    def test_a_stale_if_match_is_412_and_a_missing_one_is_428(self, ctx):
        idp_id = _provider(ctx)

        stale = _patch(ctx, idp_id, {"enabled": False}, version=7)
        missing = ctx.client.patch(f"{_API}/identity-providers/{idp_id}", json={"enabled": False, **_STEP_UP})

        assert stale.status_code == 412
        assert missing.status_code == 428
        assert _stored(ctx, idp_id).version == 1
