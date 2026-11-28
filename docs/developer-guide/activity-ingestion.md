# Activity ingestion

This page describes how a file or a provider sync becomes stored activities. The code lives in `backend/app/modules/activities/`:

- `activity_ingestion/` orchestrates the entry points and the shared pipeline.
- `activity_file_import/` turns a file into activities (`.gpx`, `.tcx`, `.fit`): a decoder per format reads the file into a `Recording` (sessions with sample columns, laps and the device summary, no math), and one shared `assembly` builds an activity from each session, using the device's own totals and computing what the file leaves out. The pipeline decompresses a `.gz` before parsing.
- `activity/` is the activities core. It never imports a parser or a provider.

Activities imported before file rows existed have no `file_id`; their file is still read and deleted by activity id (`processed/{activity id}`) until it is adopted into a row.

Three import-linter contracts enforce that split: `activities-provider-agnostic` (the activities module imports no provider), `activities-parsing-boundary` (the core imports no parser) and `ingestion-pipeline-format-agnostic` (the pipeline imports no parser directly).

## One pipeline, three entry points

Upload, the Garmin Connect sync and bulk import differ only in how the file arrives and what happens on failure. They all call the same file pipeline. The Strava sync has no file: it builds the parsed activity from the API response and enters at the store step (`store_parsed_activity`).

```mermaid
flowchart LR
    U[Upload] --> V
    P[Provider sync] --> V
    B[Bulk import batch] --> V
    V[Validate and decompress] --> PA[Parse]
    PA --> E[Enrich]
    E --> R{Source rule}
    R -- skip --> X[Not imported]
    R -- import --> RET[Retain source file]
    RET --> S[Match the source and store]
```

On failure the entry points differ: an upload cleans up and re-raises, a Garmin Connect sync logs a file the pipeline refuses and moves on (a database or storage outage is raised, so the refresh job retries the window), and a bulk import counts the file as failed and keeps its bytes (an outage is raised, so the batch resumes from its cursor).

On the local profile with one web worker the in-process pool is the only place a job runs, so startup submits every open upload and bulk import again (`resume_orphaned_local_jobs`). Re-running is safe because uploads and bulk-import members are deduplicated by content and a bulk import resumes after its cursor. A job with no staged blob, such as a folder import that was still being packed, is failed.

## What happens to a parsed activity

Decoding and assembly are pure functions. They return a canonical `ParsedFile` and know nothing about the database, privacy settings, gear or providers. The pipeline then applies these steps to each activity in the file:

1. **Enrich:** re-attach the owner's privacy defaults, gear and provider ids (`enrichment_service`).
2. **Source rules (bulk imports only):** the source's `should_import` hook decides whether to keep an activity, for example to skip duplicate listings in a Strava export. Then `apply_metadata` applies the manifest's name, description and gear.
3. **Match the source:** `store_parsed_activity` identifies the activity by one source, in this order of precedence, and skips the activity if the owner already holds that source.

    | Source of the activity | Stored as | Identity |
    | --- | --- | --- |
    | Strava activity id | `strava` source | The id |
    | Garmin activity id | `garmin` source | The id and the recording's start (a multi-activity `.fit` shares one Garmin id); the id alone for a multisport parent |
    | File content | `file` source | The file's SHA-256 and the recording's start; the hash alone for a multisport parent |
    | None of these | No source | The activity is stored without one; if its start time matches an existing activity, it is stored hidden, with a notification |

    The activity's `activity_sources` rows hold these identities, in the `activity` module next to the activity row. A start is kept in whole seconds, and a Strava activity has none. A file source copies the file's hash and does not reference `activity_files`: the retained file is deleted with its last activity, and the source must outlive it. Two unique indexes, one on `(user_id, kind, provider_id, session_start)` and one on `(user_id, file_sha256, session_start)`, settle concurrent imports of the same activity. The loser rolls back and returns the winner. `precedence` records how far the source's data is trusted (a device file 2, a TCX or GPX file 1, the Strava API 0).

    A Garmin source carries the id only and a file source the hash only, so every row has exactly one identity. The activity's `strava_activity_id` and `garminconnect_activity_id` are read from its sources; the columns of the same names are written and never read, and `dedup_key` is no longer written or read. A leg of a multisport activity keeps the source of its own session, as its key was before sources existed.

    An activity that has a Strava source and no other is live Strava data, which only its owner may see. An activity a file also recorded is not.
4. **Persist components:** the activity row and its children (laps, sets, streams, workout steps and so on) are staged through contributors registered in `contributor_registry`. A parsed component with no registered contributor fails the import instead of being dropped silently.
5. **Retain the source file:** before the first activity of a file is stored, the pipeline stages the original file as an `activity_files` row (`pending`) in its own short transaction and writes the blob with no session open. The activity is stored with that row's id (`activities.file_id`; the activities core treats it as an opaque id and never imports `activity_file_storage`), and the same transaction marks the row `attached`. A user has one live row per SHA-256, so uploading bytes the user already has, or a multi-activity `.fit`, shares the row instead of writing another copy. A file that stores no activity (a duplicate, a skipped bulk-import member, an empty file) releases the row this import created. A crash between the blob and the activity leaves a `pending` row, which the next import of the same bytes takes over and the daily sweep removes after a day.
6. **Publish `activity.created`:** staged in the same transaction as the rows. The pipeline commits once per activity, so a later failure does not undo earlier activities.

A FIT file whose `activity` message marks it multisport (`auto_multi_sport`) is the exception: the parser returns a multisport parent with the sessions as its legs, and `store_parsed_group` stages the parent and every leg in one transaction, committed once. The legs copy the parent's privacy, only the parent runs the same-start duplicate check, the parent holds the whole file's source and each leg its session's, only the parent references the retained file (the legs have no `file_id`), and the pipeline returns the parent alone. A Garmin multisport activity is listed once, so the sync reads its legs' Garmin ids and each leg's gear, resolves it to local gear and passes it as `GarminSource.leg_gear`; leg *i* takes entry *i* when the counts match, otherwise no leg takes Garmin gear (logged) and each falls back to its default. The parent never takes gear. A file whose legs were stored on their own before groups existed is left as it is.

```mermaid
sequenceDiagram
    participant Pipe as Pipeline
    participant Core as Activities core
    participant DB as Database
    participant Bus as Event system
    Pipe->>Core: store_parsed_activity(parsed)
    Core->>DB: look up the source
    alt already stored
        Core-->>Pipe: existing activity, nothing staged
    else new
        Core->>DB: stage activity and components
        Core->>Bus: stage activity.created
        Pipe->>DB: commit
        Bus-->>Bus: deliver after commit
    end
```

## Derived work

Nothing in the ingestion path knows what consumes `activity.created`. Independent subscribers react to it:

- map thumbnail generation (`activity_thumbnail`)
- reverse geocoding (`activity_geocoding`)
- notifications (`notifications`)

Thumbnails and geocoding also have a scheduled backfill that repairs missed events; notifications are transient and have none. How delivery works, locally and distributed, is covered in [Scaling and background jobs](../getting-started/scaling-and-background-jobs.md#how-events-are-delivered).

## Adding to the pipeline

- **A new file format:** write a decoder that returns a `Recording` and register it for its extension in `activity_file_import/parser_registry.py`; `assembly` and the adapter produce the canonical `ParsedFile`, with no database or provider coupling.
- **A new component stored with each activity:** register an activity-ingestion contributor in `contributor_registry`. File-scoped reference data uses a file-ingestion contributor.
- **A new provider export with its own rules:** subclass `BulkImportSource` and override `metadata_for`, `should_import`, `apply_metadata` or `import_side_artifacts` as needed; the Strava export overrides `metadata_for`, `should_import` and `import_side_artifacts`. Do not branch on the provider inside the pipeline.
