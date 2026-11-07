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

A profile export writes these names. Importing an archive from an earlier release still works: its old field names (`weight`, `body_fat`, `sleep`, `fasting`, `avg_spo2` and the like) are read as the new ones.

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
- **A chart is aggregated.** It answers with a `bucket` (`day`, `week` or `month`, the finest that keeps it to 366 points) and one point per bucket that holds a value, so a long range stays small.

## Activity streams

`GET /activities/{activity_id}/streams` returns a page of the activity's streams and `GET /activities/{activity_id}/streams/{stream_type}` returns one; the public activity has the same two routes under `/public`. Each stream has a `stream_type`, a string, and a list of `stream_waypoints`, whose shape follows the type. `{stream_type}` in the path takes the same string.

| `stream_type` | Stream | Waypoint value keys |
| ------------- | ------ | ------------------- |
| `heart_rate` | Heart rate | `hr` (bpm) |
| `power` | Power | `power` (watts) |
| `cadence` | Cadence | `cad` (rpm, spm for running) |
| `elevation` | Elevation | `ele` (meters) |
| `speed` | Speed | `vel` (m/s) |
| `pace` | Pace | `pace` (s/m, 0 at a standstill) |
| `map` | Map | `lat`, `lon` (decimal degrees) |
| `temperature` | Temperature | `temp` (degrees Celsius) |

- **Every waypoint has a `time`**: a UTC `YYYY-MM-DDTHH:MM:SS` string, or the seconds from the start as a number for a stream imported from Strava. When the owner hides the start time of the activity, `time` is missing from the waypoints other viewers get.
- **Values are numbers as stored**, so an integer such as `120` stays `120` and is not turned into `120.0`. A value can be `null` where the source recorded none.
- **A stream is served whole.** There is no downsampling, and a long activity has many waypoints; the page parameters count streams, not waypoints.
- The heart-rate stream also carries `zone_percentages`, computed from the owner's current thresholds. Streams of other types have `null` there.
