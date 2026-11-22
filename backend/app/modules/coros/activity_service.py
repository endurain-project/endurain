"""Pull COROS activities through MCP and feed them to the shared ingestion pipeline.

The sync is idempotent: activities already stored are skipped by their COROS
id, and the ingestion pipeline keys each parsed session on the COROS id plus its
start time. FIT downloads are capped per user per day, and activities COROS has
no usable file for are recorded once instead of retried on every sync.
"""

import json
import re
import tempfile
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse

import httpx2
import jasil.providers as platform_providers
from jasil.container import Platform

import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import core.network as core_network
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.coros.constants as coros_constants
import modules.coros.contracts as coros_contracts
import modules.coros.crud as coros_crud
import modules.coros.mcp_client as coros_mcp_client
import modules.coros.oauth as coros_oauth
import modules.coros.service as coros_service
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)

_SPORT_RECORDS_LABEL_RE = re.compile(
    r"label[_\s-]*id\s*[\"']?\s*[:=]\s*[\"']?([0-9A-Za-z_-]+)",
    re.IGNORECASE,
)
_SPORT_RECORDS_SPORT_RE = re.compile(
    r"sport[_\s-]*type\s*[\"']?\s*[:=]\s*[\"']?(\d+)",
    re.IGNORECASE,
)
_QUERY_CHUNK_DAYS = 7
_MAX_REDIRECTS = 3


def _date_chunks(start_date: date, end_date: date) -> Iterator[tuple[date, date]]:
    """Split an inclusive date range into bounded query windows.

    Args:
        start_date: First date.
        end_date: Last date.

    Yields:
        Inclusive ``(start, end)`` pairs.
    """
    cursor = start_date
    while cursor <= end_date:
        chunk_end = min(cursor + timedelta(days=_QUERY_CHUNK_DAYS - 1), end_date)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _structured_records(value: object, records: list[coros_contracts.CorosActivitySummary]) -> None:
    """Collect activity identifiers from structured tool output.

    Args:
        value: Structured content or nested value.
        records: Accumulator, mutated in place.
    """
    if isinstance(value, dict):
        label_id = value.get("labelId", value.get("label_id"))
        sport_type = value.get("sportType", value.get("sport_type"))
        if isinstance(sport_type, str) and sport_type.isdigit():
            sport_type = int(sport_type)
        if isinstance(label_id, (str, int)) and isinstance(sport_type, int):
            records.append(
                coros_contracts.CorosActivitySummary(
                    label_id=str(label_id),
                    sport_type=sport_type,
                )
            )
        for nested in value.values():
            _structured_records(nested, records)
    elif isinstance(value, list):
        for nested in value:
            _structured_records(nested, records)


def _table_records(text: str, records: list[coros_contracts.CorosActivitySummary]) -> None:
    """Collect activity identifiers from a Markdown-style table.

    Args:
        text: Tool text content.
        records: Accumulator, mutated in place.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if "|" not in line:
            continue
        headers = [cell.strip().lower() for cell in line.strip("|").split("|")]
        label_index = next(
            (position for position, header in enumerate(headers) if "label" in header and "id" in header),
            None,
        )
        sport_index = next(
            (position for position, header in enumerate(headers) if "sport" in header and "type" in header),
            None,
        )
        if label_index is None or sport_index is None:
            continue
        for row in lines[index + 1 :]:
            if "|" not in row:
                continue
            cells = [cell.strip().strip("`*") for cell in row.strip("|").split("|")]
            if len(cells) <= max(label_index, sport_index):
                continue
            label_id = cells[label_index]
            sport_type = cells[sport_index]
            if label_id and sport_type.isdigit():
                records.append(
                    coros_contracts.CorosActivitySummary(
                        label_id=label_id,
                        sport_type=int(sport_type),
                    )
                )
        break


def _text_records(text: str, records: list[coros_contracts.CorosActivitySummary]) -> None:
    """Collect activity identifiers from the text shape COROS documents.

    Args:
        text: Tool text content.
        records: Accumulator, mutated in place.
    """
    _table_records(text, records)
    matches = list(_SPORT_RECORDS_LABEL_RE.finditer(text))
    for index, match in enumerate(matches):
        block_start = max(0, match.start() - 300)
        block_end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), match.end() + 600)
        sport_match = _SPORT_RECORDS_SPORT_RE.search(text[block_start:block_end])
        if sport_match is None:
            continue
        label_id = match.group(1).strip()
        if not label_id or label_id.lower() == "null":
            continue
        records.append(
            coros_contracts.CorosActivitySummary(
                label_id=label_id,
                sport_type=int(sport_match.group(1)),
            )
        )


def parse_sport_records(result: coros_mcp_client.MCPToolResult) -> list[coros_contracts.CorosActivitySummary]:
    """Parse ``querySportRecords`` into activity summaries.

    COROS returns a human-readable text list; some gateway versions also include
    JSON or structured content. Both shapes are accepted, and the numeric
    ``sportType`` is kept because later tools require it.

    Args:
        result: Tool result.

    Returns:
        The summaries, deduplicated by activity id.

    Raises:
        coros_mcp_client.CorosMCPProtocolError: When a non-empty response has no
            recognizable activity record.
    """
    records: list[coros_contracts.CorosActivitySummary] = []
    text_chunks: list[str] = []
    for item in result.content:
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            text_chunks.append(item["text"])
    if result.structured_content:
        _structured_records(result.structured_content, records)
    for text in text_chunks:
        stripped = text.strip()
        if stripped.startswith(("[", "{")):
            try:
                _structured_records(json.loads(stripped), records)
            except ValueError:
                _text_records(text, records)
        else:
            _text_records(text, records)

    deduplicated: dict[str, coros_contracts.CorosActivitySummary] = {}
    for record in records:
        deduplicated.setdefault(record.label_id, record)
    summaries = list(deduplicated.values())

    if not summaries and text_chunks:
        combined = "\n".join(text_chunks).lower()
        if ("no " in combined and ("record" in combined or "activit" in combined)) or re.search(
            r"\b0\s+records?\b", combined
        ):
            return []
        if combined.strip():
            raise coros_mcp_client.CorosMCPProtocolError("COROS activity list has an unknown shape")
    return summaries


def _query_records(
    client: coros_mcp_client.CorosMCPClient,
    start_date: date,
    end_date: date,
) -> list[coros_contracts.CorosActivitySummary]:
    """Query one window, splitting it when COROS returns a full page.

    Args:
        client: Authenticated MCP client.
        start_date: Inclusive first date.
        end_date: Inclusive last date.

    Returns:
        The summaries, deduplicated.
    """
    result = client.call_tool(
        coros_constants.TOOL_QUERY_ACTIVITIES,
        {
            "startDate": start_date.strftime(coros_constants.COROS_DATE_FORMAT),
            "endDate": end_date.strftime(coros_constants.COROS_DATE_FORMAT),
            "limit": coros_constants.SPORT_RECORDS_PAGE_SIZE,
        },
    )
    summaries = parse_sport_records(result)
    if len(summaries) < coros_constants.SPORT_RECORDS_PAGE_SIZE or start_date >= end_date:
        return summaries
    midpoint = start_date + (end_date - start_date) / 2
    first_half = _query_records(client, start_date, midpoint)
    second_half = _query_records(client, midpoint + timedelta(days=1), end_date)
    return first_half + second_half


def fetch_activity_summaries(
    client: coros_mcp_client.CorosMCPClient,
    start_date: datetime,
    end_date: datetime,
) -> list[coros_contracts.CorosActivitySummary]:
    """Fetch every activity summary in a window.

    Args:
        client: Authenticated MCP client.
        start_date: Inclusive start.
        end_date: Inclusive end.

    Returns:
        The summaries, deduplicated.
    """
    records: list[coros_contracts.CorosActivitySummary] = []
    # COROS dates use the account timezone, while the sync window is UTC. One
    # day of padding on each side prevents an activity near local midnight from
    # falling outside the requested dates; deduplication makes the overlap free.
    query_start = start_date.date() - timedelta(days=1)
    query_end = end_date.date() + timedelta(days=1)
    for chunk_start, chunk_end in _date_chunks(query_start, query_end):
        records.extend(_query_records(client, chunk_start, chunk_end))
    deduplicated = {record.label_id: record for record in records}
    return list(deduplicated.values())


def _url_is_allowed(url: str) -> bool:
    """Return whether a FIT download URL is HTTPS and not private.

    Args:
        url: Candidate URL.

    Returns:
        True when the URL may be fetched.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    return core_network.url_rejection_reason(url, purpose="coros_fit_download") is None


def _download_url(url: str) -> bytes | None:
    """Download a pre-signed FIT URL with redirect and size checks.

    Args:
        url: Candidate URL.

    Returns:
        The file bytes, or None when the URL no longer serves a file.

    Raises:
        coros_mcp_client.CorosMCPTransientError: On retryable network failures.
        coros_mcp_client.CorosMCPProtocolError: On an unsafe or oversized file.
    """
    current = url
    with httpx2.Client(timeout=60.0, follow_redirects=False) as client:
        for _redirect in range(_MAX_REDIRECTS + 1):
            if not _url_is_allowed(current):
                raise coros_mcp_client.CorosMCPProtocolError("COROS returned an unsafe FIT URL")
            try:
                with client.stream("GET", current) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current = urljoin(current, location)
                        continue
                    if response.status_code in (404, 410):
                        return None
                    if response.status_code != 200:
                        raise coros_mcp_client.CorosMCPTransientError("COROS FIT download failed")
                    length = response.headers.get("content-length")
                    try:
                        declared_length = int(length) if length is not None else 0
                    except ValueError:
                        declared_length = 0
                    if declared_length > coros_constants.MAX_FIT_BYTES:
                        raise coros_mcp_client.CorosMCPProtocolError("COROS FIT file is too large")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > coros_constants.MAX_FIT_BYTES:
                            raise coros_mcp_client.CorosMCPProtocolError("COROS FIT file is too large")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except (httpx2.TimeoutException, httpx2.RequestError) as err:
                raise coros_mcp_client.CorosMCPTransientError("COROS FIT download failed") from err
    raise coros_mcp_client.CorosMCPProtocolError("COROS FIT URL redirected too many times")


def _download_fit(
    client: coros_mcp_client.CorosMCPClient,
    summary: coros_contracts.CorosActivitySummary,
) -> bytes | None:
    """Download one activity's FIT file through the MCP tools.

    Args:
        client: Authenticated MCP client.
        summary: Activity identifier and sport code.

    Returns:
        The FIT bytes, or None when COROS has no file for the activity.

    Raises:
        coros_mcp_client.CorosMCPError: On transport or protocol failures.
    """
    result = client.call_tool(
        coros_constants.TOOL_DOWNLOAD_FIT,
        {"labelId": summary.label_id, "sportType": summary.sport_type},
    )
    payload = coros_mcp_client.extract_binary_payload(result)
    if payload is not None:
        return payload

    urls = coros_mcp_client.extract_urls(result)
    if urls:
        return _download_url(urls[0])

    # Some clients cannot receive binary resources; ask for links explicitly.
    result = client.call_tool(
        coros_constants.TOOL_FIT_DOWNLOAD_URLS,
        {"labelId": summary.label_id, "sportType": summary.sport_type},
    )
    urls = coros_mcp_client.extract_urls(result)
    if urls:
        return _download_url(urls[0])
    return None


def _ingest_fit(
    user_id: uuid.UUID,
    label_id: str,
    fit_bytes: bytes,
) -> list[activity_schema.ActivityRead]:
    """Validate, parse and store one FIT file.

    Args:
        user_id: Owning user.
        label_id: COROS activity identifier.
        fit_bytes: Downloaded FIT payload.

    Returns:
        The stored activities; empty when the file was rejected.
    """
    with tempfile.TemporaryDirectory(prefix="coros-activity-") as work_dir:
        try:
            path = core_file_uploads.save_validated_bytes_sync(
                fit_bytes,
                kind=core_file_uploads.UploadKind.ACTIVITY,
                upload_dir=work_dir,
                filename="coros.fit",
            )
        except core_exceptions.DomainError as err:
            logger.warning(
                "COROS FIT file failed validation",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, coros_activity_id=label_id),
            )
            return []
        with SessionLocal() as db:
            created = activity_ingestion_integration.ingest_activity_file(
                user_id=user_id,
                file_path=path,
                db=db,
                source=activity_ingestion_integration.CorosSource(activity_id=label_id),
            )
        return created or []


def _already_stored(user_id: uuid.UUID, label_id: str) -> bool:
    """Return whether an activity was already imported.

    Args:
        user_id: Owning user.
        label_id: COROS activity identifier.

    Returns:
        True when the activity row exists.
    """
    with SessionLocal() as db:
        return activity_integration.get_activity_by_coros_id(label_id, user_id, db) is not None


def _already_skipped(user_id: uuid.UUID, label_id: str) -> bool:
    """Return whether an activity is marked as having no usable FIT file.

    Args:
        user_id: Owning user.
        label_id: COROS activity identifier.

    Returns:
        True when the activity should not be requested again.
    """
    with SessionLocal() as db:
        return coros_crud.is_activity_skipped(user_id, label_id, db)


def _mark_skipped(user_id: uuid.UUID, label_id: str, reason: str) -> None:
    """Record a permanent skip for an activity.

    Args:
        user_id: Owning user.
        label_id: COROS activity identifier.
        reason: Why the activity was skipped.
    """
    with SessionLocal() as db:
        coros_crud.mark_activity_skipped(user_id, label_id, reason, db)
        db.commit()
        logger.debug(
            "COROS activity marked skipped",
            extra=core_logger.context(user_id=user_id, coros_activity_id=label_id),
        )


def _sync_locked(
    user_id: uuid.UUID, start_date: datetime, end_date: datetime
) -> list[activity_schema.ActivityRead] | None:
    """Run one sync while the caller holds the per-user lock.

    Args:
        user_id: Owning user.
        start_date: Inclusive start.
        end_date: Inclusive end.

    Returns:
        The stored activities, or None when nothing was stored.
    """
    stored: list[activity_schema.ActivityRead] = []
    quota_exhausted = False
    try:
        connection = coros_service.get_valid_connection(user_id)
        with coros_mcp_client.CorosMCPClient(
            connection.mcp_url or coros_constants.MCP_URL,
            connection.access_token or "",
        ) as client:
            tools = client.list_tools()
            available = {tool["name"] for tool in tools if isinstance(tool.get("name"), str)}
            missing = sorted(coros_constants.REQUIRED_TOOLS - available)
            if missing:
                raise coros_mcp_client.CorosToolUnavailableError(", ".join(missing))
            summaries = fetch_activity_summaries(client, start_date, end_date)

            def process(summary: coros_contracts.CorosActivitySummary) -> list[activity_schema.ActivityRead]:
                """Process one summary, returning what it stored."""
                nonlocal quota_exhausted
                if _already_stored(user_id, summary.label_id) or _already_skipped(user_id, summary.label_id):
                    return []
                if not coros_service.reserve_fit_download(user_id):
                    quota_exhausted = True
                    logger.warning(
                        "COROS daily FIT download quota reached",
                        extra=core_logger.context(user_id=user_id),
                    )
                    raise activity_ingestion_contracts.WindowStoppedError()
                try:
                    fit_bytes = _download_fit(client, summary)
                except coros_mcp_client.CorosMCPToolError as err:
                    logger.warning(
                        "COROS FIT tool failed for one activity",
                        extra=core_logger.context(user_id=user_id, coros_activity_id=summary.label_id),
                        exc_info=err,
                    )
                    return []
                if fit_bytes is None:
                    _mark_skipped(user_id, summary.label_id, "no_file")
                    logger.debug(
                        "COROS activity has no FIT file; marked skipped",
                        extra=core_logger.context(user_id=user_id, coros_activity_id=summary.label_id),
                    )
                    return []
                created = _ingest_fit(user_id, summary.label_id, fit_bytes)
                if not created:
                    _mark_skipped(user_id, summary.label_id, "invalid_file")
                    logger.warning(
                        "COROS FIT file produced no activity",
                        extra=core_logger.context(user_id=user_id, coros_activity_id=summary.label_id),
                    )
                    return []
                return created

            results = activity_ingestion_integration.run_provider_window(
                summaries,
                process,
                provider=coros_constants.PROVIDER_NAME,
                user_id=user_id,
                describe=lambda summary: {"coros_activity_id": summary.label_id},
                propagate=(
                    coros_mcp_client.CorosMCPAuthenticationError,
                    coros_mcp_client.CorosMCPRateLimitError,
                    coros_mcp_client.CorosToolUnavailableError,
                    coros_mcp_client.CorosMCPProtocolError,
                    coros_mcp_client.CorosMCPTransientError,
                    coros_oauth.CorosTransientError,
                    coros_oauth.CorosAuthenticationError,
                ),
            )
            stored = [activity for result in results for activity in result]
    except coros_mcp_client.CorosMCPAuthenticationError:
        coros_service.mark_sync_error(user_id, coros_constants.SyncErrorCode.AUTHORIZATION_EXPIRED)
        logger.warning(
            "COROS access token rejected; account needs reconnecting", extra=core_logger.context(user_id=user_id)
        )
        return None
    except coros_mcp_client.CorosMCPRateLimitError:
        coros_service.mark_sync_error(user_id, coros_constants.SyncErrorCode.RATE_LIMITED)
        logger.warning("COROS rate limit reached", extra=core_logger.context(user_id=user_id))
        return None
    except coros_mcp_client.CorosToolUnavailableError as err:
        coros_service.mark_sync_error(user_id, coros_constants.SyncErrorCode.TOOLS_UNAVAILABLE)
        logger.error(
            "COROS MCP is missing a required tool",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
        return None
    except coros_mcp_client.CorosMCPToolError as err:
        coros_service.mark_sync_error(user_id, coros_constants.SyncErrorCode.PROTOCOL_ERROR)
        logger.error(
            "COROS MCP rejected a sync tool call",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
        return None
    except coros_mcp_client.CorosMCPProtocolError as err:
        coros_service.mark_sync_error(user_id, coros_constants.SyncErrorCode.PROTOCOL_ERROR)
        logger.error(
            "COROS MCP returned an unusable response", exc_info=err, extra=core_logger.context(user_id=user_id)
        )
        return None
    except (coros_mcp_client.CorosMCPTransientError, coros_oauth.CorosTransientError) as err:
        coros_service.mark_sync_error(user_id, coros_constants.SyncErrorCode.NETWORK_ERROR)
        logger.error("COROS sync hit a transient failure", exc_info=err, extra=core_logger.context(user_id=user_id))
        raise
    except coros_oauth.CorosAuthenticationError as err:
        coros_service.mark_sync_error(user_id, coros_constants.SyncErrorCode.AUTHORIZATION_EXPIRED)
        logger.warning(
            "COROS authorization cannot be refreshed; account needs reconnecting",
            extra=core_logger.context(user_id=user_id),
        )
        logger.debug("COROS authentication failure", exc_info=err)
        return None
    except Exception as err:
        coros_service.mark_sync_error(user_id, coros_constants.SyncErrorCode.PROCESSING_ERROR)
        logger.error("COROS sync failed unexpectedly", exc_info=err, extra=core_logger.context(user_id=user_id))
        raise

    if quota_exhausted:
        coros_service.mark_sync_error(user_id, coros_constants.SyncErrorCode.QUOTA_EXHAUSTED)
    else:
        coros_service.mark_sync_success(user_id, len(stored))
    logger.info(
        "COROS sync finished",
        extra=core_logger.context(user_id=user_id, activity_count=len(stored), quota_exhausted=quota_exhausted),
    )
    return stored or None


def get_user_coros_activities_by_dates(
    platform: Platform,
    start_date: datetime,
    end_date: datetime,
    user_id: uuid.UUID,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch and store a user's COROS activities in a window.

    Runs on a worker thread. A per-user platform lock prevents a manual and a
    scheduled sync from downloading the same files concurrently. No database
    session is held across an MCP or download call.

    Args:
        platform: The platform providers, resolved by the caller.
        start_date: Inclusive start.
        end_date: Inclusive end.
        user_id: Owning user.

    Returns:
        The stored activities, or None when COROS is not linked or nothing new
        arrived.
    """
    guard_key = f"coros:sync:{user_id}"
    guard_acquired = False
    try:
        guard_acquired = platform.state.set_if_absent(
            guard_key,
            b"1",
            ttl_seconds=coros_constants.SYNC_GUARD_TTL_SECONDS,
        )
        if not guard_acquired:
            logger.debug(
                "COROS sync already running for this user; skipping",
                extra=core_logger.context(user_id=user_id),
            )
            return None
    except platform_providers.StateBackendUnavailableError as err:
        # The shared state is an optimisation for the local lock below; a
        # temporary state outage must not block the sync entirely.
        logger.warning("Could not set the COROS sync guard", exc_info=err, extra=core_logger.context(user_id=user_id))

    try:
        with platform.lock.try_acquire(guard_key) as acquired:
            if not acquired:
                logger.debug(
                    "COROS sync already running for this user; skipping",
                    extra=core_logger.context(user_id=user_id),
                )
                return None
            return _sync_locked(user_id, start_date, end_date)
    finally:
        if guard_acquired:
            try:
                platform.state.delete(guard_key)
            except platform_providers.StateBackendUnavailableError as err:
                logger.debug(
                    "Could not clear the COROS sync guard",
                    exc_info=err,
                    extra=core_logger.context(user_id=user_id),
                )
