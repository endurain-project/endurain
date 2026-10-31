"""Storage addressing constants shared with the packages that stage files here."""

#: Domain-owned storage namespace for activity source files. Retained files live
#: under ``processed/`` and staged uploads under ``upload_staging/``; both share
#: the area, so it is stated once and the ingestion package imports it rather than
#: repeating the string.
ACTIVITY_FILE_STORAGE_AREA = "activity_files"
