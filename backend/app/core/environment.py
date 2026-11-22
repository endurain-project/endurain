"""The deployment environments ``ENVIRONMENT`` may name, and which of them serve real traffic.

Kept apart from :mod:`core.config` so pure layers can ask the question without reading settings.
"""

from typing import Literal

Environment = Literal["production", "demo", "development"]

#: Environments that serve real traffic: HSTS, ``Secure`` cookies and JSON logging apply to them.
DEPLOYED_ENVIRONMENTS: frozenset[str] = frozenset({"production", "demo"})


def is_deployed_environment(environment: str) -> bool:
    """Tell whether an environment name is one that serves real traffic.

    Args:
        environment: The ``ENVIRONMENT`` value.

    Returns:
        True for ``production`` and ``demo``.
    """
    return environment in DEPLOYED_ENVIRONMENTS
