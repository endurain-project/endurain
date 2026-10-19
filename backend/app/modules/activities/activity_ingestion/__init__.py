"""Activity ingestion — the parsing/provider boundary for the activities module.

This package orchestrates how a file becomes activities: upload, bulk-import and
provider-sync entry points, the shared pipeline, enrichment and the provider seams. Format parsing
(``.gpx`` / ``.tcx`` / ``.fit`` / ``.gz``) lives in ``activity_file_import``. Its layers are:

* :mod:`contracts` — what a file came from (upload / Garmin / bulk import), and the
  metadata that source carries.
* :mod:`pipeline_service` — the one shared path: validate, parse, enrich, store, retain.
* :mod:`upload_entry_service` / :mod:`provider_entry_service` — the entry points for one
  file, which differ only in how it arrives and what happens when it fails.
* :mod:`bulk_import_service` — a bulk import: one job over one staged archive, worked
  through in short batches that resume from a cursor and queue their own continuation.
* :mod:`enrichment_service` — re-attaches owner privacy defaults, gear and provider ids
  to an activity the (pure) parsers produced.

Parsing itself lives in :mod:`~modules.activities.activity_file_import`, which
hands back the canonical
:class:`~modules.activities.activity.contracts.ParsedFile`; this package persists
it through
:func:`modules.activities.activity.ingestion_service.store_parsed_activity`.

The activities core (``activity/``) stays parser-agnostic: it never imports a file parser
or the Strava export layout, which Strava registers as a bulk-import format. That boundary is enforced structurally by the
``activities-parsing-boundary`` import-linter contract.
"""
