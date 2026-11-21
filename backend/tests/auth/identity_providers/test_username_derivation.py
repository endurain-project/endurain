"""An SSO account's username is valid and never carries any part of the email address."""

from types import SimpleNamespace

from pydantic import TypeAdapter

import modules.auth.identity_providers.claim_mapping as claim_mapping
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.user_provisioning_service as provisioning
import modules.users.users.schema as users_schema
from tests._factories.identity_links import make_oidc_provider
from tests._factories.users import make_user


def _username(subject: str, claims: dict) -> str:
    """The username a first sign-in with these claims starts from."""
    mapped = claim_mapping.map_user_claims(SimpleNamespace(user_mapping=None), claims)
    return provisioning.derive_sso_username(mapped.get("username"), subject)


def test_google_claims_without_preferred_username_get_a_subject_based_name():
    claims = {"sub": "1048576123456789", "email": "john.smith@gmail.com", "name": "John Smith"}

    assert _username("1048576123456789", claims) == "user_10485761"


def test_an_entra_upn_is_not_used():
    claims = {"sub": "AAAAAAAA-bbbb", "preferred_username": "john@contoso.com", "email": "john@contoso.com"}

    username = _username("AAAAAAAA-bbbb", claims)

    assert username == "user_AAAAAAAA"
    assert "john" not in username


def test_a_valid_preferred_username_is_kept():
    claims = {"sub": "abc", "preferred_username": "jane.doe", "email": "jane@example.com"}

    assert _username("abc", claims) == "jane.doe"


def test_invalid_characters_are_replaced_by_a_single_underscore_per_run():
    claims = {"sub": "abc", "preferred_username": "  Jöse +Silva  ", "email": "j@example.com"}

    assert _username("abc", claims) == "J_se_Silva"


def test_a_claim_with_nothing_usable_falls_back_to_the_subject():
    claims = {"sub": "abcdefghijkl", "preferred_username": "+++ ö", "email": "j@example.com"}

    assert _username("abcdefghijkl", claims) == "user_abcdefgh"


def test_a_subject_with_a_pipe_gives_a_valid_name():
    assert _username("auth0|5f7c8ec7c33c6c004bbafe82", {"email": "j@example.com"}) == "user_auth0_5f"


def test_a_short_or_unusable_subject_falls_back_to_a_hash():
    import core.hashing as core_hashing

    assert _username("|||", {"email": "j@example.com"}) == f"user_{core_hashing.sha256_hex('|||')[:8]}"


def test_a_subject_that_is_an_email_is_hashed():
    username = _username("john@contoso.com", {"email": "john@contoso.com"})

    assert "john" not in username
    assert len(username) == len("user_") + 8


def test_a_very_long_subject_gives_a_short_valid_name():
    assert _username("x" * 5000, {"email": "j@example.com"}) == "user_xxxxxxxx"


def test_the_uniqueness_suffix_keeps_the_username_valid_at_the_length_limit(db):
    base = "a" * provisioning.MAX_USERNAME_BASE_LENGTH
    make_user(db, username=base)
    idp = idp_crud.get_identity_provider(make_oidc_provider(db, "acme", "https://idp.example.com"), db)

    created = provisioning.create_user_from_idp(
        idp, "subject-1", {"username": "a" * 400, "email": "limit@example.com"}, db
    )

    assert TypeAdapter(users_schema.UserUsername).validate_python(created.username) == created.username
    assert created.username.startswith(base + "_")
    assert len(created.username) == 250
