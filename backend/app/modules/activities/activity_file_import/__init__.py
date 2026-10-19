"""Pure parsers turning activity file bytes into the canonical parsed contract.

``.gpx`` / ``.tcx`` / ``.fit`` in, ``ParsedFile`` out. Pure by contract: no
database, no privacy settings, no gear lookup, no provider client, no HTTP —
which is what makes a parser testable with bytes alone. The domain context a
parsed activity needs (owner privacy defaults, gear, provider ids) is re-attached
afterwards by ``activity_ingestion.enrichment_service``, and the
``activity-file-import-purity`` import-linter contract keeps it that way.

Callers outside this package use :mod:`integration_service` (``get_parser``,
``supported_extensions``); the parser modules and ``registry`` are private to it.
Importing this package does not pull in a parser.
"""
