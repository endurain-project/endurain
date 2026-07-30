#!/bin/sh

set -e

echo_info_log() {
    echo "INFO:     $1"
}

echo_error_log() {
    echo "ERROR:     $1" >&2
}

# Log the container's UID and GID for troubleshooting
current_uid=$(id -u)
current_gid=$(id -g)
echo_info_log "Container running as UID $current_uid, GID $current_gid"

# Create required directories
BACKEND_FOLDER="${BACKEND_DIR:-/app/backend}"
DATA_FOLDER="${DATA_DIR:-$BACKEND_FOLDER/data}"
LOGS_FOLDER="${LOGS_DIR:-$BACKEND_FOLDER/logs}"
FRONTEND_FOLDER="${FRONTEND_DIR:-/app/frontend/dist}"

# Pre-created so a fresh data volume has the full layout visible from boot.
# Most of these are also asserted by config.check_required_dirs(); the
# exception is upload_staging, which is the local StorageProvider's area for
# uploads awaiting import. The provider creates it on demand, and an S3
# deployment has no such directory at all, so it is deliberately not a config
# constant — it is listed here only so operators see it alongside the rest.
REQUIRED_DIRS="
$DATA_FOLDER
$DATA_FOLDER/user_images
$DATA_FOLDER/server_images
$DATA_FOLDER/activity_media
$DATA_FOLDER/activity_thumbnails
$DATA_FOLDER/activity_files
$DATA_FOLDER/activity_files/processed
$DATA_FOLDER/activity_files/bulk_import
$DATA_FOLDER/activity_files/bulk_import/import_errors
$DATA_FOLDER/activity_files/upload_incoming
$DATA_FOLDER/activity_files/upload_staging
$DATA_FOLDER/activity_files/strava_import
$DATA_FOLDER/activity_files/strava_import/activities
$DATA_FOLDER/activity_files/strava_import/media
$DATA_FOLDER/activity_files/strava_import/import_errors
$LOGS_FOLDER
"

for dir in $REQUIRED_DIRS; do
    if [ ! -d "$dir" ]; then
        echo_info_log "Creating directory: $dir"
        if ! mkdir -p "$dir" 2>/dev/null; then
            echo_error_log "Cannot create $dir - permission denied."
            echo_error_log "Container UID: $current_uid, GID: $current_gid"
            if echo "$dir" | grep -q "^$LOGS_FOLDER"; then
                mount_root="$LOGS_FOLDER"
            else
                mount_root="$DATA_FOLDER"
            fi
            if [ -d "$mount_root" ]; then
                echo_error_log "Mount point: $(stat -c '%A  owner=%u  group=%g  path=%n' "$mount_root" 2>/dev/null || true)"
            fi
            echo_error_log "The bind mount on the host is not writable by container UID $current_uid, GID $current_gid."
            echo_error_log "Fix on the host - run once:"
            echo_error_log "  sudo chown -R $current_uid:$current_gid /var/opt/endurain/backend"
            echo_error_log "(Replace /var/opt/endurain with your LOCAL_PATH if set.)"
            echo_error_log "See docs.endurain.com/getting-started#create-directory-structure"
            exit 1
        fi
    fi
done

if [ -n "$ENDURAIN_HOST" ]; then
    echo "window.env = { ENDURAIN_HOST: \"$ENDURAIN_HOST\" };" > "$FRONTEND_FOLDER/env.js"
    echo_info_log "Runtime env.js written with ENDURAIN_HOST=$ENDURAIN_HOST"

    # Pin the SPA's fallback Content-Security-Policy connect-src to the exact
    # backend API/WebSocket origin derived from ENDURAIN_HOST, replacing the
    # broad build-time default. Only a statically served SPA relies on this meta
    # CSP; the backend response-header CSP stays authoritative where it serves
    # the page. Re-derived on every start so it tracks ENDURAIN_HOST changes.
    INDEX_HTML="$FRONTEND_FOLDER/index.html"
    if [ -f "$INDEX_HTML" ]; then
        # Strip trailing slashes to get a clean origin (scheme://host[:port]).
        API_ORIGIN="$ENDURAIN_HOST"
        while [ "${API_ORIGIN%/}" != "$API_ORIGIN" ]; do
            API_ORIGIN="${API_ORIGIN%/}"
        done

        # Derive the matching WebSocket origin (http -> ws, https -> wss).
        WS_ORIGIN=""
        case "$API_ORIGIN" in
            https://*) WS_ORIGIN="wss://${API_ORIGIN#https://}" ;;
            http://*)  WS_ORIGIN="ws://${API_ORIGIN#http://}" ;;
        esac

        # Reject anything that is not a clean http(s) origin so a malformed
        # ENDURAIN_HOST cannot inject extra CSP directives or break the meta tag.
        case "$API_ORIGIN" in
            *[!A-Za-z0-9.:/_-]*) WS_ORIGIN="" ;;
        esac

        if [ -n "$WS_ORIGIN" ]; then
            # Preserve the external origins from the build-time default
            # (vite.config.ts) — currently the Codeberg release-update check.
            EXTERNAL_CONNECT="https://codeberg.org"
            # connect-src is the LAST CSP directive (see vite.config.ts), so match
            # through to the closing '"' of the meta content attribute. Matching to
            # the next ';' would corrupt the policy: the built HTML encodes quotes
            # as &#39; whose trailing ';' terminates the match early.
            tmp_file=$(mktemp) || exit 1
            if ! sed "s#connect-src [^\"]*#connect-src 'self' $API_ORIGIN $WS_ORIGIN $EXTERNAL_CONNECT#g" "$INDEX_HTML" > "$tmp_file"; then
                echo_error_log "Failed to update CSP connect-src in index.html"
                rm -f "$tmp_file"
                exit 1
            fi
            cat "$tmp_file" > "$INDEX_HTML" || { echo_error_log "Failed to write updated index.html"; rm -f "$tmp_file"; exit 1; }
            rm -f "$tmp_file"
            echo_info_log "Hardened CSP connect-src to 'self' $API_ORIGIN $WS_ORIGIN $EXTERNAL_CONNECT"
        else
            echo_error_log "ENDURAIN_HOST is not a clean http(s) origin; left CSP connect-src as 'self'."
        fi
    fi
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

# Select the process role: "api" (default) serves HTTP; "worker" drains the
# durable-job queue (requires JOBS_ENABLED=true). One image, two shapes.
APP_ROLE="${APP_ROLE:-api}"

case "$APP_ROLE" in
    api)
        CMD="uvicorn main:app --host 0.0.0.0 --port 8080 --log-level $LOG_LEVEL"
        if [ "$BEHIND_PROXY" = "true" ]; then
            CMD="$CMD --proxy-headers"
        fi
        # Run multiple Uvicorn workers when WEB_WORKERS > 1. The backend's
        # deployment fail-fast (Settings._enforce_deployment_topology) requires
        # shared state (Redis) and a shared coordination lock whenever
        # WEB_WORKERS > 1, so a multi-worker start that is not correctly
        # configured aborts at boot rather than silently diverging.
        WEB_WORKERS="${WEB_WORKERS:-1}"
        if [ "$WEB_WORKERS" -gt 1 ] 2>/dev/null; then
            CMD="$CMD --workers $WEB_WORKERS"
            echo_info_log "Starting Uvicorn with $WEB_WORKERS workers"
        fi
        exec $CMD
        ;;
    worker)
        echo_info_log "Starting durable-job worker (APP_ROLE=worker)"
        exec python worker.py
        ;;
    *)
        echo_error_log "Invalid APP_ROLE '$APP_ROLE'. Supported roles: api, worker."
        exit 1
        ;;
esac