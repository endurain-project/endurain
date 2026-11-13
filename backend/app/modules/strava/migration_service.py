"""The Strava operations exposed only to data migrations."""

import modules.strava.bulk_import_service as strava_bulk_import_service

drop_directory_for = strava_bulk_import_service.drop_directory_for
