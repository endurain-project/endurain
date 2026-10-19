# Exporting and importing your data

You can download a copy of your data and restore it later, on the same server or on another one. This is useful for backups, for moving to a new instance, and for keeping your own archive.

Open **Settings → My profile** and find the **Your data** card. It has an **Export data** and an **Import data** button.

## Export

Export builds a ZIP archive named `user_<your id>_export.zip` and streams it to your browser. The archive contains:

- your profile, privacy settings, goals, default gear and integration settings
- gear and gear components
- activities with their laps, sets, streams, workout steps and other detail
- the original activity files and activity media
- weight records and health targets
- your profile photo

The archive does **not** include your password, MFA configuration, or other security settings. It also does not include your account's access level or status, so importing cannot be used to change them.

!!! note
    Large accounts take a while to export. If the server runs low on memory or the export takes too long, it stops with an error instead of producing a broken archive.

## Import

Choose **Import data** and select a `.zip` archive created by an export. The import:

- **adds** the data to your current account. It does not replace or delete what you already have.
- creates new gear and activities, and relinks activities to the imported gear.
- updates your profile fields, goals and privacy settings from the archive.
- finishes with a count of what was imported. An archive with nothing importable is rejected with an error.

Because an import cannot be undone, back up your database first if you are unsure. See [Updates and backups](../getting-started/operations.md).

### Limits

The server chooses limits from the memory available when the import starts, so a larger machine accepts bigger archives.

| Available memory | Maximum archive size | Maximum activities | Time limit |
| ---------------- | -------------------- | ------------------ | ---------- |
| More than 2 GB | 2000 MB | 20,000 | 2 hours |
| More than 1 GB | 1000 MB | 10,000 | 1 hour |
| 1 GB or less | 500 MB | 5,000 | 30 minutes |

An archive over the limit, a corrupt ZIP or a file that is not an Endurain export is refused with an explanation. To move more activities than the limit allows, use a [bulk import](importing.md) of the original files instead.
