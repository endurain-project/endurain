## Default Credentials

- **Username:** admin  
- **Password:** admin

## Docker Deployment

Endurain provides a Docker image for simplified deployment. To get started, check out the `docker-compose.yml.example` file in the project repository and adjust it according to your setup. Supported tags are:

- **latest:** contains the latest released version;
- **version, example "v0.3.0":** contains the app state available at the time of the version specified;
- **development version, example "dev_06092024":** contains a development version of the app at the date specified. This is not a stable released and may contain issues and bugs. Please do not open issues if using a version like this unless asked by me.

## Supported Environment Variables
Table below shows supported environment variables. Variables marked with optional "No" should be set to avoid errors.

| Environment variable  | Default value | Optional | Notes |
| --- | --- | --- | --- |
| UID | 1000 | Yes | User ID for mounted volumes. Default is 1000 |
| GID | 1000 | Yes | Group ID for mounted volumes. Default is 1000 |
| TZ | UTC | Yes | Timezone definition. Useful for TZ calculation for activities that do not have coordinates associated, like indoor swim or weight training. If not specified UTC will be used. List of available time zones [here](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones). Format `Europe/Lisbon` expected |
| FRONTEND_DIR | `/app/frontend/dist` | Yes | You will only need to change this value if installing using bare metal method |
| BACKEND_DIR | `/app/backend` | Yes | You will only need to change this value if installing using bare metal method |
| DATA_DIR | `/app/backend/data` | Yes | You will only need to change this value if installing using bare metal method |
| LOGS_DIR | `/app/backend/logs` | Yes | You will only need to change this value if installing using bare metal method |
| ENDURAIN_HOST | No default set | `No` | Required for internal communication and Strava. For Strava https must be used. Host or local ip (example: http://192.168.1.10:8080 or https://endurain.com) |
| REVERSE_GEO_PROVIDER | nominatim | Yes | Defines reverse geo provider. Expects <a href="https://geocode.maps.co/">geocode</a>, photon or nominatim. photon can be the <a href="https://photon.komoot.io">SaaS by komoot</a> or a self hosted version like a <a href="https://github.com/rtuszik/photon-docker">self hosted version</a>. Like photon, Nominatim can be the <a href="https://nominatim.openstreetmap.org/">SaaS</a> or a self hosted version |
| PHOTON_API_HOST | photon.komoot.io | Yes | API host for photon. By default it uses the <a href="https://photon.komoot.io">SaaS by komoot</a> |
| PHOTON_API_USE_HTTPS | true | Yes | Protocol used by photon. By default uses HTTPS to be inline with what <a href="https://photon.komoot.io">SaaS by komoot</a> expects |
| NOMINATIM_API_HOST | nominatim.openstreetmap.org | Yes | API host for Nominatim. By default it uses the <a href="https://nominatim.openstreetmap.org">SaaS</a> |
| NOMINATIM_API_USE_HTTPS | true | Yes | Protocol used by Nominatim. By default uses HTTPS to be inline with what <a href="https://nominatim.openstreetmap.org">SaaS</a> expects |
| GEOCODES_MAPS_API | changeme | Yes | <a href="https://geocode.maps.co/">Geocode maps</a> offers a free plan consisting of 1 Request/Second. Registration necessary. |
| REVERSE_GEO_RATE_LIMIT | 1 | Yes | Change this if you have a paid Geocode maps tier. Other providers also use this variable. Keep it as is if you use photon or Nominatim to keep 1 request per second | 
| DB_HOST | postgres | Yes | postgres |
| DB_PORT | 5432 | Yes | 3306 or 5432 |
| DB_USER | endurain | Yes | N/A |
| DB_PASSWORD | No default set | `No` | Database password. Alternatively, use `DB_PASSWORD_FILE` for Docker secrets |
| DB_DATABASE | endurain | Yes | N/A |
| SECRET_KEY | No default set | `No` | Run `openssl rand -hex 32` on a terminal to get a secret. Alternatively, use `SECRET_KEY_FILE` for Docker secrets |
| FERNET_KEY | No default set | `No` | Run `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` on a terminal to get a secret or go to [https://fernetkeygen.com](https://fernetkeygen.com). Example output is `7NfMMRSCWcoNDSjqBX8WoYH9nTFk1VdQOdZY13po53Y=`. Alternatively, use `FERNET_KEY_FILE` for Docker secrets |
| ALGORITHM | HS256 | Yes | Currently only HS256 is supported |
| ACCESS_TOKEN_EXPIRE_MINUTES | 15 | Yes | Time in minutes |
| REFRESH_TOKEN_EXPIRE_DAYS | 7 | Yes | Time in days |
| SESSION_IDLE_TIMEOUT_ENABLED | false | Yes | Enforce idle timeouts (supported values are `true` and `false`) |
| SESSION_IDLE_TIMEOUT_HOURS | 1 | Yes | Time in hours |
| SESSION_ABSOLUTE_TIMEOUT_HOURS | 24 | Yes | Time in hours |
| JAEGER_ENABLED | false | Yes | N/A |
| JAEGER_PROTOCOL | http | Yes | N/A |
| JAEGER_HOST | jaeger | Yes | N/A |
| JAEGER_PORT | 4317 | Yes | N/A |
| BEHIND_PROXY | false | Yes | Change to true if behind reverse proxy |
| ENVIRONMENT | production | Yes | "production" and "development" allowed. "development" allows connections from localhost:8080 and localhost:5173 at the CORS level |
| SMTP_HOST | No default set | Yes | The SMTP host of your email provider. Example `smtp.protonmail.ch` |
| SMTP_PORT | 587 | Yes | The SMTP port of your email provider. Default is 587 |
| SMTP_USERNAME | No default set | Yes | The username of your SMTP email provider, probably your email address |
| SMTP_PASSWORD | No default set | Yes | The password of your SMTP email provider. Some providers allow the use of your account password, others require the creation of an app password. Please refer to your provider documentation. Alternatively, use `SMTP_PASSWORD_FILE` for Docker secrets |
| SMTP_SECURE | true | Yes | By default it uses secure communications. Accepted values are `true` and `false` |
| SMTP_SECURE_TYPE | starttls | Yes | If SMTP_SECURE is set you can set the communication type. Accepted values are `starttls` and `ssl` |

Table below shows the obligatory environment variables for postgres container. You should set them based on what was also set for the Endurain container.

| Environemnt variable  | Default value | Optional | Notes |
| --- | --- | --- | --- |
| POSTGRES_PASSWORD | changeme | `No` | N/A |
| POSTGRES_DB | endurain | `No` | N/A |
| POSTGRES_USER | endurain | `No` | N/A |
| PGDATA | /var/lib/postgresql/data/pgdata | `No` | N/A |

To check Python backend dependencies used, use poetry file (pyproject.toml).

Frontend dependencies:

- To check npm dependencies used, use npm file (package.json)
- Logo created on Canva

## Session Timeout Configuration (Optional)

By default, Endurain sessions last 7 days without enforcing idle timeouts.
For enhanced security, you can enable automatic session expiration:

**Environment Variables:**

- `SESSION_IDLE_TIMEOUT_ENABLED`: Enable timeout enforcement (default: `false`)
- `SESSION_IDLE_TIMEOUT_HOURS`: Logout after inactivity (default: `1`)
- `SESSION_ABSOLUTE_TIMEOUT_HOURS`: Force re-login after duration (default: `24`)

**Example:**

```yaml
environment:
  SESSION_IDLE_TIMEOUT_ENABLED: "true"
  SESSION_IDLE_TIMEOUT_HOURS: "2"
  SESSION_ABSOLUTE_TIMEOUT_HOURS: "48"
```

## Docker Secrets Support

Endurain supports [Docker secrets](https://docs.docker.com/compose/how-tos/use-secrets/) for securely managing sensitive environment variables. For the following environment variables, you can use `_FILE` variants that read the secret from a file instead of storing it directly in environment variables:

- `DB_PASSWORD` → `DB_PASSWORD_FILE`
- `SECRET_KEY` → `SECRET_KEY_FILE`
- `FERNET_KEY` → `FERNET_KEY_FILE`
- `SMTP_PASSWORD` → `SMTP_PASSWORD_FILE`

### Using File-Based Secrets

Use file-based secrets to securely manage sensitive environment variables:

1. **Create a secrets directory with proper permissions:**

```bash
mkdir -p secrets
chmod 700 secrets
```

2. **Create secret files with strong passwords:**

```bash
# Use randomly generated passwords, not hardcoded ones
echo "$(openssl rand -base64 32)" > secrets/db_password.txt
echo "$(openssl rand -hex 32)" > secrets/secret_key.txt
echo "$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")" > secrets/fernet_key.txt

# Set secure file permissions
chmod 600 secrets/*.txt
chown $(id -u):$(id -g) secrets/*.txt
```

3. **Configure docker-compose.yml:**

```yaml
services:
  endurain:
    environment:
      - DB_PASSWORD_FILE=/run/secrets/db_password
      - SECRET_KEY_FILE=/run/secrets/secret_key
      - FERNET_KEY_FILE=/run/secrets/fernet_key
    secrets:
      - db_password
      - secret_key
      - fernet_key

secrets:
  db_password:
    file: ./secrets/db_password.txt
  secret_key:
    file: ./secrets/secret_key.txt
  fernet_key:
    file: ./secrets/fernet_key.txt
```

**Note**: When using `_FILE` variants, the original environment variables (e.g., `DB_PASSWORD`) are not needed. The application will automatically read from the file specified by the `_FILE` environment variable.

## Volumes

Docker image uses a non-root user, so ensure target folders are not owned by root. Non-root user should use UID and GID 1000. It is recommended to configure the following volumes for data persistence:

| Volume | Notes |
| --- | --- |
| `<local_path>/endurain/backend/logs:/app/backend/logs` | Log files for the backend |
| `<local_path>/endurain/backend/data:/app/backend/data` | Necessary for image and activity files persistence on docker image update |

## Bulk import and file upload

To perform a bulk import:
- Place .fit, .tcx, .gz and/or .gpx files into the data/activity_files/bulk_import folder. Create the folder if needed.
- In the "Settings" menu select "Import".
- Click "Import" next to "Bulk Import".

.fit files are preferred. I noticed that Strava/Garmin Connect process of converting .fit to .gpx introduces additional data to the activity file leading to minor variances in the data, like for example additional 
meters in distance and elevation gain. Some notes:

- After the files are processed, the files are moved to the processed folder
- GEOCODES API has a limit of 1 Request/Second on the free plan, so if you have a large number of files, it might not be possible to import all in the same action
- The bulk import currently only imports data present in the .fit, .tcx or .gpx files - no metadata or other media are imported.

## Importing information from a Strava bulk export (BETA)

Strava allows users to create a bulk export of their historical activity on the site. This information is stored in a zip file, primarily as .csv files, GPS recording files (e.g., .gpx, .fit), and media files (e.g., .jpg, .png).

### Importing gear from a Strava bulk export

#### Bike import
At the present time, importing bikes from a Strava bulk export is implemented as a beta feature - use with caution.  Components of bikes are not imported - just the bikes themselves.  There is no mechanism present to undo an import.

To perform an import of bikes: 
- Place the bikes.csv file from a Strava bulk export into the data/activity_files/bulk_import folder. Create the folder if needed;
- In the `Settings` menu select `Import`;
- Click `Import Strava Bikes` next to `Strava gear import`;
- Upon successful import, the bikes.csv file is moved to /data/activity_files/processed folder;
- Status messages about the import, including why any gear was not imported, can be found in the logs.

Ensure the file is named `bikes.csv` and has a header row with at least the fields 'Bike Name', 'Bike Brand', and 'Bike Model'.

#### Shoe import

At the present time, importing shoes from a Strava bulk export is implemented as a beta feature - use with caution.  Components of shooes are not imported - just the shoes themselves. 

To perform an import of shoes: 
- Place the shoes.csv file from a Strava bulk export into the data/activity_files/bulk_import folder. Create the folder if needed;
- In the `Settings` menu select `Import`;
- Click `Shoes import` next to `Strava gear import`;
- Upon successful import, the shoes.csv file is moved to /data/activity_files/processed folder;
- Status messages about the import, including why any gear was not imported, can be found in the logs.

Ensure the file is named `shoes.csv` and has a header row with at least the fields 'Shoe Name', 'Shoe Brand', and 'Shoe Model'.

Note that Strava allows blank shoe names, but Endurain does not.  Shoes with a blank name will thus be given a default name of `Unnamed Shoe #` on import.

#### Notes on importing gear

NOTE: There is currently no mechanism to undo a gear import.

All gear will be imported as active, as Strava does not export the active/inactive status of the gear.

Note that Endurain does not allow the `+` character in gear field names, and thus +'s will removed from all fields and replaced with spaces (" ") on import.  All beginning and ending space characters (" ") will be removed on import as well.

Endurain does not allow duplicate gear nicknames, case insensitively (e.g., `Ilves` and `ilves` would not be allowed) and regardless of gear type (e.g., `Ilves` the bike and `ilves` the shoe would not be allowed). Gear with duplicate nicknames will not be imported (i.e., only the first item with a given nickname will be imported).

The import routine checks for duplicate items, and should not import duplicates. Thus it should be safe to re-import the same file mulitple times. However, due to the renaming of un-named shoes, repeated imports of the same shoe file will create duplicate entries of any unnamed shoes present. 

Gear that is already present in Endurain due to having an active link with Strava will not be imported via the manual import process.

### Importing other items from a Strava bulk import

Importing activity metadata and media is under development in October 2025.

## Image personalization

It is possible (v0.10.0 or higher) to personalize the login image in the login page. To do that, map the data/server_images directory for image persistence on container updates and:
 - Set the image in the server settings zone of the settings page
 - A square image is expected. Default one uses 1000px vs 1000px
