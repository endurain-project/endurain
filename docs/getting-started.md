# Getting started

---

## Default Credentials

- **Username:** admin  
- **Password:** admin

## Docker Deployment

Endurain provides Docker images for simplified deployment. To get started, check out the `docker-compose.yml.example` file in the project repository and adjust it according to your setup.
Supported tags are:

- **latest:** contains the latest released version;
- **version, example "v0.3.0":** contains the app state available at the time of the version specified;
- **development version, example "dev_06092024":** contains a development version of the app at the date specified. This is not a stable released and may contain issues and bugs. Please do not open issues if using a version like this unless asked by me.

## Frontend Environment Variables
Table below shows supported environment variables. Variables marked with optional "No" should be set to avoid errors.

| Environment variable  | Default value | Optional | Notes |
| --- | --- | --- | --- |
| MY_APP_BACKEND_PROTOCOL | http | Yes | Needs to be `https` if you want to enable Strava integration. Strava callback relies on this. You may need to update this variable based on docker image spin up (api host or local ip (example: http://192.168.1.10:98)) |
| MY_APP_BACKEND_HOST | localhost:98 | Yes | Needs to be set and be Internet faced/resolved if you want to enable Strava integration. Strava callback relies on this. You may need to update this variable based on docker image spin up (api host or local ip (example: http://192.168.1.10:98)) |
| MY_APP_STRAVA_CLIENT_ID | changeme | Yes | Needs to be set with your Strava API Client ID if you want to enable Strava integration. |

Frontend dependencies:

- To check npm dependencies used, use npm file (package.json)
- User avatars create using DiceBear (https://www.dicebear.com) avataaars style.
- Logo created on Canva

## Backend Environment Variables
Table below shows supported environment variables. Variables marked with optional "No" should be set to avoid errors.

Environment variable  | Default value | Optional | Notes |
| --- | --- | --- | --- |
| TZ | UTC | Yes | Timezone definition. Useful for TZ calculation for activities that do not have coordinates associated, like indoor swim or weight training. If not specified UTC will be used. List of available time zones [here](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones). Format `Europe/Lisbon` expected |
| DB_HOST | mariadb | Yes | N/A |
| DB_PORT | 3306 | Yes | N/A |
| DB_USER | endurain | Yes | N/A |
| DB_PASSWORD | changeme | `No` | N/A |
| DB_DATABASE | endurain | Yes | N/A |
| SECRET_KEY | changeme | `No` | Run "openssl rand -hex 32" on a terminal to get a secret |
| ALGORITHM | HS256 | Yes | Currently only HS256 is supported |
| ACCESS_TOKEN_EXPIRE_MINUTES | 15 | Yes | Time in minutes |
| REFRESH_TOKEN_EXPIRE_DAYS | 7 | Yes | Time in days |
| STRAVA_CLIENT_ID | changeme | `No` | Needed if you want to enable the Strava integration |
| STRAVA_CLIENT_SECRET | changeme | `No` | Needed if you want to enable the Strava integration |
| STRAVA_AUTH_CODE | changeme | `No` | Needed if you want to enable the Strava integration |
| JAEGER_ENABLED | false | Yes | N/A |
| JAEGER_PROTOCOL | http | Yes | N/A |
| JAEGER_HOST | jaeger | Yes | N/A |
| JAGGER_PORT | 4317 | Yes | N/A |
| FRONTEND_PROTOCOL | http | Yes | Needs to be set if you want to enable Strava integration. You may need to update this variable based on docker image spin up (frontend host or local ip (example: http://192.168.1.10:8080)) |
| FRONTEND_HOST | frontend:8080 | Yes | Needs to be set if you want to enable Strava integration. You may need to update this variable based on docker image spin up (frontend host or local ip (example: http://192.168.1.10:8080)) |
| GEOCODES_MAPS_API | changeme | `No` | <a href="https://geocode.maps.co/">Geocode maps</a> offers a free plan consisting of 1 Request/Second. Registration necessary. |

Table below shows the obligatory environment variables for mariadb container. You should set them based on what was also set for backend container.

| Environemnt variable  | Default value | Optional | Notes |
| --- | --- | --- | --- |
| MYSQL_ROOT_PASSWORD | changeme | `No` | N/A |
| MYSQL_DATABASE | endurain | `No` | N/A |
| MYSQL_USER | endurain | `No` | N/A |
| MYSQL_PASSWORD | changeme | `No` | N/A |

To check Python backend dependencies used, use poetry file (pyproject.toml)

## Volumes

It is recommended to configure the following volumes for data persistence:

| Volume | Path | Notes |
| --- | --- | --- |
| /app/files/bulk_import | <local_path>/endurain/backend/files/bulk_import:/app/files/bulk_import | Necessary to enable bulk import of activities. Place here your activities files |
| /app/files/processed | <local_path>/endurain/backend/files/processed:/app/files/processed | Necessary for processed original files persistence on container image updates |
| /app/user_images | <local_path>/endurain/backend/user_images:/app/user_images | Necessary for user image persistence on container image updates |
| /app/logs | <local_path>/endurain/backend/logs:/app/logs | Log files for the backend |

## Bulk import and file upload

.fit files are preferred. I noticed that Strava/Garmin Connect process of converting .fit to .gpx introduces additional data to the activity file leading to minor variances in the data, like for example additional meters in distance and elevation gain.
Some notes:

- After the files are processed, the files are moved to the processed folder.
- GEOCODES API has a limit of 1 Request/Second on the free plan, so if you have a large number of files, it might not be possible to import all in the same action.