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
    echo "/app/backend/logs directory does not exist. Using default UID 1000."
    HOST_UID=1000  # Default to 1000 if directory does not exist
    HOST_GID=1000  # Default to 1000 if directory does not exist
fi

# Get the current UID and GID of the 'endurain' user
USER_UID=$(id -u endurain)
USER_GID=$(id -g endurain)

# Only adjust if the user UID/GID doesn't match the host directory UID/GID
if [ "$USER_UID" -ne "$HOST_UID" ] || [ "$USER_GID" -ne "$HOST_GID" ]; then
    echo "Adjusting ownership to match host UID ($HOST_UID) and GID ($HOST_GID)..."

    # Avoid setting the UID/GID to 0 (root user UID/GID)
    if [ "$HOST_UID" -ne 0 ]; then
        usermod -u "$HOST_UID" endurain
    else
        echo "Skipping UID change to 0 (root UID)."
    fi

    if [ "$HOST_GID" -ne 0 ]; then
        groupmod -g "$HOST_GID" endurain
    else
        echo "Skipping GID change to 0 (root GID)."
    fi

    # Update the ownership of the mounted directories
    chown -R endurain:endurain /app/backend/logs /app/backend/user_images /app/backend/files
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
CMD=("uvicorn" "main:app" "--host" "0.0.0.0" "--port" "80")

# Add --proxy-headers if BEHIND_PROXY is true
if [ "$BEHIND_PROXY" = "true" ]; then
    echo "Enabling proxy headers"
    CMD+=("--proxy-headers")
fi

# Execute the command
exec "${CMD[@]}"
