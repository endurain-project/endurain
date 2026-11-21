# Setup a dev environment

Below are the steps to create a dev environment. Examples below will use Endurain repo, but you should adapt those for your scenario (forked repo, etc).

- Clone the repo to your dev machine:

```bash
cd <folder_to_store_code>
git clone https://github.com/endurain-project/endurain.git # this will clone the repo structure to the previous folder inside a folder called endurain
```

## Docker image and backend logic
Make sure Docker is installed, more info [here](https://docs.docker.com/get-started/introduction/get-docker-desktop/).

- On the project root folder, create a new Docker image, the example below uses `unified-image` as the image name:

```bash
docker build -f docker/Dockerfile -t unified-image .
```

- Go to the project root folder and create a file called `docker-compose.yml` and adapt it to your needs. Example below:

```conf
services:
    endurain:
        container_name: endurain
        image: unified-image # based on image that will be created above
        environment:
            - TZ=Europe/Lisbon # change if needed. Default is UTC
            - DB_HOST=postgres
            - DB_PORT=5432
            - DB_PASSWORD=changeme
            - SECRET_KEY=replace-with-at-least-32-random-characters # openssl rand -hex 32 or use the Tools page Secret Generators
            - FERNET_KEY=changeme # openssl rand -base64 32 or use the Tools page Secret Generators
            - ENDURAIN_HOST=http://localhost:8080 # change if needed
            - BEHIND_PROXY=false
            - ENVIRONMENT=development
            - LOG_LEVEL=debug # change log level if needed. Supported levels: critical, error, warning, info, debug, trace
        volumes:
            - <folder_to_store_code>/backend/app:/app/backend # this will replace the backend code logic with yours. Any changes in the code need a container reboot for them to apply
        ports:
            - "8080:8080" # change if needed
        depends_on:
            postgres:
                condition: service_healthy
        restart: unless-stopped

    postgres:
        image: postgres:18
        container_name: postgres
        environment:
            - POSTGRES_PASSWORD=changeme
            - POSTGRES_DB=endurain
            - POSTGRES_USER=endurain
            - PGDATA=/var/lib/postgresql/data/pgdata
        ports:
            - "5432:5432"
        healthcheck:
            test: ["CMD-SHELL", "pg_isready -U endurain"]
            interval: 5s
            timeout: 5s
            retries: 5
        volumes:
            - ${LOCAL_PATH:-/var/opt/endurain}/postgres:/var/lib/postgresql/data
        restart: unless-stopped

    adminer:
        container_name: adminer
        image: adminer:5.3.0
        ports:
            - 8081:8080
        restart: unless-stopped
```

> While this example uses specific versions for simplicity, always pin Docker images to exact tags and digests (`tag@sha256:...`) in production to guarantee immutable, verifiable builds. The project's compose files use this pattern.

> Need values for `SECRET_KEY` and `FERNET_KEY`? Generate and copy them from the [Tools](../tools.md#secret-generators) page.

- In the same folder, create a `.env` file that sets the data storage location:

```conf
LOCAL_PATH=./endurain_data
```

This keeps postgres data inside your project folder. The `endurain_data/` directory is already gitignored.

- Start your project based on the docker compose file created before:

```bash
docker compose up -d
```

- To stop the project:

```bash
docker compose down
```

- To remove the create `unified-image` Docker image:

```bash
docker image remove unified-image
```

## Backend tooling

The backend (Python 3.15) uses [uv](https://docs.astral.sh/uv/) for dependencies and [hatch](https://hatch.pypa.io/) for scripts. Install Python 3.15 and uv on your machine, then work from the `backend/` folder:

```bash
cd backend
uv sync                                       # install dependencies
PYTHONPATH=app uv run lint-imports            # check module boundaries
uv run pytest tests/<area> -q                 # run tests for one area
uv run ruff format --check . && uv run ruff check .   # format and lint
```

The tests run against PostgreSQL. With Docker running, `uv run pytest` starts a throwaway `postgres:18` container for the run and removes it afterwards. To reuse a database you keep running, set `TEST_DATABASE_URL` to a disposable database whose name contains `test`; the run creates and drops its own databases beside it:

```bash
docker run -d --rm --name endurain-test-pg -e POSTGRES_USER=endurain -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=endurain_test -p 55432:5432 postgres:18 -c fsync=off -c synchronous_commit=off -c full_page_writes=off
export TEST_DATABASE_URL=postgresql+psycopg://endurain:test@localhost:55432/endurain_test
uv run hatch run test                         # the whole suite in parallel, with the coverage gate CI applies
```

Hatch scripts group the common checks, for example `uv run hatch run check` runs lint, format, tests and type checks without changing files. Backend code changes in the mounted `backend/app` folder apply after a container restart.

## Load tests

`loadtest/` holds a load-test stack: a distributed Endurain (nginx in front of several API replicas, dedicated workers, PostgreSQL with `pg_stat_statements` behind toxiproxy, Redis, an S3-compatible store, adobe/s3mock as in the distributed CI job, and a stub for the providers the application calls) built from `docker/Dockerfile` with `PYTHON_EXTRAS=distributed`, a seeding script and a [Locust](https://locust.io/) scenario file. It needs Docker (about 4 GB of memory for the VM) and uv, and it has its own `pyproject.toml`, so the backend's dependencies are untouched. The stack runs as the Compose project `endurain-load` and publishes only `localhost:18080` (the proxy), `127.0.0.1:15432` (PostgreSQL), `127.0.0.1:18474` (toxiproxy's API) and `127.0.0.1:18081` (the stub's admin API). `run.sh` generates the stack's `SECRET_KEY`, `FERNET_KEY` and database password into `loadtest/.env.secrets` on first use (gitignored); `loadtest/.env.loadtest` holds the rest of its settings.

```bash
cd loadtest
./run.sh smoke       # 1 API, 1 worker, 2 minutes, small seed: a few minutes in all
./run.sh standard    # 2 APIs, 2 workers, 10 minutes, 50 users x 200 activities
./run.sh soak        # 2 APIs, 2 workers, 2 hours; watch memory, connections and queue depth
./run.sh scale       # the same load with 1, 2 and 4 API replicas; records throughput per step
./run.sh faults      # 2 APIs, 2 workers: each fault scenario under a steady load, about 20 minutes
./run.sh compare <run>   # p95 per group against loadtest/baseline.json
```

A profile brings the stack up, seeds it (`seed.py` runs inside the image and uses the application's own users, activities, health, gears and followers code; it is idempotent per seed name), runs Locust headless, runs `invariants.py` against the database, dumps the top `pg_stat_statements` and the connection counts, and tears the stack down. `LOADTEST_KEEP=1` leaves it up, and `LOADTEST_USERS` and `LOADTEST_RUNTIME` override a profile's virtual users and run time.

Results go to `loadtest/results/<profile>-<timestamp>/` (git-ignored): `summary.json` (p50, p95 and p99, rate and failures per endpoint and per group), Locust's CSV files, `invariants.json`, `connections.csv`, `pg_stat_statements.txt`, `pg_stat_activity.txt`, the container logs and, for `scale`, `scale.json` next to the per-step folders.

A run fails (non-zero exit) when:

- a group's p95 or error rate in `thresholds.json` is exceeded. Requests are named `<group> <METHOD> <path>`, a group with fewer than `min_requests` requests is skipped, and a `429` is the rate limiter working, so it is counted as `throttled` and is neither a success nor a failure;
- an invariant of `invariants.py` is violated: a duplicate activity per user and dedup key, more than one record for an `Idempotency-Key` (the same key fired at once from several sessions of one account), more open uploads than the cap of 10, a durable job stuck past its lease or run twice, an undrained outbox, an orphan row, or a count that does not match what the run created. A dead-lettered job, a failed Strava refresh, an upload job that never ended and a Strava 429 that did not defer a refresh also fail it.

### Stub providers

The `stub` service (`loadtest/stub/stub.py`, run in the application image) answers over https, with a certificate it makes at start, for `tile.openstreetmap.org` (a PNG for every tile), `nominatim.openstreetmap.org` (a reverse-geocoding answer) and `www.strava.com` (token refresh, athlete, activities list, activity, streams, laps and gear, with stable ids so a repeated sync meets the same activities). The stack gives it a fixed address on a fixed subnet and points those names at it with `extra_hosts`; `SSRF_ALLOWED_HOSTS` allows that subnet, and `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` name a bundle of the system CAs plus the stub's CA. Thumbnails and geocoding therefore succeed, and **any dead-lettered job is an invariant violation**, except in a fault scenario that causes one on purpose.

Strava answers 429 with Strava's rate-limit headers when a limit is set through the admin API (`POST 127.0.0.1:18081/strava/limit` with `{"limit": 40, "window": 900}` for a fixed window per Strava application, or `{"reject_for": 30}` for a burst). `seed.py --strava-users N` links the first N users, each as its own Strava application. The load test's `StravaUser` sessions (two per account, so syncs of one account overlap) call `POST /activities/refresh` and follow the job, and one burst of 429 is asked for 40 seconds into a run (`LOADTEST_STRAVA_BURST=<after>:<seconds>`, empty to turn it off). The invariants then require that no refresh job failed, that every deferred refresh carries `retry_after`, that a refresh used no retry attempt, that the 429 answers deferred refreshes, and that no activity is duplicated per Strava id.

### Fault scenarios

`./run.sh faults` brings the stack up and runs `faults.py`, which runs each scenario under a steady Locust load (16 users: browsing, uploads and Strava syncs), puts everything back, then runs `invariants.py` for it. A scenario fails on a violated invariant, on a failed assertion about the fault, or when the stack is not back within its recovery bound:

| Scenario | Fault | Asserted | Bound |
| --- | --- | --- | --- |
| `worker_kill` | SIGKILL the worker while it holds jobs of an upload burst, then start a new one | every job ends once: the lease (45 s here) expires and the reaper requeues it | 240 s |
| `api_restart` | restart one API replica during load and an upload burst | the replica and the proxy serve again; requests in flight may fail, but no accepted job is lost or duplicated | 120 s |
| `redis_outage` | stop Redis for 20 s | as documented in [Monitoring](../getting-started/monitoring.md): `/health` answers 200 with `degraded`, reads keep working, WebSocket tickets answer 503; afterwards `/health` is `ok` and tickets and sign-in work | 60 s |
| `postgres_faults` | toxiproxy: 200 ms latency for 30 s, then every connection reset for 10 s | the application answers again, no connection is stuck idle in a transaction, every job ends | 90 s |
| `strava_429` | the stub answers 429 to every Strava call for 45 s | refreshes are deferred (with `retry_after`), not failed | n/a |

Results go to `results/<run>/faults.json` (the outcome and notes of each scenario) and `results/<run>/<scenario>/` (Locust files, `ledger.json`, `invariants.json`). The scenarios that break connections or the shared state (`api_restart`, `redis_outage`, `postgres_faults`) run the invariants in fault mode: dead-lettered jobs and an upload job whose response the fault cut off are reported, not failed.

### Weekly workflow and baseline

`.github/workflows/load-test.yml` runs weekly (Sunday 03:17 UTC) and on demand (`workflow_dispatch`, input `profile`, default `standard`): it builds the stack, runs the profile, then `./run.sh faults`, compares the profile's `summary.json` with `loadtest/baseline.json` and uploads `loadtest/results/` as an artifact. It fails on a threshold, an invariant, a failed fault scenario or a regression. A group regresses when its p95 is more than **1.5 times** the baseline's and also more than 50 ms above it (2 s for the groups made of polling: `*_e2e`, `*_hint`): 1.5 is above the run-to-run spread seen on one machine and still catches a real slowdown, and the floor stops a 6 ms to 11 ms wobble on a shared runner from failing a run. The comparison is printed to the job summary. Only the `standard` profile has a baseline.

`baseline.json` was made from a `standard` run on a developer machine, which is not the CI runner. **Regenerate it from the first scheduled run**: `uv run python compare.py <run> --write-baseline` on that run's results (download the artifact), and commit it. Do the same after a change that is meant to move the numbers.

Locust runs as one process (its ledger of what the run created is in memory).

Run `uv run python invariants.py --run <run>` again to re-check a kept stack, and `docker compose -p endurain-load --env-file .env.loadtest --env-file .env.secrets -f compose.yaml run --rm seed --users 50 --activities-per-user 200 --days 730` to seed by hand.

## Frontend
Make sure you have Node.js 26+ installed ([nodejs.org](https://nodejs.org/)).

- Go to the root of the project and move to frontend folder and install the dependencies:

```bash
cd frontend
npm install
```

- The frontend reads the backend address from `frontend/public/env.js`, which sets `ENDURAIN_HOST` to `http://localhost:8080`. Edit that value if your docker compose publishes the backend on another address.

- After the dependencies are installed run the frontend:

```bash
npm run dev
```

- After the frontend starts running, it should be available in the port `5173`. You should now be able to access the dev environment at `http://localhost:5173`. Screenshot below shows the output from the `npm run dev`. Adapt the port based on the command output.

![Frontend running](../assets/developer-guide/npm_run_dev.png)

- Some processes, like token refresh may redirect your dev env from port `5173` to `8080` (or other, depending on your compose file). If this happens simply navigate again to `5173`.

## Code navigation with CodeGraph

This project uses [CodeGraph](https://github.com/colbymchenry/codegraph) to index the codebase (symbols, call paths and dependencies) so that code can be explored and understood faster, either by you or by AI coding assistants such as Claude Code. Using it is optional.

- Install CodeGraph following its documentation.
- From the repository root, initialize and index the project:

```bash
codegraph init
```

- The index is stored in the `.codegraph/` directory at the repository root. It is a local artifact and should not be committed.
- Once indexed, you can query the codebase from the terminal, for example:

```bash
codegraph explore "how does token refresh work"
```
