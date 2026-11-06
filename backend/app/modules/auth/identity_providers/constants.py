"""Identity-provider constants."""

from enum import StrEnum
from typing import TypedDict

#: Icon keys that ship with a bundled logo; the only values the ``icon`` field accepts. Any other logo is uploaded.
BUILTIN_ICONS = frozenset({"authelia", "authentik", "casdoor", "keycloak", "pocketid"})

#: Storage area of the uploaded provider icons, keyed by identity-provider id.
ICON_STORAGE_AREA = "identity_provider_icons"

#: How often the icon area is swept for blobs no provider names.
ICON_SWEEP_INTERVAL_MINUTES = 1440

#: How often the sign-ins of ended sessions that still hold a token are revoked at their provider.
TOKEN_REVOCATION_SWEEP_INTERVAL_MINUTES = 15

#: Largest accepted icon upload, in bytes. A provider logo is a small image shown to every visitor of the login page.
ICON_MAX_BYTES = 1024 * 1024

#: How long one refresh of an identity-provider token may hold its claim: longer than the provider calls it
#: makes, so a live refresh keeps it, and short enough that a lost worker blocks the next one only briefly.
TOKEN_REFRESH_CLAIM_TTL_SECONDS = 60

#: How recent the identity-provider sign-in of a step-up must be. Sent as ``max_age`` and enforced on the ID
#: token's ``auth_time``. Not 0: some providers read ``max_age=0`` as unset, and the margin absorbs whole-second
#: ``auth_time`` values and clock skew.
STEP_UP_MAX_AGE_SECONDS = 60

#: How long a step-up ticket stays redeemable after the provider's callback: long enough to finish what the
#: step-up was for (scanning an MFA enrolment code, typing a new email address), and still one request only,
#: in the session and browser that started it.
STEP_UP_TICKET_TTL_SECONDS = 300


class StepUpAction(StrEnum):
    """A sensitive operation a step-up re-authentication can authorise, so a ticket for one cannot pay for another.

    Attributes:
        API_KEY_CREATE: Create an API key.
        IDP_LINK: Mint a token that links an identity provider.
        IDP_UNLINK: Unlink an identity provider.
        EMAIL_CHANGE: Change the account's email address.
        ACCOUNT_DELETE: Delete the account.
        PROFILE_EXPORT: Export all of the account's data.
        MFA_ENABLE: Enable MFA.
        MFA_DISABLE: Disable MFA.
        MFA_BACKUP_CODES: Regenerate MFA backup codes.
        ADMIN_CREDENTIAL_RESET: An administrator sets another user's password.
        ADMIN_USER_EDIT: An administrator changes another user's email, access type or active flag.
        ADMIN_USER_DELETE: An administrator deletes another user's account.
        ADMIN_IDP_UNLINK: An administrator unlinks an identity provider from another user.
    """

    API_KEY_CREATE = "api_key_create"
    IDP_LINK = "idp_link"
    IDP_UNLINK = "idp_unlink"
    EMAIL_CHANGE = "email_change"
    ACCOUNT_DELETE = "account_delete"
    PROFILE_EXPORT = "profile_export"
    MFA_ENABLE = "mfa_enable"
    MFA_DISABLE = "mfa_disable"
    MFA_BACKUP_CODES = "mfa_backup_codes"
    ADMIN_CREDENTIAL_RESET = "admin_credential_reset"
    ADMIN_USER_EDIT = "admin_user_edit"
    ADMIN_USER_DELETE = "admin_user_delete"
    ADMIN_IDP_UNLINK = "admin_idp_unlink"


class IdentityProviderTemplate(TypedDict):
    """A built-in identity provider template, keyed by its template id in ``IDP_TEMPLATES``."""

    name: str
    provider_type: str
    issuer_url: str
    scopes: str
    icon: str
    user_mapping: dict[str, list[str]]
    description: str
    configuration_notes: str


#: Pre-configured templates for common identity providers, keyed by template id.
IDP_TEMPLATES: dict[str, IdentityProviderTemplate] = {
    "authelia": {
        "name": "Authelia",
        "provider_type": "oidc",
        "issuer_url": "https://{your-authelia-domain}",
        "scopes": "openid profile email",
        "icon": "authelia",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email"],
            "name": ["name"],
        },
        "description": "Authelia - Open-source authentication and authorization server",
        "configuration_notes": (
            "Replace {your-authelia-domain} with your Authelia server domain (e.g., auth.example.com). "
            "Configure an OIDC client in your Authelia configuration file."
        ),
    },
    "authentik": {
        "name": "Authentik",
        "provider_type": "oidc",
        "issuer_url": "https://{your-authentik-domain}/application/o/{slug}/",
        "scopes": "openid profile email",
        "icon": "authentik",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email", "mail"],
            "name": ["name", "display_name"],
        },
        "description": "Authentik - Open-source Identity Provider",
        "configuration_notes": (
            "Replace {your-authentik-domain} with your Authentik server domain (e.g., authentik.example.com) "
            "and {slug} with your application slug. Create an OAuth2/OIDC provider in Authentik."
        ),
    },
    "casdoor": {
        "name": "Casdoor",
        "provider_type": "oidc",
        "issuer_url": "https://{your-casdoor-domain}",
        "scopes": "openid profile email",
        "icon": "casdoor",
        "user_mapping": {
            "username": ["preferred_username", "username", "name"],
            "email": ["email"],
            "name": ["name", "displayName"],
        },
        "description": "Casdoor - Open-source Identity and Access Management (IAM) / Single-Sign-On (SSO) platform",
        "configuration_notes": (
            "Replace {your-casdoor-domain} with your Casdoor server domain (e.g., casdoor.example.com). "
            "Create an OAuth2/OIDC application in Casdoor admin console."
        ),
    },
    "keycloak": {
        "name": "Keycloak",
        "provider_type": "oidc",
        "issuer_url": "https://{your-keycloak-domain}/realms/{realm}",
        "scopes": "openid profile email",
        "icon": "keycloak",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email", "mail"],
            "name": ["name", "display_name", "full_name"],
        },
        "description": "Keycloak - Open Source Identity and Access Management",
        "configuration_notes": (
            "Replace {your-keycloak-domain} with your Keycloak server domain (e.g., keycloak.example.com) "
            "and {realm} with your realm name. Create an OIDC client in Keycloak admin console."
        ),
    },
    "pocketid": {
        "name": "Pocket ID",
        "provider_type": "oidc",
        "issuer_url": "https://{your-pocketid-domain}",
        "scopes": "openid profile email",
        "icon": "pocketid",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email"],
            "name": ["name"],
        },
        "description": "Pocket ID - Simple OIDC provider for passwordless passkey authentication",
        "configuration_notes": (
            "Replace {your-pocketid-domain} with your Pocket ID server domain (e.g., auth.example.com). "
            "Create a new OIDC client in Pocket ID admin panel and copy the Client ID, Client Secret, and "
            "OIDC Discovery URL."
        ),
    },
}
