# Users API reference

## Users

::: backend.app.modules.users.users.router
    handler: python
    options:
      docstring_style: google

::: backend.app.modules.users.users.schema
    handler: python
    options:
      docstring_style: google

## Users profile

The profile router also serves the privacy settings routes (`/profile/privacy`). The profile's sessions, two-step verification and identity provider links (`/profile/sessions`, `/profile/mfa` and `/profile/idp`) are served by the auth module; see [Authentication](authentication.md).

::: backend.app.modules.users.users_profile.router
    handler: python
    options:
      docstring_style: google

::: backend.app.modules.users.users_profile.schema
    handler: python
    options:
      docstring_style: google

## Users goals

::: backend.app.modules.users.users_goals.router
    handler: python
    options:
      docstring_style: google

::: backend.app.modules.users.users_goals.schema
    handler: python
    options:
      docstring_style: google

## Users default gear

::: backend.app.modules.users.users_default_gear.router
    handler: python
    options:
      docstring_style: google

::: backend.app.modules.users.users_default_gear.schema
    handler: python
    options:
      docstring_style: google

## Users integrations

::: backend.app.modules.users.users_integrations.schema
    handler: python
    options:
      docstring_style: google

## Users privacy settings

::: backend.app.modules.users.users_privacy_settings.schema
    handler: python
    options:
      docstring_style: google
