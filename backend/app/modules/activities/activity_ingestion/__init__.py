"""Activity ingestion — the parsing/provider boundary for the activities module.

This package owns *all* knowledge of source formats (``.gpx`` / ``.tcx`` / ``.fit`` /
``.gz``) and provider bulk-import glue (Strava). It parses uploaded and provider files,
adapts them into the canonical :class:`~modules.activities.activity.schema.ParsedActivity`
contract via :mod:`~modules.activities.activity_ingestion.file_adapter`, and persists them
through :func:`modules.activities.activity.ingestion_service.store_parsed_activity`.

The activities core (``activity/``) stays parser-agnostic: it never imports a file parser
or the Strava bulk-import utilities. That boundary is enforced structurally by the
``activities-parsing-boundary`` import-linter contract.
"""
