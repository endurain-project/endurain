## Default Credentials

- **Username:** admin  
- **Password:** admin

## Docker Deployment

Endurain provides a Docker image for simplified deployment. To get started, check out the `docker-compose.yml.example` file in the project repository and adjust it according to your setup. Supported tags are:

- **latest:** contains the latest released version;
- **major.minor version, example "v0.18":** latest patch release within the v0.18.x train;
- **version, example "v0.3.0":** contains the app state available at the time of the version specified;
- **development version, example "dev_06092024":** contains a development version of the app at the date specified. This is not a stable released and may contain issues and bugs. Please do not open issues if using a version like this unless asked by me.

## Supported Environment Variables
Table below shows supported environment variables. Variables marked with optional "No" should be set to avoid errors.

| Environment variable  | Default value | Optional | Notes |
| --- | --- | --- | --- |
| LOCAL_PATH | /var/opt/endurain | Yes | Root directory for Docker volume mounts. Controls where activity files, images, logs, and database data are stored on the host. |
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
| DB_SSLMODE | *(empty)* | Yes | Optional TLS mode for the PostgreSQL connection. Leave empty to disable (default — keeps local Postgres without SSL working). Accepted values match libpq: `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`. Recommended for any deployed environment: `require`. Most secure (validates CA + hostname): `verify-full` |
| SECRET_KEY | No default set | `No` | Run `openssl rand -hex 32` on a terminal or use the [Secret Generators](../tools.md#secret-generators) tool. Example output is `69b85208190c96821050d4ba980a8a95d928ab7e0ebf1a40b8ef6d09fd8367d3`. Alternatively, use `SECRET_KEY_FILE` for Docker secrets |
| FERNET_KEY | No default set | `No` | Run `openssl rand -base64 32` on a terminal or use the base64 tool in the [Secret Generators](../tools.md#secret-generators). Example output is `7NfMMRSCWcoNDSjqBX8WoYH9nTFk1VdQOdZY13po53Y=`. Alternatively, use `FERNET_KEY_FILE` for Docker secrets |
| ALGORITHM | HS256 | Yes | Currently only HS256 is supported |
| ACCESS_TOKEN_EXPIRE_MINUTES | 15 | Yes | Time in minutes |
| REFRESH_TOKEN_EXPIRE_DAYS | 7 | Yes | Time in days |
| SESSION_IDLE_TIMEOUT_ENABLED | false | Yes | Enforce idle timeouts (supported values are `true` and `false`) |
| SESSION_IDLE_TIMEOUT_HOURS | 1 | Yes | Time in hours |
| SESSION_ABSOLUTE_TIMEOUT_HOURS | 24 | Yes | Time in hours |
| BEHIND_PROXY | false | Yes | Change to true if behind reverse proxy |
| ENVIRONMENT | production | Yes | `production`, `demo` and `development` allowed. `development` allows connections from localhost:8080 and localhost:5173 at the CORS level. `demo` equals to `production` except it does not return user sessions. **`production` and `demo` set the `Secure` flag on all authentication cookies (refresh token and OAuth/SSO session), so Endurain must be served over HTTPS (directly or via a reverse proxy terminating TLS) for login, session refresh, and SSO to work** |
| SMTP_HOST | No default set | Yes | The SMTP host of your email provider. Example `smtp.protonmail.ch` |
| SMTP_PORT | 587 | Yes | The SMTP port of your email provider. Default is 587 |
| SMTP_USERNAME | No default set | Yes | The username of your SMTP email provider, probably your email address |
| SMTP_PASSWORD | No default set | Yes | The password of your SMTP email provider. Some providers allow the use of your account password, others require the creation of an app password. Please refer to your provider documentation. Alternatively, use `SMTP_PASSWORD_FILE` for Docker secrets |
| SMTP_FROM | No default set | Yes | Sets the "From" address on outgoing emails. If unset, it is auto-detected (usually `SMTP_USERNAME`). Set this when your provider requires a verified sender that differs from the login username (e.g. Brevo) |
| SMTP_SECURE | true | Yes | By default it uses secure communications. Accepted values are `true` and `false` |
| SMTP_SECURE_TYPE | starttls | Yes | If SMTP_SECURE is set you can set the communication type. Accepted values are `starttls` and `ssl` |
| LOG_LEVEL | info | Yes | Supported levels: critical, error, warning, info, debug, trace |
| ALLOWED_REDIRECT_SCHEMES | `endurain` | Yes | Comma-separated list of custom URI schemes allowed as SSO redirect targets for mobile apps using the system browser (e.g., `endurain,gadgetbridge`). Defaults to `endurain` when unset. If set, only the configured schemes are allowed (no implicit merge with `endurain`). Only relative paths (e.g., `/dashboard`) are accepted when no custom scheme is used. External `http`/`https` URLs are always rejected regardless of this setting. See [Mobile SSO with PKCE](../developer-guide/authentication.md#mobile-sso-with-pkce) |
| TRUSTED_PROXIES | "*" | Yes | Comma-separated list of trusted proxy IPs, CIDR ranges, or hostnames for correct client IP detection when `BEHIND_PROXY` is `true`. Defaults to `["*"]` (all proxies trusted) in development and `[]` in production and demo. **Hostname support:** You can use hostnames (e.g., `proxy.internal` or Docker container names like `caddy`) which are resolved to IPs at application startup and refreshed periodically in memory. This is useful in Docker deployments where container IPs may change on restart. If a hostname cannot be resolved, a warning is logged and the entry is skipped (graceful degradation). |
| SSRF_ALLOWED_HOSTS | No default set | Yes | Comma-separated allowlist of exact hostnames (case-insensitive) and/or explicit IP CIDR ranges that may resolve to private/internal addresses for admin-configured outbound calls (currently OIDC discovery and JWKS fetch only). Enables self-hosted identity providers (Authentik, Pocket ID, Keycloak, ...) reachable only over a private network. Example: `auth.internal.example.com,10.10.0.0/24,fd00::/64`. Wildcards (`*`) are rejected; CIDRs must be at least `/8` for IPv4 and `/32` for IPv6. Every allowlisted outbound call is audit-logged at INFO. Does not affect other outbound calls (geocoding, etc.) |
| CSP_ADDITIONAL_CONNECT_SRC | No default set | Yes | Comma-separated list of extra origins appended to the `Content-Security-Policy` `connect-src` directive. Set this when Endurain is behind a forward-auth reverse proxy (e.g. Pangolin) that redirects API calls to its own domain for session validation; without its origin here the browser blocks the redirect with a CSP error and the app fails to load. Example: `https://auth.example.com`. Use specific origins: overly broad values that would defeat `connect-src` are rejected at startup — the bare wildcard `*` and scheme-only sources like `https:` (host wildcards such as `https://*.example.com` are fine). Entries containing whitespace or `;` are also rejected (to prevent header injection). Default: empty (`connect-src` stays `'self'` plus the jsDelivr CDN). |
| RATE_LIMIT_ENABLED | true | Yes | Enable or disable API rate limiting. Set to `false` to disable for development or testing. Accepted values are `true` and `false` |
| DEPLOYMENT_PROFILE | local | No | Deployment shape selecting the backend for all shared state. `local` (default) uses in-process memory; `distributed` requires Redis. A `distributed` or multi-worker deployment wired to memory is rejected at startup. |
| WEB_WORKERS | 1 | No | Number of web-server worker processes. When `> 1`, shared state (Redis) is required even under the `local` profile. |
| STATE_URI | No default set | No | Explicit override for the shared ephemeral-state backend (rate-limit counters, login/step-up lockout, pending-MFA, MFA setup secrets, Garmin MFA codes, websocket tickets). Takes precedence over `REDIS_URL`. `memory://` or `redis://…`. |
| REDIS_URL | No default set | No | Shared Redis DSN for every Redis capability with no explicit URI. Required for `distributed` or `WEB_WORKERS > 1`. |
| EVENT_LOG_RETENTION_DAYS | 90 | Yes | Age in days after which event-log observability rows are pruned by a scheduled cleanup (runs daily and once at startup). The `event_log` table records every background event's lifecycle for the admin dashboard; it is best-effort and safe to lose, so every row older than this is removed. Set to `0` (or negative) to disable pruning and keep rows forever. |
| JOBS_RETENTION_DAYS | 90 | Yes | Age in days after which completed durable-job bookkeeping is pruned by the same scheduled cleanup: relayed outbox rows and completed background-job rows. In-flight work (pending/running jobs, unrelayed outbox rows) and dead-lettered jobs (kept for review) are never pruned. Only relevant when the durable job queue is enabled. Set to `0` (or negative) to disable pruning. |
| ALLOW_API_KEY_QUERY_PARAM | false | Yes | Allow API keys to be passed as a `?api_key=` query parameter. Disabled by default because query-string credentials appear in server access logs, reverse-proxy logs, and browser history. Enable only for integrations that cannot set custom request headers (e.g. some webhook senders). The `X-API-Key` header is always preferred. When enabled, every request that uses the query parameter emits a warning in the application log. |

### TRUSTED_PROXIES Examples

When running Endurain behind a reverse proxy (e.g., Caddy, Nginx) with `BEHIND_PROXY=true`, configure `TRUSTED_PROXIES` to ensure correct client IP detection:

**Docker Compose with Hostname (Recommended for Docker):**
```yaml
services:
  endurain:
    environment:
      BEHIND_PROXY: "true"
      TRUSTED_PROXIES: "caddy"  # Use the service name of your reverse proxy
```
The hostname `caddy` will be resolved to its IP address at startup and refreshed periodically. This is useful because Docker container IPs can change on restart.

**With Static IPs:**
```yaml
environment:
  BEHIND_PROXY: "true"
  TRUSTED_PROXIES: "10.0.0.5"
```

**With CIDR Ranges:**
```yaml
environment:
  BEHIND_PROXY: "true"
  TRUSTED_PROXIES: "192.168.0.0/16"
```

**Mixed Format:**
```yaml
environment:
  BEHIND_PROXY: "true"
  TRUSTED_PROXIES: "caddy,192.168.1.0/24,reverse-proxy.local"
```

**Debug Output:**
When the application starts, it logs resolved hostnames at startup:
```
INFO: Resolved TRUSTED_PROXIES hostname 'caddy' to ['10.0.0.5']
INFO: Allowed trusted proxies: ['caddy', '192.168.1.0/24']
INFO: Resolved trusted proxy IPs: ['10.0.0.5']
```

If a hostname cannot be resolved, a warning is logged but the application continues:
```
WARNING: Failed to resolve TRUSTED_PROXIES hostname 'nonexistent': [Errno -3] Temporary failure in name resolution
```

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

Docker image runs as a non-root user (`app`). For named Docker volumes, permissions are handled automatically. For host bind mounts, ensure target directories on the host are writable by the container's UID (default 1000). Use `user:` in docker-compose to run as a custom UID/GID, and ensure host bind mounts are writable by that user. It is recommended to configure the following volumes for data persistence:

| Volume | Notes |
| --- | --- |
| `${LOCAL_PATH:-/var/opt/endurain}/backend/logs:/app/backend/logs` | Log files for the backend |
| `${LOCAL_PATH:-/var/opt/endurain}/backend/data:/app/backend/data` | Necessary for image and activity files persistence on docker image update |

## Image personalization

It is possible (v0.10.0 or higher) to personalize the login image in the login page. To do that, map the data/server_images directory for image persistence on container updates and:

 - Set the image in the server settings zone of the settings page
 - A square image is expected. Default one uses 1000px vs 1000px

