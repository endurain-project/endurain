#!/bin/sh

# Substitute MY_APP_ENDURAIN_HOST with the value of ENDURAIN_HOST
if [ ! -z "$ENDURAIN_HOST" ]; then
    find /app/backend/frontend/dist -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|MY_APP_ENDURAIN_HOST|${ENDURAIN_HOST}|g" '{}' +
fi

# Substitute MY_APP_STRAVA_CLIENT_ID with the value of STRAVA_CLIENT_ID
if [ ! -z "$STRAVA_CLIENT_ID" ]; then
    find /app/backend/frontend/dist -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|MY_APP_STRAVA_CLIENT_ID|${STRAVA_CLIENT_ID}|g" '{}' +
fi