"""Core metadata and static fallback routes."""

from datetime import UTC, datetime, timedelta
from typing import Literal

import jasil.audit as jasil_audit
import jasil.settings as jasil_settings
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from jasil.providers import StateBackendUnavailableError
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

import core.config as core_config
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.utils as core_utils

logger = core_logger.get_logger(__name__)

# Define the API router
router = APIRouter()


class LicenseInfo(BaseModel):
    """
    API license metadata.

    Attributes:
        name: License display name.
        identifier: SPDX license identifier.
        url: Public license URL.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    identifier: str
    url: str


class AboutResponse(BaseModel):
    """
    API metadata returned by the about endpoint.

    Attributes:
        name: API display name.
        version: API version string.
        license: License metadata.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    license: LicenseInfo


@router.get(
    core_config.ROOT_PATH + "/about",
    response_model=AboutResponse,
)
async def about() -> AboutResponse:
    """
    Returns metadata information about the Endurain API.

    Returns:
        API name, version, and license details.
    """
    return AboutResponse(
        name="Endurain API",
        version=core_config.API_VERSION,
        license=LicenseInfo(
            name=core_config.LICENSE_NAME,
            identifier=core_config.LICENSE_IDENTIFIER,
            url=core_config.LICENSE_URL,
        ),
    )


class HealthResponse(BaseModel):
    """
    Health of the dependencies this process needs.

    Attributes:
        status: ``ok``, or ``degraded`` when the shared state backend is unreachable or the audit trail
            is unhealthy.
        state: Whether the shared state backend (rate limits, claims, tickets) answers.
        audit: Whether the audit trail is healthy: tomorrow's partition exists, the latest checkpoint is
            recent and no audit record failed to write recently.
    """

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded"]
    state: Literal["ok", "unavailable"]
    audit: Literal["ok", "degraded"]


#: Key the health probe reads. It is never written, so the probe leaves nothing in the backend.
_STATE_PROBE_KEY = "endurain:health:probe"


#: How old the latest sealed checkpoint, or how recent a failed refusal-row write, may be before the audit
#: trail counts as degraded.
_AUDIT_HEALTH_WINDOW = timedelta(hours=1)


def _audit_degraded_reason() -> str | None:
    """
    Find why the audit trail is unhealthy.

    A checkpoint that was never sealed is not flagged: no timestamp tells how long the instance has run,
    and maintenance records the partition and the checkpoint together, so a scheduler that never ran
    already shows as a missing partition.

    Returns:
        A fixed description of the first problem found, or ``None`` when the audit trail is healthy or
        disabled.
    """
    if not jasil_settings.get_settings().audit.enabled:
        return None
    try:
        audit_health = jasil_audit.get_audit_health()
    except Exception as err:
        return f"the audit health could not be read ({type(err).__name__})"
    now = datetime.now(UTC)
    furthest_partition_date = audit_health["furthest_partition_date"]
    if furthest_partition_date is None or furthest_partition_date < now.date() + timedelta(days=1):
        return "tomorrow's audit partition does not exist"
    last_checkpoint_at = audit_health["last_checkpoint_at"]
    if last_checkpoint_at is not None and now - last_checkpoint_at > _AUDIT_HEALTH_WINDOW:
        return "the latest audit checkpoint is older than an hour"
    last_failure_at = audit_health["last_failure_at"]
    if last_failure_at is not None and now - last_failure_at <= _AUDIT_HEALTH_WINDOW:
        return "an audit record failed to write within the last hour"
    return None


@router.get(core_config.ROOT_PATH + "/health", response_model=HealthResponse)
def health(db: core_dependencies.DbSession, state: core_dependencies.PlatformState) -> HealthResponse:
    """
    Liveness check that needs a database connection, and reports the shared state backend.

    Unlike ``/about``, this fails when the connection pool is exhausted or the
    database is unreachable, so orchestrators can detect a wedged instance. A state
    backend that does not answer does not fail it: the process still serves most
    routes (rate limits fall back to per-process counters), and restarting or
    de-routing replicas would not bring the backend back. It answers 200 with
    ``degraded`` so a monitor can alert on the body. An unhealthy audit trail does the same.

    Args:
        db: Database session.
        state: The platform state provider.

    Returns:
        ``ok`` when the database and the state backend answer and the audit trail is healthy,
        ``degraded`` when only the state backend or the audit trail is not.

    Raises:
        HTTPException: 503 when no connection can be obtained or the query fails.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable") from err
    state_ok = True
    try:
        state.get(_STATE_PROBE_KEY)
    except StateBackendUnavailableError as err:
        logger.warning("The shared state backend did not answer the health probe", exc_info=err)
        state_ok = False
    audit_reason = _audit_degraded_reason()
    if audit_reason is not None:
        logger.warning("The audit trail is degraded: %s", audit_reason)
    audit_ok = audit_reason is None
    return HealthResponse(
        status="ok" if state_ok and audit_ok else "degraded",
        state="ok" if state_ok else "unavailable",
        audit="ok" if audit_ok else "degraded",
    )


# NOTE: there is deliberately no ``/server_images/{img}``, ``/user_images/{user_img}``,
# ``/activity_media/{media}`` or ``/activity_thumbnails/{thumbnail}`` route here.
# All three serve private user data and are reachable only through their
# token-gated routes. A filename-addressed route beside them is a full bypass of
# that gate, which is what these used to be — and for user photos, stored as
# ``{user_id}.{ext}``, it enumerated the entire user base.


@router.get(
    "/{path:path}",
    include_in_schema=False,
    response_class=FileResponse,
)
def frontend_not_found(
    path: str,
) -> FileResponse:
    """
    Return the requested frontend asset or app index.

    Args:
        path (str): The requested resource path.

    Returns:
        Response: The frontend index file or the requested resource if found.

    Raises:
        NotFoundError: If the path is under the API prefix, since no API route matched it.
        HTTPException: If the requested resource is not found.
    """
    api_prefix = core_config.ROOT_PATH.strip("/")
    if path == api_prefix or path.startswith(f"{api_prefix}/"):
        raise core_exceptions.NotFoundError("Resource not found")

    if "." in path.split("/")[-1]:
        result = core_utils.return_frontend_index(path)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found",
            )
        return result

    result = core_utils.return_frontend_index("index.html")
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frontend index not found",
        )
    return result
