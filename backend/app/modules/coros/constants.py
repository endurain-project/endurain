"""Stable COROS integration constants."""

from enum import StrEnum

#: Stable provider identifier registered with activity ingestion.
PROVIDER_NAME = "coros"

#: Official COROS MCP endpoint. COROS routes it to the account's regional
#: server and publishes the matching OAuth metadata from the gateway.
MCP_URL = "https://mcp.coros.com/mcp"

#: Only the scopes COROS publishes on its authorization server metadata.
SCOPES = ("openid", "offline_access", "mcp.tools")
SCOPE_STRING = " ".join(SCOPES)

#: MCP tools this integration requires. Availability is checked from
#: ``tools/list`` on every sync instead of being assumed.
TOOL_QUERY_ACTIVITIES = "querySportRecords"
TOOL_DOWNLOAD_FIT = "downloadActivityFitFiles"
TOOL_FIT_DOWNLOAD_URLS = "queryActivityFitFileDownloadUrls"
REQUIRED_TOOLS = frozenset({TOOL_QUERY_ACTIVITIES, TOOL_DOWNLOAD_FIT})

#: A pending authorization is short-lived; the user must finish the browser
#: round-trip within this window.
STATE_TTL_MINUTES = 10

#: COROS documents 30-day access tokens and 180-day refresh tokens. The token
#: response normally carries ``expires_in``; these are the fallbacks when it
#: does not.
ACCESS_TOKEN_FALLBACK_DAYS = 30
REFRESH_TOKEN_FALLBACK_DAYS = 180

#: Refresh proactively instead of waiting for the first rejected call.
TOKEN_REFRESH_SKEW_MINUTES = 10

#: COROS allows 50 FIT file downloads per user in a fixed 24-hour window.
MAX_FIT_DOWNLOADS_PER_DAY = 50

#: Files larger than this are rejected before parsing, matching the shared
#: activity-file upload cap.
MAX_FIT_BYTES = 200 * 1024 * 1024

#: The documented default page size of ``querySportRecords``. A window
#: returning that many is split in half so results are not silently truncated
#: if the server caps the requested limit at its default.
SPORT_RECORDS_PAGE_SIZE = 20

#: A sync guard longer than the worst-case 50-file backfill. It expires on its
#: own if a process dies, so a crashed sync never blocks the user forever.
SYNC_GUARD_TTL_SECONDS = 2 * 60 * 60

#: A corrupt or unparseable FIT file is retried after this delay, in case the
#: failure was a transient server-side problem rather than the file itself.
INVALID_FILE_RETRY_DAYS = 7

#: Days covered by the automatic initial sync when an account is connected.
INITIAL_SYNC_DAYS = 30

#: Days re-read by "Sync now"; overlapping the hourly refresh catches late
#: uploads without re-downloading the whole history.
MANUAL_SYNC_DAYS = 7

#: COROS record queries use the documented ``yyyyMMdd`` format.
COROS_DATE_FORMAT = "%Y%m%d"


class SyncStatus(StrEnum):
    """Outcome of the most recent sync attempt."""

    NEVER = "never"
    SUCCESS = "success"
    ERROR = "error"


class SyncErrorCode(StrEnum):
    """Sanitized reason shown to the user after a failed sync."""

    AUTHORIZATION_EXPIRED = "authorization_expired"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"
    TOOLS_UNAVAILABLE = "tools_unavailable"
    QUOTA_EXHAUSTED = "quota_exhausted"
    PROTOCOL_ERROR = "protocol_error"
    PROCESSING_ERROR = "processing_error"
