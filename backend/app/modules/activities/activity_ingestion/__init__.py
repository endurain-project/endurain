"""Activity ingestion — the parsing/provider boundary for the activities module.

This package owns *all* knowledge of source formats (``.gpx`` / ``.tcx`` / ``.fit`` /
``.gz``) and provider bulk-import glue (Strava). Its layers are:

* :mod:`sources` — what a file came from (upload / Garmin / bulk import), and the
  metadata that source carries.
* :mod:`pipeline` — the one shared path: validate, parse, enrich, store, retain.
* :mod:`upload_entry` / :mod:`bulk_entry` — the two entry points, which differ
  only in how the file arrives and what happens when it fails.
* :mod:`enrichment` — re-attaches owner privacy defaults, gear and provider ids
  to an activity the (pure) parsers produced.

Parsing itself lives in :mod:`~modules.activities.activity_file_import`, which
hands back the canonical
:class:`~modules.activities.activity.contracts.ParsedFile`; this package persists
it through
:func:`modules.activities.activity.ingestion_service.store_parsed_activity`.

The activities core (``activity/``) stays parser-agnostic: it never imports a file parser
or the Strava bulk-import utilities. That boundary is enforced structurally by the
``activities-parsing-boundary`` import-linter contract.
"""
