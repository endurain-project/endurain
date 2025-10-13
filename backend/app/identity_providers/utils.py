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
            "name": ["name", "display_name", "full_name"]
        },
        "description": "Keycloak - Open Source Identity and Access Management",
        "configuration_notes": "Replace {your-keycloak-domain} with your Keycloak server domain (e.g., keycloak.example.com) and {realm} with your realm name. Create an OIDC client in Keycloak admin console."
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
            "name": ["name", "display_name"]
        },
        "description": "Authentik - Open-source Identity Provider",
        "configuration_notes": "Replace {your-authentik-domain} with your Authentik server domain (e.g., authentik.example.com) and {slug} with your application slug. Create an OAuth2/OIDC provider in Authentik."
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
            "name": ["name"]
        },
        "description": "Authelia - Open-source authentication and authorization server",
        "configuration_notes": "Replace {your-authelia-domain} with your Authelia server domain (e.g., auth.example.com). Configure an OIDC client in your Authelia configuration file."
    },
    "google": {
        "name": "Google",
        "provider_type": "oidc",
        "issuer_url": "https://accounts.google.com",
        "scopes": "openid profile email",
        "icon": "fa-google",
        "user_mapping": {
            "username": ["email"],
            "email": ["email"],
            "name": ["name"]
        },
        "description": "Google OAuth 2.0",
        "configuration_notes": "Create OAuth 2.0 credentials in Google Cloud Console."
    },
    "microsoft": {
        "name": "Microsoft",
        "provider_type": "oidc",
        "issuer_url": "https://login.microsoftonline.com/{tenant}/v2.0",
        "scopes": "openid profile email",
        "icon": "fa-microsoft",
        "user_mapping": {
            "username": ["preferred_username", "email"],
            "email": ["email"],
            "name": ["name"]
        },
        "description": "Microsoft Azure AD / Entra ID",
        "configuration_notes": "Replace {tenant} with your tenant ID or 'common'. Register an app in Azure Portal."
    }
}


def get_idp_templates() -> List[idp_schema.IdentityProviderTemplate]:
    """
    Retrieve a list of identity provider templates.

    Returns:
        List[idp_schema.IdentityProviderTemplate]: A list of IdentityProviderTemplate instances,
        each representing a predefined identity provider template.
    """
    templates = []
    for template_id, template_data in IDP_TEMPLATES.items():
        templates.append(
            idp_schema.IdentityProviderTemplate(
                template_id=template_id,
                **template_data
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
