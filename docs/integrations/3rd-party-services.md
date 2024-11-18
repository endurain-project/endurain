# 3rd party services

---

## Strava Integration

To enable Strava integration, ensure your API endpoint is accessible from the internet and follow Strava's [API setup guide](https://developers.strava.com/docs/getting-started/). After the integration is successful the access and refresh tokens are stored in the DB. Each user will have his/hers own pair.

On Strava unlink action every data imported from Strava, i.e. activities and gears, will be deleted according to Strava [API Agreement](https://www.strava.com/legal/api).

For Strava integration [stravalib](https://github.com/stravalib/stravalib) Python module is used.

## Garmin Connect Integration

To enable Garmin Connect integration, Endurain will ask for your Garmin Connect credentials. These credentials are not stored, but the authentication tokens (access and refresh tokens) are stored in the DB, similar to the Strava integration. The credentials are sent from the frontend to the backend in plain text, so the use of HTTPS is highly recommended.

For Garmin Connect integration [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) Python module is used.