#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Check if the mounted directory exists and has proper permissions
echo "Checking ownership of necessary directories..."

# Dynamically adjust UID and GID based on host-mounted directory
if [ -d "/app/backend/logs" ]; then
    HOST_UID=$(stat -c '%u' /app/backend/logs)  # Get UID if directory exists
    HOST_GID=$(stat -c '%g' /app/backend/logs)  # Get GID if directory exists
else
    echo "/app/backend/logs directory does not exist. Using default provided UID and GID. Default is 1000."
    HOST_UID=${UID:-1000}
    HOST_GID=${GID:-1000}
fi

# Avoid setting ownership to root (UID/GID = 0)
if [ "$HOST_UID" -ne 0 ] && [ "$HOST_GID" -ne 0 ]; then
    echo "Adjusting ownership to match host UID ($HOST_UID) and GID ($HOST_GID)..."
    for dir in /app/backend/logs /app/backend/user_images /app/backend/files; do
        if [ -d "$dir" ]; then
            chown -R "$HOST_UID:$HOST_GID" "$dir"
        else
            echo "Directory $dir does not exist, skipping chown."
        fi
    done
else
    echo "Directory is owned by root UID/GID (0). Adjusting will fail, change ownership manually to non-root, example 1000:1000."
fi

# Substitute MY_APP_ENDURAIN_HOST with the value of ENDURAIN_HOST
if [ -n "$ENDURAIN_HOST" ]; then
    echo "Substituting MY_APP_ENDURAIN_HOST with $ENDURAIN_HOST"
    find /app/frontend/dist -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|MY_APP_ENDURAIN_HOST|${ENDURAIN_HOST}|g" '{}' +
fi

# Substitute MY_APP_STRAVA_CLIENT_ID with the value of STRAVA_CLIENT_ID
if [ -n "$STRAVA_CLIENT_ID" ]; then
    echo "Substituting MY_APP_STRAVA_CLIENT_ID with $STRAVA_CLIENT_ID"
    find /app/frontend/dist -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|MY_APP_STRAVA_CLIENT_ID|${STRAVA_CLIENT_ID}|g" '{}' +
fi

echo "Starting FastAPI with BEHIND_PROXY=$BEHIND_PROXY"

# Define the base command for starting the FastAPI server as an array
CMD=("uvicorn" "main:app" "--host" "0.0.0.0" "--port" "8080")

# Add --proxy-headers if BEHIND_PROXY is true
if [ "$BEHIND_PROXY" = "true" ]; then
    echo "Enabling proxy headers"
    CMD+=("--proxy-headers")
fi

# Execute the command
exec "${CMD[@]}"
