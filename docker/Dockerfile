# Stage 0: Pin uv version
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv-dist

# Stage 1: Build Vue.js app
FROM node:24-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5 AS frontend-build

# Set the working directory to /tmp/frontend
WORKDIR /tmp/frontend

# Copy and install dependencies
COPY frontend/package*.json ./
RUN npm ci --prefer-offline --ignore-scripts

# Copy the frontend directory
COPY frontend ./

# Build the app
RUN npm run build

# Stage 2: Install requirements
FROM python:3.13-alpine@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a AS requirements-stage

# Optional project extras baked into the image. Empty by default so the image
# stays lean for `local` deployments. Build with
# `--build-arg PYTHON_EXTRAS=distributed` to add the Redis / S3 dependencies
# required by REDIS_URL / STATE_URI / EVENTS_URI=redis://... and STORAGE_URI=s3://...
ARG PYTHON_EXTRAS=""

# Set the working directory
WORKDIR /tmp/backend

# Install uv
COPY --from=uv-dist /uv /uvx /usr/local/bin/

# Copy pyproject.toml and uv.lock files
COPY backend/pyproject.toml backend/uv.lock ./

# Export production dependencies to requirements.txt
RUN uv export --no-emit-project --no-dev ${PYTHON_EXTRAS:+--extra "$PYTHON_EXTRAS"} -o requirements.txt

# Stage 3: Build FastAPI app
FROM python:3.13-alpine@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a

ARG UID=1000
ARG GID=1000
ARG APP_USER=appuser

# Install dependencies (privileged — must run before USER)
RUN apk add --no-cache \
    build-base \
    pkgconfig \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev \
    gcc \
    curl \
    ca-certificates

# Create configurable non-root user
# Alpine's adduser does not create sparse /var/log/faillog files,
# so --no-log-init (Debian-specific) is not needed here.
RUN addgroup -S -g ${GID} ${APP_USER} \
 && adduser -S -u ${UID} -G ${APP_USER} -h /app -s /sbin/nologin ${APP_USER}

# Pre-create /app and set ownership so the non-root user can write to it
RUN mkdir -p /app && chown -R ${APP_USER}:${APP_USER} /app

# Define environment variables
ENV BEHIND_PROXY=false

# --- Frontend ---
WORKDIR /app/frontend

COPY --from=frontend-build --chown=${UID}:${GID} /tmp/frontend/dist ./dist

# --- Backend ---
WORKDIR /app/backend

COPY --from=requirements-stage --chown=${UID}:${GID} /tmp/backend/requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --require-hashes -r ./requirements.txt

COPY --chown=${UID}:${GID} backend/app ./

# --- Entrypoint ---
COPY --chown=${UID}:${GID} docker/start.sh /docker-entrypoint.d/start.sh

# Normalize line endings and make the script executable.
# This avoids '/bin/sh\r: no such file or directory' when the file
# is checked out with CRLF on Windows hosts.
RUN sed -i 's/\r$//' /docker-entrypoint.d/start.sh \
 && chmod +x /docker-entrypoint.d/start.sh

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Add a healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 CMD curl -f http://localhost:8080/api/v1/about || exit 1

# Switch to non-root user - all privileged RUN commands above
USER ${APP_USER}

# Run the FastAPI app
ENTRYPOINT ["/docker-entrypoint.d/start.sh"]