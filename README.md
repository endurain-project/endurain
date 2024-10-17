<div align="center">
  <img src="frontend/app/public/logo/logo.png" width="128" height="128">

  # Endurain

  <a title="Crowdin" target="_blank" href="https://crowdin.com/project/endurain"><img src="https://badges.crowdin.net/endurain/localized.svg"></a>
  ![License](https://img.shields.io/github/license/joaovitoriasilva/endurain)
  [![GitHub release](https://img.shields.io/github/v/release/joaovitoriasilva/endurain)](https://github.com/joaovitoriasilva/endurain/releases)
  [![GitHub stars](https://img.shields.io/github/stars/joaovitoriasilva/endurain.svg?style=social&label=Star)](https://github.com/joaovitoriasilva/endurain/stargazers)

  **A self-hosted fitness tracking service**  
  Visit Endurain's [Mastodon profile](https://fosstodon.org/@endurain).

  <img src="screenshot_01.png" alt="Endurain Screenshot">
</div>

> [!WARNING]
> This project is currently in **Alpha** state. You can try it out at your own risk, but be aware that things might break and **DATA LOSS** may occur.

## Table of Contents

- [What is Endurain?](#what-is-endurain)
- [Features](#features)
- [Planned Features](#planned-features)
- [Deployment Instructions](#deployment-instructions)
- [API Integration](#api-integration-v030)
- [Configuration](#configuration)
  - [Frontend Environment Variables](#frontend-environment-variables)
  - [Backend Environment Variables](#backend-environment-variables)
- [Volumes](#volumes)
- [Bulk import and file upload](#bulk-import-and-file-upload)
- [Strava Integration](#strava-integration)
- [Sponsors](#sponsors)
- [Contributing](#contributing)
- [License](#license)
- [Help Translate](#help-translate)
- [Community & Support](#community--support)

## What is Endurain?

Endurain is a self-hosted fitness tracking service designed to give users full control over their data and hosting environment. It's similar to Strava but focused on privacy and customization. Built with:

- **Frontend:** Vue.js and Bootstrap CSS
- **Backend:** Python FastAPI, Alembic, SQLAlchemy, stravalib for Strava integration, gpxpy and fitdecode for .gpx and .fit file import respectively 
- **Database:** MariaDB for efficient user data management
- **Observability:** Jaeger for basic tracing and monitoring

To deploy Endurain, Docker images are available, and a comprehensive example can be found in the "docker-compose.yml.example" file provided. Configuration is facilitated through environment variables, ensuring flexibility and ease of customization. More details bellow.

### Developer's Note

As a non-professional developer, my journey with Endurain involved learning and implementing new technologies and concepts, with invaluable assistance from ChatGPT. The primary motivation behind this project was to gain hands-on experience and expand my understanding of modern development practices. Second motivation is that I'm an amateur triathlete and I want to keep track of my gear and gear components usage.

If you have any recommendations or insights on improving any aspect of Endurain, whether related to technology choices, user experience, or any other relevant area, I would greatly appreciate your input. The goal is to create a reliable and user-friendly fitness tracking solution that caters to the needs of individuals who prefer self-hosted applications. Your constructive feedback will undoubtedly contribute to the refinement of Endurain.

## Features

Endurain currently supports:

- Multi-user functionality
- Admin and user profiles with adaptable interfaces
- Activity import via manual or bulk upload (.gpx and .fit files)
- Strava integration for syncing activities and gear
- Personalized activity feeds and statistics (week/month)
- Basic activity privacy settings
- Gear tracking (wetsuits, bicycles, shoes)
- User pages with stats and activity histories
- Follower features (view activities)
- Multi-language support (currently English only)
- Dark/light theme switcher
- Third-party app support
- Weight logging

## Planned Features

Upcoming features (in no particular order):

- Garmin Connect integration
- Simplified Docker images
- Live tracking
- Default gear for activity types
- Gear component tracking (e.g., track when components like bike chains need replacing)
- Activity comments and likes
- Notification system
- Potential ActivityPub integration

## Deployment Instructions

### Default Credentials

- **Username:** admin  
- **Password:** admin

### Docker Deployment

Endurain provides Docker images for simplified deployment. To get started, check out the `docker-compose.yml.example` file and adjust it according to your setup.
Supported tags are:
- **latest:** contains the latest released version;
- **version, example "v0.3.0":** contains the app state available at the time of the version specified;
- **development version, example "dev_06092024":** contains a development version of the app at the date specified. This is not a stable released and may contain issues and bugs. Please do not open issues if using a version like this unless asked by me.

## API Integration (v0.3.0+)

Endurain supports integration with other apps:

- For **web apps**, the backend sends access/refresh tokens as HTTP-only cookies.
- For **mobile apps**, tokens are included in the response body.

### API Requirements

- **Add a header:** Every request must include an `X-Client-Type` header with either `web` or `mobile` as the value. Requests with other values will receive a `403` error.
- **Activity Upload:** Use the `/activities/create/upload` endpoint (expects a .gpx or .fit file).

## Configuration

### Frontend Environment Variables
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

### Backend Environment Variables
Table below shows supported environment variables. Variables marked with optional "No" should be set to avoid errors.

Environment variable  | Default value | Optional | Notes |
--- | --- | --- | --- |
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
| STRAVA_DAYS_ACTIVITIES_ONLINK | 30 | Yes | On Strava integration setup the number of days (including today) to get activities. Strava free API limitations can limit number of days you can query in a given time |
| FRONTEND_PROTOCOL | http | Yes | Needs to be set if you want to enable Strava integration. You may need to update this variable based on docker image spin up (frontend host or local ip (example: http://192.168.1.10:8080)) |
| FRONTEND_HOST | frontend:8080 | Yes | Needs to be set if you want to enable Strava integration. You may need to update this variable based on docker image spin up (frontend host or local ip (example: http://192.168.1.10:8080)) |
| GEOCODES_MAPS_API | changeme | `No` | <a href="https://geocode.maps.co/">Geocode maps</a> offers a free plan consisting of 1 Request/Second. Registration necessary. |

Table below shows the obligatory environment variables for mariadb container. You should set them based on what was also set for backend container.

| Environemnt variable  | Default value | Optional | Notes |
| --- | --- | --- | ---
| MYSQL_ROOT_PASSWORD | changeme | `No` | N/A |
| MYSQL_DATABASE | endurain | `No` | N/A |
| MYSQL_USER | endurain | `No` | N/A |
| MYSQL_PASSWORD | changeme | `No` | N/A |

To check Python backend dependencies used, use poetry file (pyproject.toml)

## Volumes

It is recommended to configure the following volumes for data persistence:

| Volume | Path | Notes |
| --- | --- | --- |
| /app/files/bulk_import | <local_path>/endurain/backend/app/files/bulk_import:/app/files/bulk_import | Necessary to enable bulk import of activities. Place here your activities files |
| /app/files/processed | <local_path>/endurain/backend/app/files/processed:/app/files/processed | Necessary for processed original files persistence on container image updates |
| /app/user_images | <local_path>/endurain/backend/app/user_images:/app/user_images | Necessary for user image persistence on container image updates |
| /app/logs | <local_path>/endurain/backend/app.log:/app/logs | Log files for the backend |

## Bulk import and file upload

.fit files are preferred. I noticed that Strava/Garmin Connect process of converting .fit to .gpx introduces additional data to the activity file leading to minor variances in the data, like for example additional meters in distance and elevation gain.
Some notes:
- After the files are processed, the files are moved to the processed folder.
- GEOCODES API has a limit of 1 Request/Second on the free plan, so if you have a large number of files, it might not be possible to import all in the same action.

## Strava Integration

To enable Strava integration, ensure your API endpoint is accessible from the internet and follow Strava's [API setup guide](https://developers.strava.com/docs/getting-started/).

## Sponsors

A huge thank you to our sponsors! Your support helps keep this project going.

Consider [sponsoring Endurain on GitHub](https://github.com/sponsors/joaovitoriasilva) to ensure continuous development.

## Contributing

Contributions are welcomed! Please open an issue to discuss any changes or improvements before submitting a PR. Check out the [Contributing Guidelines](CONTRIBUTING.md) for more details.

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## Help Translate

Endurain has multi-language support, and you can help translate it into more languages via [Crowdin](https://crowdin.com/project/endurain). Currently, only English is available.