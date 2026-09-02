"""The file-role vocabulary from ``docs/developer-guide/module-structure.md``.

Filenames are part of the contract: a file named ``crud.py`` is treated as
persistence wherever it appears. The corollary is that the enforcement rules have
to agree on what a filename *means*, and they are spread across two test modules
(``tests/architecture/test_module_boundaries.py`` decides visibility,
``tests/test_logging_rule.py`` decides which log levels a layer may use). Stating
the vocabulary in each of them would be two copies of one definition, and a
divergence between them is exactly the silent exemption the rules exist to
prevent.

A stem *qualifies* its role rather than replacing it: ``summary_crud`` is a
``crud``, ``summary_router`` is a ``router``. Matching on the exact stem meant a
qualified name inherited nothing — ``summary_query`` opened a ``Session`` and
executed for the whole summaries feature while matching neither the ``crud``
rules (wrong stem) nor the ``query`` ones (wrong role).
"""

import pathlib

#: Every role, longest first so ``integration_service`` is not read as
#: ``service`` and ``public_router`` is not read as ``router``.
ROLES: tuple[str, ...] = (
    "contributor_registry",
    "subscriber_registry",
    "integration_service",
    "migration_service",
    "event_publishers",
    "scheduled_jobs",
    "model_registry",
    "public_router",
    "dependencies",
    "computation",
    "serializers",
    "subscribers",
    "constants",
    "contracts",
    "service",
    "schema",
    "router",
    "events",
    "models",
    "query",
    "crud",
)


def role_of(stem: str) -> str:
    """
    Return the role a file stem declares.

    Args:
        stem: The file stem, e.g. ``crud`` or ``summary_crud``.

    Returns:
        The matching role, or the stem itself when it names none — which leaves
        it package-private, the safe default.
    """
    for role in ROLES:
        if stem == role or stem.endswith(f"_{role}"):
            return role
    return stem


def files_with_role(roots: tuple[pathlib.Path, ...], role: str) -> list[pathlib.Path]:
    """
    Return every Python file under ``roots`` that plays the given role.

    Args:
        roots: The module roots to walk.
        role: The role to collect, e.g. ``crud``.

    Returns:
        The matching paths, deduplicated and sorted.
    """
    return sorted(
        {
            path
            for root in roots
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts and role_of(path.stem) == role
        }
    )
