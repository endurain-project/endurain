#!/bin/sh

set -e

echo_info_log() {
    echo "INFO:     $1"
}

echo_error_log() {
    echo "ERROR:     $1" >&2
}

validate_id() {
    case "$1" in
        ''|*[!0-9]*)
            echo_error_log "Invalid ID: $1. Must be a non-negative integer."
            exit 1
            ;;
    esac
}

validate_id "$UID"
validate_id "$GID"

echo_info_log "UID=$UID, GID=$GID"

if [ -n "$ENDURAIN_HOST" ]; then
    echo "window.env = { ENDURAIN_HOST: \"$ENDURAIN_HOST\" };" > /app/frontend/dist/env.js
    echo_info_log "Runtime env.js written with ENDURAIN_HOST=$ENDURAIN_HOST"
fi

echo_info_log "Starting FastAPI with BEHIND_PROXY=$BEHIND_PROXY"

CMD="uvicorn main:app --host 0.0.0.0 --port 8080"
if [ "$BEHIND_PROXY" = "true" ]; then
    CMD="$CMD --proxy-headers"
fi

exec gosu "$UID:$GID" $CMD