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

# Create required directories with correct ownership
# These directories are created as root before switching to the non-root user
# to ensure proper permissions on fresh volume mounts
DATA_FOLDER="${DATA_DIR:-$BACKEND_DIR/data}"
LOGS_FOLDER="${LOGS_DIR:-$BACKEND_DIR/logs}"

REQUIRED_DIRS="
$DATA_FOLDER
$DATA_FOLDER/user_images
$DATA_FOLDER/server_images
$DATA_FOLDER/activity_media
$DATA_FOLDER/activity_files
$DATA_FOLDER/activity_files/processed
$DATA_FOLDER/activity_files/bulk_import
$DATA_FOLDER/activity_files/bulk_import/import_errors
$LOGS_FOLDER
"

for dir in $REQUIRED_DIRS; do
    if [ ! -d "$dir" ]; then
        echo_info_log "Creating directory: $dir"
        mkdir -p "$dir"
    fi
    echo_info_log "Setting ownership recursively of $dir to $UID:$GID"
    chown -R "$UID:$GID" "$dir"
done

if [ -n "$ENDURAIN_HOST" ]; then
    FRONTEND_FOLDER="${FRONTEND_DIR:-/app/frontend/dist}"
    echo "window.env = { ENDURAIN_HOST: \"$ENDURAIN_HOST\" };" > "$FRONTEND_FOLDER/env.js"
    echo_info_log "Runtime env.js written with ENDURAIN_HOST=$ENDURAIN_HOST"
fi

# Set log level (default: info)
# Supported levels: critical, error, warning, info, debug, trace
LOG_LEVEL="${LOG_LEVEL:-info}"

# Validate log level
case "$LOG_LEVEL" in
    critical|error|warning|info|debug|trace)
        # Valid log level
        ;;
    *)
        echo_error_log "Invalid LOG_LEVEL '$LOG_LEVEL'. Supported levels: critical, error, warning, info, debug, trace. Defaulting to 'info'."
        LOG_LEVEL="info"
        ;;
esac

echo_info_log "Starting FastAPI with BEHIND_PROXY=$BEHIND_PROXY, LOG_LEVEL=$LOG_LEVEL"

CMD="uvicorn main:app --host 0.0.0.0 --port 8080 --log-level $LOG_LEVEL"
if [ "$BEHIND_PROXY" = "true" ]; then
    CMD="$CMD --proxy-headers"
fi

exec gosu "$UID:$GID" $CMD