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
            - SECRET_KEY=changeme # openssl rand -hex 32
            - FERNET_KEY=changeme # https://fernetkeygen.com or python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
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
        image: postgres:latest
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
            - <path_to_container_folders>/postgres:/var/lib/postgresql/data
        restart: unless-stopped

    adminer:
        container_name: adminer
        image: adminer
        ports:
            - 8081:8080
        restart: unless-stopped
```

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

- Backend uses [Poetry](https://python-poetry.org/) for dependency management. You may need to install Python and Poetry if dependency management is necessary.

## Frontend
Make sure you have an up-to-date version of [Node.js](https://nodejs.org/) installed.

- Go to the root of the project and move to frontend/app folder and install the dependencies:

```bash
cd frontend/app
npm install
```

- Create a file called `.env.local` inside frontend/app and add the following to it:

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