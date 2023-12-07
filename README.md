# Frontend

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
JAEGER_HOST | jaeger | Yes
STRAVA_DAYS_ACTIVITIES_ONLINK | 30 | Yes

Table bellow shows the obligatory environemnt variables for mariadb container. You should set them based on what was also set for backend container.

Environemnt variable  | Default value | Optional
--- | --- | ---
MYSQL_ROOT_PASSWORD | changeme | `No`
MYSQL_DATABASE | gearguardian | `No`
MYSQL_USER | gearguardian | `No`
MYSQL_PASSWORD | changeme | `No`