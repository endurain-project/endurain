# Changelog

## Unreleased

### Changed

- Elevation is now smoothed on import (median window 9, then moving average window 21). The stored elevation stream, the elevation graph and the activity's elevation gain/loss all use the same smoothed series, so they agree. Timestamps and all other streams are unchanged. This applies to .fit, .gpx and .tcx imports and to Strava sync.
- Elevation gain/loss now counts far less GPS noise (for example ~186 m instead of 251 m on the run from endurain-flutter issue 17).

### Migration

- Existing activities are **not** recomputed or migrated. Their stored elevation stream and gain/loss keep the old raw values. Re-import an activity to get the smoothed values.
