"""Startup capability report and deployment-consistency checks.

Renders how each infrastructure capability (state, storage, events, lock,
clock) is wired for a human-readable startup log, and detects fatal
inconsistencies — a deployment that *requires* a shared backend but resolves
one to a process- or node-local implementation.

Two consistency rules are enforced (see the foundations plan §9.2):

- **Cross-process backends** — ephemeral *state* (rate-limit, auth-security,
  MFA, websocket tickets) and the *event* bus — must not resolve to
  process-local memory when the topology requires shared state (the
  ``distributed`` profile or more than one web worker); the stores/bus would
  diverge silently across processes. Both share the ``memory://`` / ``redis://``
  vocabulary and are validated by :func:`check_state_consistency`.
- **Cross-node storage** must not resolve to the local filesystem under the
  ``distributed`` profile, where replicas run on separate nodes with no shared
  disk. A multi-worker *local* deployment shares one host disk, so local
  storage stays valid there. Validated by :func:`check_storage_consistency`.
- **The coordination lock** must not resolve to the in-process ``noop`` lock
  whenever the deployment runs more than one process (the ``distributed``
  profile or any multi-worker deployment), or every process would run every
  scheduled job. Validated by :func:`check_lock_consistency`.

The *clock* is always the system clock, so its default is never a fatal choice
here.

Pure module — imports only ``infra.profile``. The actual logging is
performed by the caller (``main.startup_event``) so this stays side-effect free
and trivially testable.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from infra.profile import (
    DeploymentProfile,
    DeploymentTopology,
    StateBackendKind,
    classify_state_uri,
    resolve_topology,
)


@dataclass(frozen=True)
class StateSource:
    """A configured source of ephemeral state.

    Attributes:
        label: The setting name backing this state (e.g. ``STATE_URI``).
        uri: The effective storage URI.
        applies: Whether this source is active (e.g. rate limiting may be off).
    """

    label: str
    uri: str
    applies: bool = True

    @property
    def backend(self) -> StateBackendKind:
        """The classified backend for this source's URI."""
        return classify_state_uri(self.uri)


@dataclass(frozen=True)
class CapabilityRow:
    """One line of the capability report.

    Attributes:
        name: Capability name (state / storage / events / lock / clock).
        backend: The resolved backend (e.g. ``memory``, ``local``, ``system``).
        source: Where the value came from (setting name or ``profile default``).
    """

    name: str
    backend: str
    source: str


@dataclass(frozen=True)
class CapabilityReport:
    """A rendered snapshot of how each capability is wired at startup."""

    topology: DeploymentTopology
    rows: tuple[CapabilityRow, ...]

    def render(self) -> str:
        """Render the report as a multi-line, aligned string."""
        header = (
            f"Deployment profile: {self.topology.profile.value} "
            f"(WEB_WORKERS={self.topology.web_workers}, "
            f"requires_shared_state={self.topology.requires_shared_state})"
        )
        width = max((len(row.name) for row in self.rows), default=0)
        lines = [f"  {row.name.ljust(width)} -> {row.backend}  (source: {row.source})" for row in self.rows]
        return "\n".join([header, *lines])


def build_capability_report(
    *,
    profile: DeploymentProfile,
    web_workers: int,
    primary_state: StateSource,
    storage_backend: str,
    storage_source: str,
    events_backend: str,
    events_source: str,
    lock_backend: str,
    lock_source: str,
) -> CapabilityReport:
    """Build the observational capability report for startup logging.

    Args:
        profile: The deployment profile.
        web_workers: Configured worker count.
        primary_state: The state source shown on the ``state`` row (the resolved
            auth-security store — the most security-critical shared state).
        storage_backend: The resolved blob-storage backend (``local`` or ``s3``).
        storage_source: The setting backing blob storage today.
        events_backend: The resolved event-bus backend (``in-process`` or ``redis``).
        events_source: The setting backing the event bus today.
        lock_backend: The resolved coordination-lock backend (``none`` or ``pg``).
        lock_source: The setting backing the coordination lock today.

    Returns:
        A ``CapabilityReport`` reflecting today's effective wiring. Only the
        clock is a static row.
    """
    topology = resolve_topology(profile, web_workers)
    rows = (
        CapabilityRow("state", primary_state.backend.value, primary_state.label),
        CapabilityRow("storage", storage_backend, storage_source),
        CapabilityRow("events", events_backend, events_source),
        CapabilityRow("lock", lock_backend, lock_source),
        CapabilityRow("clock", "system", "profile default"),
    )
    return CapabilityReport(topology=topology, rows=rows)


def check_state_consistency(
    *,
    profile: DeploymentProfile,
    web_workers: int,
    environment: str,
    state_sources: Sequence[StateSource],
) -> list[str]:
    """Return fatal issues for cross-process backends (empty when consistent).

    A deployment that requires shared state (the ``distributed`` profile or more
    than one web worker) but resolves a cross-process backend to process-local
    memory is fatally misconfigured: ephemeral state (rate-limit counters, login
    lockout, pending-MFA) and the in-process event bus would silently diverge
    across processes. State stores and the event bus share the ``memory://`` /
    ``redis://`` vocabulary, so both are validated here.

    Args:
        profile: The deployment profile.
        web_workers: Configured worker count.
        environment: Runtime environment; ``development`` is never fatal.
        state_sources: The active cross-process backends to validate (the
            resolved state and event-bus URIs).

    Returns:
        A list of human-readable issue messages; empty when consistent. The
        caller (``core.config``) raises at ``Settings`` construction when
        non-empty, so misconfiguration is caught at boot.
    """
    if environment == "development":
        return []
    if profile is DeploymentProfile.CUSTOM:
        return []
    topology = resolve_topology(profile, web_workers)
    if not topology.requires_shared_state:
        return []
    issues: list[str] = []
    for source in state_sources:
        if not source.applies or source.backend is StateBackendKind.REDIS:
            continue
        reason = (
            "process-local memory" if source.backend is StateBackendKind.MEMORY else "an unrecognized storage scheme"
        )
        issues.append(
            f"{source.label} resolves to {reason}, but "
            f"DEPLOYMENT_PROFILE={profile.value} with WEB_WORKERS={topology.web_workers} "
            f"requires a backend shared across processes. Point it at Redis "
            f"(redis://...) or run a single worker under the local profile."
        )
    return issues


def check_storage_consistency(
    *,
    profile: DeploymentProfile,
    environment: str,
    storage_uri: str,
    storage_label: str,
) -> list[str]:
    """Return a fatal issue when distributed storage resolves to local disk.

    Under the ``distributed`` profile replicas run on separate nodes that do not
    share a filesystem, so blob storage (thumbnails, media) must be object
    storage. A multi-worker ``local`` deployment shares one host disk, so local
    storage stays valid there and is not flagged.

    Args:
        profile: The deployment profile.
        environment: Runtime environment; ``development`` is never fatal.
        storage_uri: The resolved blob-storage URI.
        storage_label: The setting backing blob storage (for the message).

    Returns:
        A single-item issue list when misconfigured; empty otherwise. The caller
        (``core.config``) raises at ``Settings`` construction when non-empty.
    """
    if environment == "development" or profile is not DeploymentProfile.DISTRIBUTED:
        return []
    if not storage_uri.strip().lower().startswith("local://"):
        return []
    return [
        f"{storage_label} resolves to the local filesystem, but "
        f"DEPLOYMENT_PROFILE={profile.value} runs replicas on separate nodes that do "
        f"not share a disk. Point it at object storage (s3://bucket/...)."
    ]


def check_lock_consistency(
    *,
    profile: DeploymentProfile,
    web_workers: int,
    environment: str,
    lock_uri: str,
    lock_label: str,
) -> list[str]:
    """Return a fatal issue when a multi-process deployment uses a no-op lock.

    The coordination lock makes scheduled/backfill jobs single-runner across
    processes. Whenever a deployment runs more than one process — the
    ``distributed`` profile or any multi-worker deployment
    (:attr:`DeploymentTopology.requires_shared_state`) — an in-process
    ``noop://`` lock coordinates nothing, so every process would run every
    interval job (Strava/Garmin sync, token sweeps, thumbnail backfill). The
    profile-aware default already resolves to ``postgres-advisory://`` in that
    case, so this only trips on an explicit ``LOCK_URI=noop://`` override. A
    single-process ``local`` deployment has nothing to coordinate, so ``noop``
    stays valid there.

    Args:
        profile: The deployment profile.
        web_workers: Configured worker count.
        environment: Runtime environment; ``development`` is never fatal.
        lock_uri: The resolved coordination-lock URI.
        lock_label: The setting backing the lock (for the message).

    Returns:
        A single-item issue list when misconfigured; empty otherwise. The caller
        (``core.config``) raises at ``Settings`` construction when non-empty.
    """
    if environment == "development" or profile is DeploymentProfile.CUSTOM:
        return []
    topology = resolve_topology(profile, web_workers)
    if not topology.requires_shared_state:
        return []
    if not lock_uri.strip().lower().startswith("noop://"):
        return []
    return [
        f"{lock_label} resolves to an in-process no-op lock, but "
        f"DEPLOYMENT_PROFILE={profile.value} with WEB_WORKERS={topology.web_workers} "
        f"runs multiple processes that would each run scheduled jobs. Point it at "
        f"the shared database lock (postgres-advisory://)."
    ]
