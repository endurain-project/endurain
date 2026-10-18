# Integrations

Endurain works with other apps and services. For building your own integration, see the [Integrate](../integrate/authentication.md) section.

## RunnerUp

[RunnerUp](https://github.com/jonasoreland/runnerup), an app for tracking your sport activities with your Android phone, can automatically sync your activities recorded with it to your Endurain instance.

RunnerUp currently **does not** support login with MFA.

## Gadgetbridge

[Gadgetbridge](https://gadgetbridge.org/) is an Android app for wearables. It signs in to Endurain through the system browser using SSO and a custom redirect scheme. An administrator must allow that scheme by adding `gadgetbridge` to `ALLOWED_REDIRECT_SCHEMES` (for example `endurain,gadgetbridge`); see [advanced setup](../getting-started/advanced-setup.md) and [OAuth/SSO and PKCE](../integrate/oauth-sso-pkce.md).

## Garmin Connect

To enable Garmin Connect integration, Endurain will ask for your Garmin Connect credentials. These credentials are not stored, but the authentication tokens (access and refresh tokens) are stored in the DB, similar to the Strava integration. The credentials are sent from the frontend to the backend in plain text, so the use of HTTPS is highly recommended.

Once the integration with Garmin Connect is configured, on startup, every one and four hours the backend will check if there is new unimported activities and new body composition entries respectively. If yes, the new data is automatically imported.

For Garmin Connect integration [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) Python module is used.

## Strava

!!! warning
    Due to Strava API changes, expect changes in the Strava integration in a future release.

To enable Strava integration, ensure your Endurain instance is accessible from the internet and follow Strava's [API setup guide](https://developers.strava.com/docs/getting-started/). After the integration is successful the access and refresh tokens are stored in the DB. Each user will have his/hers own pair.

Once the integration with Strava is configured, on startup and every hour the backend will check if there is new unimported activities. If yes, the new activity is automatically imported.

On link, user will need to provide his/her API client ID and secret. Pair will be temporary stored in the DB until the process finishes. Info is sent on a JSON payload and HTTPS end2end is encouraged.

On Strava unlink action every data imported from Strava, i.e. activities and gears, will be deleted according to Strava [API Agreement](https://www.strava.com/legal/api).

For Strava integration [stravalib](https://github.com/stravalib/stravalib) Python module is used.
