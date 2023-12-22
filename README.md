Endurain is a Strava like service that you can selfhost.
It uses for the frontend PHP+HTML+basic JS+Bootstrap CSS, for the backend Python FastAPI and stravalib, MariaDB for the database engine and Jaeger for observability basic usage. 
Docker images are available to deploy the service and you can check "docker-compose.yml" file for an example. Environemnt variables detailed bellow.

I'm not a developer by profession (my dev concepts are from university ten years ago) so this work had a lot of help from ChatGPT and the main purpose was to learn new technologies and new concepts, so please be gentle.
If you have recommendations for any topic please let me know.

Currently the service supports:
 - Multi-user
 - Create/edit/delete users
 - Basic admin and regular users profiles that adapt the interface
 - Import activities using .gpx files
 - Connect with Strava and retrieve activities from Strava
 - Feed with user activities, current user week stats and month stats
 - Feed with followers activities
 - Basic activity privacy
 - Activity page with more in depth info of the activity
 - Delete activities
 - Create/edit/delete gear (wetsuit, bycicle and running shoes)
 - Add/edit/delete activity gear
 - User page with user stats and user activities per week
 - Follow user basic implementation

To do features (not by order):
 - Retrieve gear from Strava
 - Default gear for activity type
 - Track gear usage
 - Gear components logic for component usage tracking
 - Comments and likes logic for activities
 - Notifications logic
 - Activity Pub integration?
---
# Frontend
Table bellow shows supported environemnt variables. Variables marked with optional "No" should be set to avoid errors.

Environemnt variable  | Default value | Optional
--- | --- | ---
BACKEND_PROTOCOL | http | Yes
BACKEND_HOST | backend | Yes

Frontend dependencies:
 - php:8.3-apache
 - User avatars create using DiceBear (https://www.dicebear.com) avataaars style.
 - Bootstrap CSS v5.3.2
 - leaflet v1.7.1
 - fontawesome icons free version
 - Logo created using Canvas
 - https://geocode.maps.co/ for reverse Geocode logic on activity parsing
---
# Backend
For Strava integration API endpoint must be available to the Internet.

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

Table bellow shows the obligatory environemnt variables for mariadb container. You should set them based on what was also set for backend container.

Environemnt variable  | Default value | Optional
--- | --- | ---
MYSQL_ROOT_PASSWORD | changeme | `No`
MYSQL_DATABASE | gearguardian | `No`
MYSQL_USER | gearguardian | `No`
MYSQL_PASSWORD | changeme | `No`

Python backend dependencies used:
 - python:3.11
 - fastapi
 - pydantic
 - uvicorn
 - python-dotenv
 - sqlalchemy
 - mysqlclient
 - python-jose[cryptography]
 - passlib[bcrypt]
 - apscheduler
 - requests
 - stravalib
 - opentelemetry-sdk
 - opentelemetry-instrumentation-fastapi
 - opentelemetry.exporter.otlp
 - https://geocode.maps.co/ for reverse Geocode logic on activity parsing