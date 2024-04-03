<div align="center">
  <img src="frontend/img/logo/logo.png" width="128" height="128">

  # Endurain
  
  <a title="Crowdin" target="_blank" href="https://crowdin.com/project/endurain"><img src="https://badges.crowdin.net/endurain/localized.svg"></a>

  A self-hosted fitness tracking service • Endurain <a href="https://fosstodon.org/@endurain">Mastodon</a> profile

  <img src="screenshot_01.png">
</div>

> [!WARNING]
> This project is currently in **Alpha** state. You can try it out at your own risk, but be aware that things might break and **DATA LOSS** may occur.

Endurain is a self-hosted fitness tracking service that operates much like Strava but allows users to have complete control over their data and the hosting environment. The application's frontend is built using a combination of PHP, HTML, basic JavaScript, and Bootstrap CSS. On the backend, it leverages Python FastAPI, Alembic, SQLAlchemy, stravalib and gpxpy for seamless integration with Strava and .gpx file import. The MariaDB database engine is employed to efficiently store and manage user data, while Jaeger is used for basic observability.

To deploy Endurain, Docker images are available, and a comprehensive example can be found in the "docker-compose.yml" file provided. Configuration is facilitated through environment variables, ensuring flexibility and ease of customization.

As a non-professional developer, my journey with Endurain involved learning and implementing new technologies and concepts, with invaluable assistance from ChatGPT. The primary motivation behind this project was to gain hands-on experience and expand my understanding of modern development practices. Second motivation is that I'm an amateur triathlete and I want to keep track of my gear and gear components usage.

If you have any recommendations or insights on improving any aspect of Endurain, whether related to technology choices, user experience, or any other relevant area, I would greatly appreciate your input. The goal is to create a reliable and user-friendly fitness tracking solution that caters to the needs of individuals who prefer self-hosted applications. Your constructive feedback will undoubtedly contribute to the refinement of Endurain.

Default credentials are:
 - User: admin
 - Password: admin

Currently the service supports:
 - Multi-user
 - Create/edit/delete users
 - Basic admin and regular users profiles that adapt the interface
 - Import activities using .gpx files
 - Connect with Strava and retrieve activities and gear from Strava
 - Feed with user activities, current user week stats and month stats
 - Feed with followers activities
 - Basic activity privacy
 - Activity page with more in depth info of the activity
 - Delete activities
 - Create/edit/delete gear (wetsuit, bycicle and running shoes)
 - Add/edit/delete activity gear
 - User page with user stats and user activities per week
 - Follow user basic implementation
 - Multi-language support, but currently only English is available
 - Basic gear tracking usage

To do features (not by order):
 - Support import of .fit files
 - Default gear for activity type
 - Gear components logic for component usage tracking
 - Comments and likes logic for activities
 - Notifications logic
 - Activity Pub integration?

More screenshots: https://imgur.com/a/lDR0sBf

---
# Frontend
Table bellow shows supported environemnt variables. Variables marked with optional "No" should be set to avoid errors.

Environemnt variable  | Default value | Optional
--- | --- | ---
BACKEND_PROTOCOL* | http | Yes
BACKEND_HOST** | backend | Yes

*BACKEND_PROTOCOL needs to be https if you want to enable Strava integration
**BACKEND_HOST needs to be set and be Internet faced/resolved if you want to enable Strava integration. Strava callback relies on this.

Frontend dependencies:
 - php:8.3-apache
 - User avatars create using DiceBear (https://www.dicebear.com) avataaars style.
 - Bootstrap CSS v5.3.2
 - leaflet v1.7.1
 - fontawesome icons free version
 - Logo created using Canvas

---
# Backend
Table bellow shows supported environemnt variables. Variables marked with optional "No" should be set to avoid errors.

Environemnt variable  | Default value | Optional
--- | --- | ---
DB_HOST | mariadb | Yes
DB_PORT | 3306 | Yes
DB_USER | gearguardian | Yes
DB_PASSWORD | changeme | `No`
DB_DATABASE | gearguardian | Yes
SECRET_KEY | changeme | `No`
ALGORITHM | HS256 | Yes
ACCESS_TOKEN_EXPIRE_MINUTES | 30 | Yes
STRAVA_CLIENT_ID | changeme | `No`
STRAVA_CLIENT_SECRET | changeme | `No`
STRAVA_AUTH_CODE | changeme | `No`
JAEGER_ENABLED | true | Yes
JAEGER_PROTOCOL | http | Yes
JAEGER_HOST | jaeger | Yes
JAGGER_PORT | 4317 | Yes
STRAVA_DAYS_ACTIVITIES_ONLINK | 30 | Yes
FRONTEND_HOST* | frontend | Yes
GEOCODES_MAPS_API** | changeme | `No`

*FRONTEND_HOST needs to be set if you want to enable Strava integration
**<a href="https://geocode.maps.co/">Geocode maps</a> offers a free plan consisting of 1 Request/Second. Registration necessary.

Table bellow shows the obligatory environemnt variables for mariadb container. You should set them based on what was also set for backend container.

Environemnt variable  | Default value | Optional
--- | --- | ---
MYSQL_ROOT_PASSWORD | changeme | `No`
MYSQL_DATABASE | gearguardian | `No`
MYSQL_USER | gearguardian | `No`
MYSQL_PASSWORD | changeme | `No`

Python backend dependencies used:
 - python:3.11
 - fastapi==0.108.0
 - pydantic==1.10.9
 - uvicorn==0.25.0
 - python-dotenv==1.0.0
 - sqlalchemy==2.0.25
 - mysqlclient==2.2.1
 - python-jose[cryptography]==3.3.0
 - passlib[bcrypt]==1.7.4
 - apscheduler==3.10.4
 - requests==2.31.0
 - stravalib==1.5
 - opentelemetry-sdk==1.22.0
 - opentelemetry-instrumentation-fastapi==0.43b0
 - opentelemetry.exporter.otlp==1.22.0
 - python-multipart==0.0.6
 - gpxpy==1.6.2
 - alembic==1.13.1

 ---
# Strava integration
For Strava integration API endpoint must be available to the Internet.
You will also need to create a API Application using a Strava account -> more info here https://developers.strava.com/docs/getting-started/