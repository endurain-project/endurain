# Importing data

Endurain lets you upload single files from the web interface. To import many files at once there are two bulk options:

- *Generic bulk import* - activity files such as .fit, .tcx, .gpx and .gz.
- *Importing from a Strava bulk export* - activities, activity metadata (name, description, gear) and photos from a Strava export, plus bikes and shoes.

Each can be started two ways:

- **Upload a ZIP.** Works everywhere, including a hosted instance where you have no access to the server. The archive is limited to the upload size the server allows (500 MiB) and 20,000 files.
- **Import from your folder on the server.** For self-hosted installs, and for exports too large to upload. Put the files in your own folder on the server and start the import from the page. The files you put there are packed and staged first, and removed from the folder only once they are safely staged, so a failure leaves them where you left them.

Both start a background import and show its progress on the page (files imported, files failed, total). You can leave the page; the import continues. Only one bulk import runs per user at a time.

## Duplicate detection

Endurain checks every imported activity, whatever the source (upload, bulk import, Garmin Connect or Strava), so importing the same data twice is safe.

- **Same activity again:** an activity you already have is skipped and nothing new is created. It is recognised by its Strava or Garmin Connect activity id, or, for plain files, by the file's content plus the activity's start time. Re-running a bulk import, or uploading the same file twice, does not create duplicates. A multi-activity `.fit` file is handled per activity.
- **Same activity from another source:** a file that has no provider id cannot be matched to an activity that came from Garmin Connect or Strava. If its start time matches an existing activity, it is still stored but hidden, and you get a notification about the duplicate. You can unhide it from the activity's edit dialog (see [Sharing, privacy and followers](sharing-and-privacy.md)).

## Generic bulk import

Choose "Import" in the settings menu, then either upload a ZIP of activity files, or place them in your folder first:

- Folder: `data/activity_files/bulk_import/<your user id>/`

The folder is chosen by the account that starts the import, so each user only ever imports the files in their own folder. Files placed in another user's folder are never read.

Files with the extensions .fit, .tcx, .gpx and .gz are imported; other files are ignored and left alone. Folders inside the ZIP or the import folder are fine.

### Notes on the generic bulk import

.fit files are preferred. Strava and Garmin Connect's conversion of .fit to .gpx introduces additional data into the file, leading to minor variances such as extra meters of distance and elevation gain.

**There is currently no mechanism to undo or revert an import.** Back up your database before importing if you have any doubts about the process or whether duplicates exist.

A file that could not be imported does not stop the others: it is counted as failed, and its bytes are kept in the `bulk_import_errors` storage area under `<user id>/<import id>/<file name>`. A finished import with failed files still shows as completed, with the failure count.

Reverse geocoding services may rate limit large imports; locations that could not be resolved are filled in by a scheduled job later.

## Importing data from a Strava bulk export (BETA)

Strava lets you request a bulk export of your history from its website. The export is a ZIP with `activities.csv`, an `activities` folder of GPS files, and a `media` folder of photos. The import only works with English `.csv` files; if your Strava profile uses another language, switch it to English before exporting.

Recommended procedure:

1. Back up your database.
2. Import, or create, any gear that was present in Strava (see below). Activities are linked to gear by name, so the gear has to exist first.
3. Import activities and photos, ideally after a small test import.

### Gear (bikes and shoes)

In the settings "Import" page, choose "Import bikes" or "Import shoes" and upload the `bikes.csv` or `shoes.csv` from your export. The file needs a header row with `Bike Name`, `Bike Brand`, `Bike Model` (bikes) or `Shoe Name`, `Shoe Brand`, `Shoe Model` (shoes). Components are not imported, only the gear itself.

- Gear is screened for duplicates by nickname, case-insensitively and across bikes and shoes, so existing gear with the same nickname prevents the import of that item.
- All gear is imported as active.
- `+` characters are replaced with spaces and surrounding spaces are removed.
- Strava allows shoes with no name, Endurain does not: they are named "Unnamed shoe N".
- Gear that is already present because you linked Strava is not imported again.

### Activities and photos

Upload the Strava export ZIP as it came from Strava (with `activities.csv`, `activities/` and `media/` at its top level), or extract it into:

- Folder: `data/activity_files/strava_import/<your user id>/`

The import:

- reads each file in `activities/`,
- applies the name, description, activity type and gear listed in `activities.csv`,
- keeps the Strava activity id in a non-displayed field,
- attaches the photos listed for each activity from `media/` (images only, not videos).

To do a small test import, put only a few files into `activities/`, together with the full `activities.csv` and `media/`.

### Limitations

**There is no mechanism to undo an import.**

Large exports take a while: each file is parsed, enriched and stored, and the import works through them in batches. You can follow the count on the page.

Comments on media are not imported (Endurain does not have comments on media).

If you had unnamed shoes in Strava, the gear import renames them, so activities that refer to them by their Strava name are not linked. Edit `activities.csv` to use the new name before importing, using the format Strava writes: `{brand} {model} {name}`.

## Developer notes

While most of the import processes are documented over in the features / importing area, this document houses notes specifically targeted to developers.

### Upload validation

All multipart import uploads are validated through `backend.app.core.file_uploads` before they are parsed or persisted. Use `validate_upload(file, kind=UploadKind.ZIP)` for profile ZIP imports that are consumed in memory, and `save_validated_upload(file, kind=..., upload_dir=..., filename=...)` for uploads that are written to disk.

Activity uploads use server-generated filenames and `UploadKind.ACTIVITY` or `UploadKind.GZIP`; decompressed gzip payloads are re-validated as `UploadKind.ACTIVITY` before parsing. Validation failures are raised as `HTTPException` responses whose `detail` includes a human-readable `message` and, when provided by `safeuploads`, a machine-readable `code`.

### Bulk import

When items are imported either through a bulk import or Strava bulk import, the dictionary "import_info" is created for the activity to record information on the import.

The import_info dictionary should include at least the following fields:
* imported (boolean)
* import_source (str) - e.g., "Strava bulk import" or "Basic bulk import"
* strava_activity_id (int) - holds Strava's internal activity ID for Strava activities when imported from a bulk Strava import
* import_ISO_time (str) - an ISO formatted string holding the time of import.  This will be the time the entire import was triggered, and should be the same for all files of a single bulk import.

If this dictionary exists for an activity, then the file was imported with one of those two functions (after this routine was added, likely v0.18.0).  Checking the "imported" field of the import_info dict can double-check this.

These fields allow determination of when files were imported (to facilitate future creation of the ability to roll back an import), and also allow separation of imported Strava activities from Strava activities added via linking with Strava as a service.
