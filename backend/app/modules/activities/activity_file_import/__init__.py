"""Pure parsers turning activity file bytes into the canonical parsed contract.

``.gpx`` / ``.tcx`` / ``.fit`` in, ``ParsedFile`` out. Pure by contract: no
database, no privacy settings, no gear lookup, no provider client, no HTTP —
which is what makes a parser testable with bytes alone. The domain context a
parsed activity needs (owner privacy defaults, gear, provider ids) is re-attached
afterwards by ``activity_ingestion.enrichment``, and the
``activity-file-import-purity`` import-linter contract keeps it that way.

Importing this package does not pull in a parser: reach for the submodule you
need (``.registry``, ``.utils_gpx``, ``.utils_fit``, ``.utils_tcx``).
"""
