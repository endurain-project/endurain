#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Function to log messages
echo_info_log() {
    echo "INFO: $1"
}

echo_error_log() {
    echo "ERROR: $1" >&2
}

# Function to validate UID and GID
validate_id() {
    if ! [[ "$1" =~ ^[0-9]+$ ]]; then
        echo_error_log "Invalid ID: $1. Must be a non-negative integer."
        exit 1
    fi
}

# Check ownership of necessary directories
echo_info_log "Checking ownership of necessary directories..."

# Dynamically adjust UID and GID based on host-mounted directory or environment variables
HOST_UID=${UID:-$(stat -c '%u' /app/backend/logs 2>/dev/null || echo 1000)}
HOST_GID=${GID:-$(stat -c '%g' /app/backend/logs 2>/dev/null || echo 1000)}

# Validate UID and GID
validate_id "$HOST_UID"
validate_id "$HOST_GID"

# Avoid setting ownership to root (UID/GID = 0)
if [ "$HOST_UID" -eq 0 ] || [ "$HOST_GID" -eq 0 ]; then
    echo_error_log "UID or GID is set to 0 (root). Adjust ownership manually to a non-root user."
    exit 1
fi

echo_info_log "Adjusting ownership to match host UID ($HOST_UID) and GID ($HOST_GID)..."

# List of directories to adjust ownership
directories=(
    /app/backend/logs
    /app/backend/user_images
    /app/backend/files
    /app/backend/server_images
)

# Adjust ownership for each directory
for dir in "${directories[@]}"; do
    if [ -d "$dir" ]; then
        chown -R "$HOST_UID:$HOST_GID" "$dir"
        echo_info_log "Ownership adjusted for $dir"
    else
        echo_info_log "Directory $dir does not exist, skipping."
    fi
done

# Substitute MY_APP_ENDURAIN_HOST with the value of ENDURAIN_HOST
if [ -n "$ENDURAIN_HOST" ]; then
    echo_info_log "Substituting MY_APP_ENDURAIN_HOST with $ENDURAIN_HOST"
    find /app/frontend/dist -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|MY_APP_ENDURAIN_HOST|${ENDURAIN_HOST}|g" '{}' +
fi

# Substitute MY_APP_STRAVA_CLIENT_ID with the value of STRAVA_CLIENT_ID
if [ -n "$STRAVA_CLIENT_ID" ]; then
    echo_info_log "Substituting MY_APP_STRAVA_CLIENT_ID with $STRAVA_CLIENT_ID"
    find /app/frontend/dist -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|MY_APP_STRAVA_CLIENT_ID|${STRAVA_CLIENT_ID}|g" '{}' +
fi

echo_info_log "Starting FastAPI with BEHIND_PROXY=$BEHIND_PROXY"

# Define the base command for starting the FastAPI server as an array
CMD=("uvicorn" "main:app" "--host" "0.0.0.0" "--port" "8080")

# Add --proxy-headers if BEHIND_PROXY is true
if [ "$BEHIND_PROXY" = "true" ]; then
    echo_info_log "Enabling proxy headers"
    CMD+=("--proxy-headers")
fi

# Execute the command
exec "${CMD[@]}"
