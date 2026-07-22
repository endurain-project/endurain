"""Domain event channel names owned by the activity-ingestion sub-domain."""

# Published once per file when a bulk import is initiated with durable jobs
# enabled; a durable subscriber (A9) imports each file as an independent,
# retryable, dead-letterable job. This channel is durable-delivery only — the
# route only publishes it when JOBS_ENABLED (so it always routes to the outbox →
# relay → per-file jobs), and falls back to the background threadpool otherwise,
# so no best-effort bus subscriber exists for it.
ACTIVITY_BULK_IMPORT_FILE = "activity.bulk_import_file"
