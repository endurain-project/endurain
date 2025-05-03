# Developer guide

---

## Setup a dev environment

Bellow are the steps to create a dev environment. Examples bellow will use Endurain repo, but you should adapt those for your scenario (forked repo, etc).

 - Clone the repo to your dev machine:

```
$ cd <folder_to_store_code>
$ git clone https://github.com/joaovitoriasilva/endurain.git # this will clone the repo structure to the previous folder inside a folder called endurain
```

### Docker image and backend logic
Make sure Docker is installed, more info [here](https://docs.docker.com/get-started/introduction/get-docker-desktop/).

 - On the project root folder, create a new Docker image, the example bellow uses `unified-image` as the image name:

```
$ docker build -f docker/Dockerfile -t unified-image .
```

 - Go to the project root folder and create a file called `docker-compose.yml` and adapt it to your needs. Example bellow:

```
services:
    endurain:
        container_name: endurain
        image: unified-image # based on image that will be created above
        environment:
            - TZ=Europe/Lisbon # change if needed. Default is UTC
            - DB_TYPE=postgres
            - DB_HOST=postgres
            - DB_PORT=5432
            - DB_PASSWORD=changeme
            - SECRET_KEY=changeme
            - GEOCODES_MAPS_API=changeme
            - ENDURAIN_HOST=http://localhost:8080 # change if needed
            - BEHIND_PROXY=false
            - ENVIRONMENT=development
        volumes:
            - <path_to_project_root_folder>/backend/app:/app/backend # this will replace the backend code logic with yours. Any changes in the code need a container reboot for them to apply
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

```
$ docker compose up -d
```

 - To stop the project:

```
$ docker compose down
```

 - To remove the create `unified-image` Docker image:

```
$ docker image remove unified-image
```

 - Backend uses [Poetry](https://python-poetry.org/) for dependency management. You may need to install Python and Poetry if dependency management is necessary.

### Frontend
Make sure you have an up-to-date version of [Node.js](https://nodejs.org/) installed.

 - Go to the root of the project and move to frontend/app folder and install the dependencies:

```
$ cd frontend/app
$ npm install
```

 - Create a file called `.env.local` inside frontend/app and add the following to it:

```
VITE_ENDURAIN_HOST=http://localhost:8080 # Adapt this based on the docker compose of your dev environment
```

 - After the dependencies are installed run the frontend:

```
$ npm run dev
```

 - After the frontend starts running, it should be available in the port `5173`. You should now be able to access the dev environment at `http://localhost:5173`. Screenshot bellow shows the output from the `npm run dev`. Adapt the port based on the command output.

![Frontend running](assets/developer-guide/npm_run_dev.png)

 - Some processes, like token refresh may redirect your dev env from port `5173` to `8080` (or other, depending on your compose file). If this happens simply navigate again to `5173`.

## API Integration (v0.3.0+)

Endurain supports integration with other apps:

### API Requirements
- **Add a header:** Every request must include an `X-Client-Type` header with either `web` or `mobile` as the value. Requests with other values will receive a `403` error.
- **Authorization:** Every request must include an `Authorization Bearer: <access token>` header with a valid (new or refreshed) access token.

### Token Handling
- The backend will generate an `access_token` valid for 15 minutes and an `refresh_token` valid for 7 days. This follow the logic of short and longed lived tokens for auth session.
- The `access_token` is used for authorization; The `refresh_token` is used to refresh the `access_token`.
- For **web apps**, the backend sends access/refresh tokens as HTTP-only cookies.
- For **mobile apps**, tokens are included in the response body.


### API Endpoints 
The API is reachable under `/api/v1`. Below are some example endpoints. All endpoints information can be checked on the backend docs (`http://localhost:98/docs` or `http://ip_address:98/docs` or `https://domain/docs`):

| What | Url | Expected Information |
| ---- | --- | -------------------- |
| **Authorize** | `/token` |  `FORM` with the fields `username` and `password`. This will be sent in clear text, use of HTTPS is highly recommended |
| **Refresh Token** | `/refresh` | header `Authorization Bearer: <Refresh Token>`  |
| **Activity Upload** | `/activities/create/upload` | .gpx or .fit file |
| **Set Weight** | `/health/weight` | JSON {'weight': <number>, 'created_at': `yyyy-MM-dd`} |


## Supported activity types
The table bellow details the activity types supported by Endurain:

| Name | Value |
| ---- | --- |
| Run | 1 |
| Trail run | 2 |
| Virtual run | 3 |
| Road cycling | 4 |
| Gravel cycling | 5 |
| MTB cycling | 6 |
| Virtual cycling | 7 |
| Indoor swimming | 8 |
| Open water swimming | 9 |
| General workout | 10 |
| Walk | 11 |
| Hike | 12 |
| Rowing | 13 |
| Yoga | 14 |
| Alpine ski | 15 |
| Nordic Ski | 16 |
| Snowboard | 17 |
| Transition | 18 |
| Strength Training | 19 |
| Crossfit | 20 |
| Tennis | 21 |
| Table Tennis | 22 |
| Badminton | 23 |
| Squash | 24 |
| Racquetball | 25 |
| Pickleball | 26 |


## Supported gear types
The table bellow details the gear types supported by Endurain:

| Name | Value |
| ---- | --- |
| Bike | 1 |
| Shoes | 2 |
| Wetsuit | 3 |
| Racquet | 4 |