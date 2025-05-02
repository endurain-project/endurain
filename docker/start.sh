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

adjust_folder_ownership(){
    if [ -d "$1" ]; then
        chown -R "$UID:$GID" "$1"
        echo_info_log "Ownership adjusted for $1"
    else
        echo_info_log "Directory $1 does not exist, skipping."
    fi
}

# Validate UID and GID
validate_id "$UID"
validate_id "$GID"

echo_info_log "UID=$UID, GID=$GID"

# List of directories to adjust ownership
directories=(
    /app/backend/logs
    /app/backend/user_images
    /app/backend/files
    /app/backend/server_images
)

# Adjust ownership for each directory
echo_info_log "Adjusting ownership to match UID ($UID) and GID ($GID)..."

for dir in "${directories[@]}"; do
    adjust_folder_ownership "$dir"
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
exec gosu "$UID:$GID" "${CMD[@]}"
