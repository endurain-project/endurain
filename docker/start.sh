#!/bin/bash
set -e

# Substitute MY_APP_ENDURAIN_HOST with the value of ENDURAIN_HOST
if [ ! -z "$ENDURAIN_HOST" ]; then
    echo "Substituting MY_APP_ENDURAIN_HOST with $ENDURAIN_HOST"
    find /app/backend/frontend/dist -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|MY_APP_ENDURAIN_HOST|${ENDURAIN_HOST}|g" '{}' +
fi

# Substitute MY_APP_STRAVA_CLIENT_ID with the value of STRAVA_CLIENT_ID
if [ ! -z "$STRAVA_CLIENT_ID" ]; then
    echo "Substituting MY_APP_STRAVA_CLIENT_ID with $STRAVA_CLIENT_ID"
    find /app/backend/frontend/dist -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|MY_APP_STRAVA_CLIENT_ID|${STRAVA_CLIENT_ID}|g" '{}' +
fi

echo "Starting FastAPI with BEHIND_PROXY=$BEHIND_PROXY"

# Base command as an array
CMD=("uvicorn" "main:app" "--host" "0.0.0.0" "--port" "80")

# Add --proxy-headers if BEHIND_PROXY is true
if [ "$BEHIND_PROXY" = "true" ]; then
    echo "Enabling proxy headers"
    CMD+=("--proxy-headers")
fi

# Execute the command
exec "${CMD[@]}"