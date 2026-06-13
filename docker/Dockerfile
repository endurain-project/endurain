# Stage 0: Pin uv version
FROM ghcr.io/astral-sh/uv:0.11.18@sha256:78bc42400d77b0678ba95765305c826652ed5431f399257271dda681d0318f03 AS uv-dist

# Stage 1: Build Vue.js app
FROM node:24-slim@sha256:2c87ef9bd3c6a3bd4b472b4bec2ce9d16354b0c574f736c476489d09f560a203 AS frontend-build

# Set the working directory to /tmp/frontend
WORKDIR /tmp/frontend

# Copy and install dependencies
COPY frontend/app/package*.json ./
RUN npm ci --prefer-offline --ignore-scripts

# Copy the frontend directory
COPY frontend/app ./

# Build the app
RUN npm run build

# Stage 2: Install requirements
FROM python:3.13-alpine@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc AS requirements-stage

# Set the working directory
WORKDIR /tmp/backend

# Install uv
COPY --from=uv-dist /uv /uvx /usr/local/bin/

# Copy pyproject.toml and uv.lock files
COPY backend/pyproject.toml backend/uv.lock ./

# Export production dependencies to requirements.txt
RUN uv export --no-emit-project --no-dev -o requirements.txt

# Stage 3: Build FastAPI app
FROM python:3.13-alpine@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc

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

# env.js is created world-writable (666) so the file can be overwritten at
# runtime even when docker-compose overrides the container user via `user:`
# to a UID different from the one baked in at build time (ARG UID).
RUN touch /app/frontend/dist/env.js && chmod 666 /app/frontend/dist/env.js

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