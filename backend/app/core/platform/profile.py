"""Deployment profile and capability-topology resolution.

Pure module — no I/O and no infrastructure imports. It answers two questions
the rest of the platform substrate builds on:

- **How is this deployment shaped?** ``DeploymentProfile`` (``local`` /
  ``distributed`` / ``custom``) plus the configured number of web workers.
- **Does that shape require state shared across processes?**
  ``DeploymentTopology.requires_shared_state``.

It also classifies a storage URI as memory- or Redis-backed so callers can
check the effective wiring against the required shape. Keeping this logic free
of infrastructure imports lets ``core.config`` consume it during ``Settings``
construction without import cycles.
"""

from dataclasses import dataclass
from enum import StrEnum


class DeploymentProfile(StrEnum):
    """How an Endurain deployment is shaped.

    Attributes:
        LOCAL: Single process/node — in-memory state, local disk, in-process
            events. The default; requires no extra infrastructure.
        DISTRIBUTED: Multi-node — requires shared state (Redis), object storage,
            and cross-process coordination.
        CUSTOM: No profile defaults; every capability must be set explicitly.
    """

    LOCAL = "local"
    DISTRIBUTED = "distributed"
    CUSTOM = "custom"


class StateBackendKind(StrEnum):
    """Classification of a state storage URI.

    Attributes:
        MEMORY: Process-local memory (``memory://``).
        REDIS: Redis-backed (``redis://`` / ``rediss://`` / ``unix://``).
        UNKNOWN: Unrecognized or unset scheme.
    """

    MEMORY = "memory"
    REDIS = "redis"
    UNKNOWN = "unknown"


_MEMORY_SCHEMES = ("memory://",)
_REDIS_SCHEMES = ("redis://", "rediss://", "unix://")


def parse_profile(value: str | DeploymentProfile | None) -> DeploymentProfile:
    """Parse a raw profile value into a ``DeploymentProfile``.

    Args:
        value: Raw environment value, an existing profile, or ``None``.

    Returns:
        The parsed profile; ``DeploymentProfile.LOCAL`` when unset or empty.

    Raises:
        ValueError: When the value is a non-empty, unrecognized profile name.
            Raising (rather than defaulting) prevents a typo like
            ``distributd`` from silently running the ``local`` profile and
            disabling the shared-state fail-fast.
    """
    if isinstance(value, DeploymentProfile):
        return value
    if value is None:
        return DeploymentProfile.LOCAL
    normalized = value.strip().lower()
    if not normalized:
        return DeploymentProfile.LOCAL
    try:
        return DeploymentProfile(normalized)
    except ValueError as err:
        valid = ", ".join(profile.value for profile in DeploymentProfile)
        raise ValueError(f"Invalid DEPLOYMENT_PROFILE '{value}'. Valid values: {valid}.") from err


def classify_state_uri(storage_uri: str | None) -> StateBackendKind:
    """Classify a state storage URI as memory / redis / unknown.

    Args:
        storage_uri: A storage URI (e.g. ``memory://`` or ``redis://host:6379/0``).

    Returns:
        The matching ``StateBackendKind``; ``UNKNOWN`` when unset or unrecognized.
    """
    if storage_uri is None:
        return StateBackendKind.UNKNOWN
    normalized = storage_uri.strip().lower()
    if normalized.startswith(_MEMORY_SCHEMES):
        return StateBackendKind.MEMORY
    if normalized.startswith(_REDIS_SCHEMES):
        return StateBackendKind.REDIS
    return StateBackendKind.UNKNOWN


@dataclass(frozen=True)
class DeploymentTopology:
    """Resolved deployment shape.

    Attributes:
        profile: The deployment profile.
        web_workers: Number of web-server worker processes (always >= 1).
    """

    profile: DeploymentProfile
    web_workers: int

    @property
    def requires_shared_state(self) -> bool:
        """Whether ephemeral state must be shared across processes.

        True for the ``distributed`` profile or any multi-worker deployment,
        because process-local memory cannot be shared between workers/replicas.
        """
        return self.profile is DeploymentProfile.DISTRIBUTED or self.web_workers > 1


def resolve_topology(profile: DeploymentProfile, web_workers: int) -> DeploymentTopology:
    """Resolve the deployment topology, clamping ``web_workers`` to >= 1.

    Args:
        profile: The deployment profile.
        web_workers: Configured worker count.

    Returns:
        The resolved ``DeploymentTopology``.
    """
    return DeploymentTopology(profile=profile, web_workers=max(1, web_workers))
