# Strava API reference

Strava linking, sync and bulk export import. See [Integrations](../features/integrations.md) and [Importing data](../features/importing.md).

## Routes

::: backend.app.modules.strava.router
    handler: python
    options:
      docstring_style: google

## Account linking

::: backend.app.modules.strava.service
    handler: python
    options:
      docstring_style: google

## Activity sync

::: backend.app.modules.strava.activity_service
    handler: python
    options:
      docstring_style: google

## Gear sync

::: backend.app.modules.strava.gear_service
    handler: python
    options:
      docstring_style: google

## Bulk import

::: backend.app.modules.strava.bulk_import_service
    handler: python
    options:
      docstring_style: google

## Client and token handling

::: backend.app.modules.strava.client_service
    handler: python
    options:
      docstring_style: google

## Rate limits

::: backend.app.modules.strava.rate_limit_store
    handler: python
    options:
      docstring_style: google

## Schemas

::: backend.app.modules.strava.schema
    handler: python
    options:
      docstring_style: google
