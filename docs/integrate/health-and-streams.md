# Health data and activity streams

How to write health records, how to read the health lists and charts for a date range, and what an activity stream carries. All paths are under `/api/v1`. The exact schemas are in the [API reference](api-reference.md).

## Writing health records

Weight, steps, sleep, water, poop and fasting are written the same way. All paths are under `/health/{metric}`.

- **One record per day** for weight, steps, sleep and water. A `POST` for a day that already has one is `409`, and the day's record is changed with `PATCH /health/{metric}/{id}`. Water does not add to the day: send the new total.
- **A date is not in the future.** A record dated after the athlete's own today is `400`, on create and on a `PATCH` that moves it. A poop or fasting time counts as the day it falls on in the athlete's time zone.
- **`date` may be left out** on weight, steps, sleep and water: the record is for the athlete's today.
- **`source` is read-only.** Every record answers it: `manual` for what a person entered, `garmin` for what the Garmin sync wrote. A request cannot set it.
- **The unit is in the name** of a measurement: mass `_kg`, duration `_seconds`, volume `_ml` and a percentage `_percent`. Counts, scores and rates keep a plain name.

| Metric | Fields with a unit |
| ------ | ------------------ |
| Weight | `weight_kg`, `bone_mass_kg`, `muscle_mass_kg`, `body_fat_percent`, `body_water_percent` |
| Sleep | `total_sleep_seconds` and the other `*_seconds` durations, `avg_spo2_percent`, `lowest_spo2_percent`, `highest_spo2_percent` |
| Water | `amount_ml` |
| Fasting | `target_duration_seconds`, `actual_duration_seconds` |
| Targets (`/health/targets`) | `weight_kg`, `sleep_seconds`, `fasting_seconds`, `water_ml`; `steps` and `poop_count` are counts |

A profile export writes these names.

## Health lists and charts

Weight, steps, sleep, water, poop and fasting each have a list (`GET /health/{metric}`) and, except for fasting, a chart (`GET /health/{metric}/chart`; sleep also has `GET /health/sleep/chart/resting-heart-rate`). They take the same window parameters.

| Parameter | Meaning |
| --------- | ------- |
| `interval` | A window that looks back from today: `last_7_days`, `last_30_days`, `last_90_days`, `last_year` or `all_time`. A list without it returns every record. A chart without it uses `last_7_days`. |
| `start_date` | The first day to include, as `YYYY-MM-DD`. |
| `end_date` | The last day to include, as `YYYY-MM-DD`. |

- **Both dates are inclusive.** `start_date=2025-03-01&end_date=2025-03-01` is that one day.
- **One date leaves the other side open.** With only `start_date` the window runs to the newest record, and with only `end_date` it starts at the oldest.
- **A date replaces `interval`.** When either date is given, `interval` is ignored: it always looks back from today, so combining it with a past range would leave nothing.
- **A start after the end is refused** with `422`, whose `errors` name `end_date`.
- **Without any of the three parameters nothing changes.** A list returns every record and a chart covers the last 7 days.
- **Days are the athlete's own.** Poop records belong to the day they happened in the user's time zone. Fasting sessions belong to the UTC day they started on.
- **A list's `total` counts the window**, not only the records on the page.
- **The sleep list leaves out the sleep stages.** A night in `GET /health/sleep` has every field of the record except `sleep_stages`, and `has_sleep_stages` says whether it has any. `GET /health/sleep/{health_sleep_id}` returns the night with its stages; read it before editing them. A night holds at most 1440 stages, one per minute of a day; more is `422`.
- **The sleep list can keep only the nights with a resting heart rate.** `GET /health/sleep?has_resting_heart_rate=true` returns those nights, and `false` the nights without one; the `total` counts the same nights.
- **A chart is aggregated.** It answers with a `bucket` (`day`, `week` or `month`, the finest that keeps it to 366 points) and one point per bucket that holds a value, so a long range stays small.

## Activity streams

`GET /activities/{activity_id}/streams` returns the activity's streams as one object, and the public activity has the same route under `/public`. The samples sit on one timeline: `offsets_ms` holds each sample's time in milliseconds from the start of the activity, and every other field is a list with one value per sample, in the same order.

| Field | Holds | Unit |
| ----- | ----- | ---- |
| `offsets_ms` | Each sample's time from the activity start | milliseconds |
| `latitude`, `longitude` | The position | decimal degrees |
| `elevation` | Elevation | meters |
| `heart_rate` | Heart rate | beats per minute |
| `power` | Power | watts |
| `cadence` | Cadence | rpm (spm for running) |
| `speed` | Speed | m/s |
| `pace` | Pace, derived from `speed` | s/m; `null` where the speed is not above 0 |
| `temperature` | Temperature | degrees Celsius |
| `heart_rate_zones` | Time in each heart-rate zone | see below |

- **A channel is `null`** when the activity has none or hides it from the viewer: the list is not there, and the field is `null`. Inside a list, a value is `null` where a sample has none, such as a heart-rate dropout. The position is `null` as a pair. The owner hides the map, heart rate, power, cadence, elevation, speed and pace one by one; the temperature is never hidden.
- **`hide_start_time` removes nothing from the streams.** `offsets_ms` counts from the start and shows only the duration, which the activity shows anyway. The route and its other values are served as the other flags allow.
- **An activity with no samples** answers `200` with an empty `offsets_ms` and every channel `null`. An activity that does not exist, or that you may not read, is `404` with `urn:endurain:error:not-found`, the same answer for both.
- **`max_points` reduces a long activity.** An integer from 2 to 10000. When the activity has more samples, its time from the first to the last sample is split into `max_points` equal buckets, and each bucket that holds a sample becomes one: its offset is the mean of the offsets (a whole number of milliseconds) and a channel is the mean of its values that exist (`null` when none does). A pause leaves empty buckets, so fewer samples can come back. The position is averaged over the samples that have both coordinates, and `pace` comes from the bucket's mean speed. Omitted, every sample is returned. A value out of range is `422`.
- **`heart_rate_zones` always counts every sample**, whatever `max_points` says, and is computed from the owner's current thresholds. Each zone has `time_seconds`, the time spent in the zone, and `percent`, its share of the recorded heart-rate time. A sample counts the time it holds until the next one, at most the pause threshold, so a pause does not inflate a zone; a heart rate of `0` is a dropout and adds no time. It is `null` when no zone holds any time, when the owner's maximum heart rate is unknown, and when the heart rate is hidden from you.
