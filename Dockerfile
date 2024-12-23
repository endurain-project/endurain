# Stage 1: Build Vue.js app
FROM node:20 AS frontend-build

# Set the working directory to /app/frontend
WORKDIR /tmp/frontend

# Copy and install dependencies
COPY frontend/app/package*.json ./
RUN npm install --frozen-lockfile

# Copy the frontend directory
COPY frontend/app ./

# Build the app
RUN npm run build

# Stage 2: Install requirements
FROM python:3.12 AS requirements-stage

# Set the working directory
WORKDIR /tmp/backend

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy pyproject.toml and poetry.lock* files
COPY backend/pyproject.toml backend/poetry.lock* ./

# Install dependencies using poetry and export them to requirements.txt
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

# Stage 3: Build FastAPI app
FROM python:3.12

# Define environment variables
ENV TZ="UTC" \
    DB_TYPE="mariadb" \
    DB_HOST="mariadb" \
    DB_PORT=3306 \
    DB_USER="endurain" \
    DB_PASSWORD="changeme" \
    DB_DATABASE="endurain" \
    SECRET_KEY="changeme" \
    ALGORITHM="HS256" \
    ACCESS_TOKEN_EXPIRE_MINUTES=30 \
    REFRESH_TOKEN_EXPIRE_DAYS=7 \
    STRAVA_CLIENT_ID="changeme" \
    STRAVA_CLIENT_SECRET="changeme" \
    STRAVA_AUTH_CODE="changeme" \
    JAEGER_ENABLED="false" \
    JAEGER_HOST="jaeger" \
    JAEGER_PROTOCOL="http" \
    JAGGER_PORT=4317 \
    ENDURAIN_HOST="http://localhost:8080" \
    GEOCODES_MAPS_API="changeme"

# Set the working directory to /app/backend
WORKDIR /app/backend

# Add a non-root user
RUN useradd -m endurain

# Copy requirements.txt from requirements-stage to /app/backend
COPY --from=requirements-stage /tmp/backend/requirements.txt ./requirements.txt

# Install dependencies
RUN pip install --no-cache-dir --upgrade -r ./requirements.txt

# Copy the directory app contents to /app
COPY backend/app ./

# Copy the directory app contents to /app
COPY --from=frontend-build /tmp/frontend/dist ./frontend/dist
COPY frontend/app/.env ./frontend/.env

# Copy the entrypoint script
COPY frontend_env.sh /docker-entrypoint.d/frontend_env.sh

# Make the entrypoint script executable
RUN chmod +x /docker-entrypoint.d/frontend_env.sh

# Change ownership to non-root user
RUN chown -R endurain:endurain ./

# Switch to non-root user
USER endurain

# Make port 80 available to the world outside this container
EXPOSE 80

# Run FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]