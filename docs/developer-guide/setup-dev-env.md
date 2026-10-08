# Setup a dev environment

Bellow are the steps to create a dev environment. Examples bellow will use Endurain repo, but you should adapt those for your scenario (forked repo, etc).

- Clone the repo to your dev machine:

```bash
cd <folder_to_store_code>
git clone https://github.com/endurain-project/endurain.git # this will clone the repo structure to the previous folder inside a folder called endurain
```

## Docker image and backend logic
Make sure Docker is installed, more info [here](https://docs.docker.com/get-started/introduction/get-docker-desktop/).

- On the project root folder, create a new Docker image, the example bellow uses `unified-image` as the image name:

```bash
docker build -f docker/Dockerfile -t unified-image .
```

- Go to the project root folder and create a file called `docker-compose.yml` and adapt it to your needs. Example bellow:

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
            - SECRET_KEY=changeme # openssl rand -hex 32 or use the Tools page Secret Generators
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

- Backend uses **uv** (Python package/project manager) and **hatch** (test runner / script orchestrator, installed as a dev dependency via `uv sync`). You may need to install Python and uv globally if dependency management is necessary.

## Frontend
Make sure you have an up-to-date version of [Node.js](https://nodejs.org/) installed.

- Go to the root of the project and move to frontend folder and install the dependencies:

```bash
cd frontend
npm install
```

- Create a file called `.env.local` inside frontend and add the following to it:

```conf
VITE_ENDURAIN_HOST=http://localhost:8080 # Adapt this based on the docker compose of your dev environment
```

- After the dependencies are installed run the frontend:

```bash
npm run dev
```

- After the frontend starts running, it should be available in the port `5173`. You should now be able to access the dev environment at `http://localhost:5173`. Screenshot bellow shows the output from the `npm run dev`. Adapt the port based on the command output.

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
