# Stage 1: Build Vue.js app
FROM node:24-slim AS frontend-build

# Set the working directory to /tmp/frontend
WORKDIR /tmp/frontend

# Copy and install dependencies
COPY frontend/app/package*.json ./
RUN npm ci --prefer-offline

# Copy the frontend directory
COPY frontend/app ./

# Build the app
RUN npm run build

# Stage 2: Install requirements
FROM python:3.13-alpine AS requirements-stage

# Set the working directory
WORKDIR /tmp/backend

# Install Poetry and add poetry-plugin-export
RUN pip install --no-cache-dir poetry \
&& poetry self add poetry-plugin-export

# Copy pyproject.toml and poetry.lock* files
COPY backend/pyproject.toml backend/poetry.lock* ./

# Install dependencies using poetry and export them to requirements.txt
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

# Stage 3: Build FastAPI app
FROM python:3.13-alpine

# Install dependencies
RUN apk add --no-cache \
    build-base \
    mariadb-dev \
    pkgconfig \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev \
    gcc \
    curl \
    ca-certificates

# Install the latest gosu
RUN set -eux; \
    arch="$(uname -m)"; \
    case "$arch" in \
        x86_64) gosu_arch='amd64' ;; \
        aarch64) gosu_arch='arm64' ;; \
        *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    latest_version="$(curl -sSL https://api.github.com/repos/tianon/gosu/releases/latest | grep '"tag_name"' | head -n 1 | cut -d '"' -f4)"; \
    curl -o /usr/local/bin/gosu -SL "https://github.com/tianon/gosu/releases/download/${latest_version}/gosu-${gosu_arch}"; \
    chmod +x /usr/local/bin/gosu; \
    gosu nobody true

# Define environment variables
ENV UID=1000 \
    GID=1000 \
    TZ="UTC" \
    DB_TYPE="postgres" \
    DB_HOST="postgres" \
    DB_PORT=5432 \
    DB_USER="endurain" \
    DB_PASSWORD="changeme" \
    DB_DATABASE="endurain" \
    SECRET_KEY="changeme" \
    ALGORITHM="HS256" \
    ACCESS_TOKEN_EXPIRE_MINUTES=15 \
    REFRESH_TOKEN_EXPIRE_DAYS=7 \
    JAEGER_ENABLED="false" \
    JAEGER_HOST="jaeger" \
    JAEGER_PROTOCOL="http" \
    JAGGER_PORT=4317 \
    ENDURAIN_HOST="http://localhost:8080" \
    GEOCODES_MAPS_API="changeme" \
    BEHIND_PROXY=false \
    ENVIRONMENT="production"

# Set the working directory to /app/frontend
WORKDIR /app/frontend

# Copy the directory app contents to /app
COPY --from=frontend-build /tmp/frontend/dist ./dist

# Set the working directory to /app/backend
WORKDIR /app/backend

# Copy requirements.txt from requirements-stage to /app/backend
COPY --from=requirements-stage /tmp/backend/requirements.txt ./requirements.txt

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --upgrade -r ./requirements.txt

# Copy the directory app contents to /app
COPY backend/app ./

# Copy the entrypoint script for starting the FastAPI app
COPY docker/start.sh /docker-entrypoint.d/start.sh

# Make the script executable
RUN chmod +x /docker-entrypoint.d/start.sh

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Add a healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s CMD curl -f http://localhost:8080/api/v1/about || exit 1

# Run the FastAPI app
ENTRYPOINT ["/docker-entrypoint.d/start.sh"]