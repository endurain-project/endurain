"""Export the backend OpenAPI schema offline.

Builds a minimal FastAPI app that mounts only the API router and dumps its
OpenAPI document to stdout (or a file). It deliberately avoids
``main.create_app()`` so it performs no filesystem, migration, or scheduler
side effects and needs no live database — making it safe to run in CI to
generate the frontend's typed API client.

Usage:
    python scripts/export_openapi.py            # write JSON to stdout
    python scripts/export_openapi.py out.json   # write JSON to a file

Run from the ``backend/`` directory (or with ``backend/app`` on PYTHONPATH).
"""

import json
import os
import sys
from pathlib import Path

# Expose the app packages (imports are top-level, e.g. ``api``) without
# relying on the caller's PYTHONPATH.
_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

# Import-time settings/secrets are validated when app modules load. Their
# values never affect the generated schema, so provide inert defaults to keep
# the export hermetic (no real secrets, no .env required).
os.environ.setdefault("DB_PASSWORD", "openapi-export-placeholder")
os.environ.setdefault("SECRET_KEY", "openapi-export-placeholder")

from fastapi import FastAPI  # noqa: E402

import core.config as core_config  # noqa: E402
from api import router as api_router  # noqa: E402


def build_openapi() -> dict:
    """Build the OpenAPI document from the API router alone.

    Returns:
        The OpenAPI schema as a plain dict, identical in paths and component
        schemas to the production app (middleware and static mounts do not
        contribute to the schema).
    """
    app = FastAPI(
        title="Endurain",
        summary="Endurain API for the Endurain app",
        version=core_config.API_VERSION,
        license_info={
            "name": core_config.LICENSE_NAME,
            "identifier": core_config.LICENSE_IDENTIFIER,
            "url": core_config.LICENSE_URL,
        },
    )
    app.include_router(api_router)
    return app.openapi()


def main() -> None:
    """Write the OpenAPI document to a file argument or stdout."""
    spec = build_openapi()
    payload = json.dumps(spec, indent=2, sort_keys=True) + "\n"

    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
