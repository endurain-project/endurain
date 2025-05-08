#!/bin/sh

set -e

echo_info_log() {
    echo "INFO: $1"
}

echo_error_log() {
    echo "ERROR: $1" >&2
}

validate_id() {
    case "$1" in
        ''|*[!0-9]*)
            echo_error_log "Invalid ID: $1. Must be a non-negative integer."
            exit 1
            ;;
    esac
}

adjust_folder_ownership() {
    if [ -d "$1" ]; then
        chown -R "$UID:$GID" "$1"
        echo_info_log "Ownership adjusted for $1"
    else
        echo_info_log "Directory $1 does not exist, skipping."
    fi
}

validate_id "$UID"
validate_id "$GID"

echo_info_log "UID=$UID, GID=$GID"

# List of directories (space-separated for POSIX shell)
directories="/app/backend/logs /app/backend/user_images /app/backend/files /app/backend/server_images"

for dir in $directories; do
    adjust_folder_ownership "$dir"
done

if [ -n "$ENDURAIN_HOST" ]; then
    echo_info_log "Substituting MY_APP_ENDURAIN_HOST with $ENDURAIN_HOST"
    find /app/frontend/dist -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|MY_APP_ENDURAIN_HOST|$ENDURAIN_HOST|g" {} +
fi

echo_info_log "Starting FastAPI with BEHIND_PROXY=$BEHIND_PROXY"

CMD="uvicorn main:app --host 0.0.0.0 --port 8080"
if [ "$BEHIND_PROXY" = "true" ]; then
    CMD="$CMD --proxy-headers"
fi

exec gosu "$UID:$GID" $CMD