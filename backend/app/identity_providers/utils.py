"""Identity Provider utility functions and templates"""

from typing import List, Dict, Any
import identity_providers.schema as idp_schema


# Pre-configured templates for common IdPs
IDP_TEMPLATES = {
    "keycloak": {
        "name": "Keycloak",
        "provider_type": "oidc",
        "issuer_url": "https://{your-keycloak-domain}/realms/{realm}",
        "scopes": "openid profile email",
        "icon": "fa-key",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email", "mail"],
            "name": ["name", "display_name", "full_name"],
        },
        "description": "Keycloak - Open Source Identity and Access Management",
        "configuration_notes": "Replace {your-keycloak-domain} with your Keycloak server domain (e.g., keycloak.example.com) and {realm} with your realm name. Create an OIDC client in Keycloak admin console.",
    },
    "authentik": {
        "name": "Authentik",
        "provider_type": "oidc",
        "issuer_url": "https://{your-authentik-domain}/application/o/{slug}/",
        "scopes": "openid profile email",
        "icon": "fa-shield-alt",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email", "mail"],
            "name": ["name", "display_name"],
        },
        "description": "Authentik - Open-source Identity Provider",
        "configuration_notes": "Replace {your-authentik-domain} with your Authentik server domain (e.g., authentik.example.com) and {slug} with your application slug. Create an OAuth2/OIDC provider in Authentik.",
    },
    "authelia": {
        "name": "Authelia",
        "provider_type": "oidc",
        "issuer_url": "https://{your-authelia-domain}",
        "scopes": "openid profile email",
        "icon": "fa-lock",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email"],
            "name": ["name"],
        },
        "description": "Authelia - Open-source authentication and authorization server",
        "configuration_notes": "Replace {your-authelia-domain} with your Authelia server domain (e.g., auth.example.com). Configure an OIDC client in your Authelia configuration file.",
    },
    "google_consumer": {
        "name": "Google",
        "provider_type": "oidc",
        "issuer_url": "https://accounts.google.com",
        "scopes": "openid profile email",
        "icon": "fa-google",
        "user_mapping": {"username": ["email"], "email": ["email"], "name": ["name"]},
        "description": "Google OAuth 2.0",
        "configuration_notes": "Create OAuth 2.0 credentials in Google Cloud Console.",
    },
    "microsoft_entra": {
        "name": "Microsoft Entra ID",
        "provider_type": "oidc",
        "issuer_url": "https://login.microsoftonline.com/{tenant}/v2.0",
        "scopes": "openid profile email",
        "icon": "fa-microsoft",
        "user_mapping": {
            "username": ["preferred_username", "email"],
            "email": ["email"],
            "name": ["name"],
        },
        "description": "Microsoft Entra ID (Azure AD) - Enterprise Accounts",
        "configuration_notes": "Replace {tenant} with your tenant ID (for single tenant) or 'organizations' (for multi-tenant). Register an app in Azure Portal under 'App registrations'.",
    },
    "microsoft_consumer": {
        "name": "Microsoft Account",
        "provider_type": "oidc",
        "issuer_url": "https://login.microsoftonline.com/consumers/v2.0",
        "scopes": "openid profile email",
        "icon": "fa-microsoft",
        "user_mapping": {
            "username": ["preferred_username", "email"],
            "email": ["email"],
            "name": ["name"],
        },
        "description": "Microsoft Account - Consumer Accounts (Outlook, Hotmail, Xbox)",
        "configuration_notes": "For personal Microsoft accounts only (@outlook.com, @hotmail.com, @live.com, Xbox accounts). Register an app in Azure Portal with 'Accounts in any organizational directory and personal Microsoft accounts' option.",
    },
}


def get_idp_templates() -> List[idp_schema.IdentityProviderTemplate]:
    """
    Retrieve a list of identity provider templates, excluding specific providers.

    Returns:
        List[idp_schema.IdentityProviderTemplate]: 
            A list of IdentityProviderTemplate objects for all identity providers 
            except 'microsoft_consumer', 'microsoft_entra', and 'google_consumer'.
    """
    templates = []
    for template_id, template_data in IDP_TEMPLATES.items():
        if (
            template_id == "microsoft_consumer"
            or template_id == "microsoft_entra"
            or template_id == "google_consumer"
        ):
            continue
        templates.append(
            idp_schema.IdentityProviderTemplate(
                template_id=template_id, **template_data
            )
        )
    return templates


def get_idp_template(template_id: str) -> Dict[str, Any] | None:
    """
    Retrieve an identity provider template by its template ID.

    Args:
        template_id (str): The unique identifier of the identity provider template.

    Returns:
        dict[str, Any] | None: The template dictionary if found, otherwise None.
    """
    return IDP_TEMPLATES.get(template_id)
