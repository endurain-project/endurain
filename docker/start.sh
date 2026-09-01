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

# uvicorn only honours --proxy-headers for peers listed in FORWARDED_ALLOW_IPS
# (default 127.0.0.1), so without it a proxy on any other address is ignored.
# Derive that list from TRUSTED_PROXIES, which operators already set for the
# application's own client-IP detection, so there is a single knob.
FORWARDED_ALLOW_IPS_LIST=""

append_forwarded_allow_ip() {
    case ",$FORWARDED_ALLOW_IPS_LIST," in
        *",$1,"*)
            return 0
            ;;
    esac
    if [ -z "$FORWARDED_ALLOW_IPS_LIST" ]; then
        FORWARDED_ALLOW_IPS_LIST="$1"
    else
        FORWARDED_ALLOW_IPS_LIST="$FORWARDED_ALLOW_IPS_LIST,$1"
    fi
}

# uvicorn cannot resolve hostnames (unmatched names become inert literals), so
# TRUSTED_PROXIES hostnames are resolved here. The application re-resolves them
# periodically for its own trust checks, so a proxy that changes IP after this
# snapshot still gets the correct client IP from core/network.py even though the
# uvicorn access log and request.client go stale until the next restart.
build_forwarded_allow_ips() {
    old_ifs="$IFS"
    IFS=','
    # -f disables pathname expansion so a literal "*" entry survives the split.
    set -f
    # shellcheck disable=SC2086
    set -- $TRUSTED_PROXIES
    set +f
    IFS="$old_ifs"

    for raw_entry in "$@"; do
        entry=$(printf '%s' "$raw_entry" | tr -d '[:space:]')
        if [ -z "$entry" ]; then
            continue
        fi

        if [ "$entry" = "*" ]; then
            FORWARDED_ALLOW_IPS_LIST="*"
            return 0
        fi

        # Classify strictly: uvicorn silently turns anything it cannot parse as
        # an IP/CIDR into an inert literal that never matches a peer, so entries
        # that are not pure IP syntax must go through hostname resolution.
        case "$entry" in
            *[!0-9A-Fa-f:./]*) entry_is_ip=0 ;;  # non-hex character -> hostname
            *:*) entry_is_ip=1 ;;                # IPv6 literal or CIDR
            *[!0-9./]*) entry_is_ip=0 ;;         # hex letters, no colon -> hostname
            *) entry_is_ip=1 ;;                  # IPv4 literal or CIDR
        esac

        if [ "$entry_is_ip" = "1" ]; then
            append_forwarded_allow_ip "$entry"
            continue
        fi

        resolved_ips=$(getent hosts "$entry" 2>/dev/null | awk '{print $1}')
        if [ -z "$resolved_ips" ]; then
            echo_error_log "Could not resolve TRUSTED_PROXIES hostname '$entry'; uvicorn will not honour forwarded headers from it."
            continue
        fi
        for resolved_ip in $resolved_ips; do
            append_forwarded_allow_ip "$resolved_ip"
        done
    done
}

CMD="uvicorn main:app --host 0.0.0.0 --port 8080 --log-level $LOG_LEVEL"
if [ "$BEHIND_PROXY" = "true" ]; then
    CMD="$CMD --proxy-headers"
    if [ -n "$FORWARDED_ALLOW_IPS" ]; then
        echo_info_log "Honouring forwarded headers from FORWARDED_ALLOW_IPS override: $FORWARDED_ALLOW_IPS"
    else
        build_forwarded_allow_ips
        if [ -n "$FORWARDED_ALLOW_IPS_LIST" ]; then
            # Exported rather than passed as --forwarded-allow-ips so it also
            # applies to a uvicorn/gunicorn started by an overridden command.
            export FORWARDED_ALLOW_IPS="$FORWARDED_ALLOW_IPS_LIST"
            echo_info_log "Honouring forwarded headers from: $FORWARDED_ALLOW_IPS_LIST"
        else
            echo_error_log "BEHIND_PROXY=true but no usable TRUSTED_PROXIES entry was found; uvicorn will only honour forwarded headers from 127.0.0.1. Set TRUSTED_PROXIES to your reverse proxy address, CIDR, or hostname."
        fi
    fi
fi

exec $CMD