# Health data and activity streams

How to read the health lists and charts for a date range, and what an activity stream carries. All paths are under `/api/v1`. The exact schemas are in the [API reference](api-reference.md).

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

`GET /activities/{activity_id}/streams` returns a page of the activity's streams and `GET /activities/{activity_id}/streams/{stream_type}` returns one; the public activity has the same two routes under `/public`. Each stream has a `stream_type` and a list of `stream_waypoints`, whose shape follows the type.

| `stream_type` | Stream | Waypoint value keys |
| ------------- | ------ | ------------------- |
| 1 | Heart rate | `hr` (bpm) |
| 2 | Power | `power` (watts) |
| 3 | Cadence | `cad` (rpm, spm for running) |
| 4 | Elevation | `ele` (meters) |
| 5 | Speed | `vel` (m/s) |
| 6 | Pace | `pace` (s/m, 0 at a standstill) |
| 7 | Map | `lat`, `lon` (decimal degrees) |
| 8 | Temperature | `temp` (degrees Celsius) |

- **Every waypoint has a `time`**: a UTC `YYYY-MM-DDTHH:MM:SS` string, or the seconds from the start as a number for a stream imported from Strava. When the owner hides the start time of the activity, `time` is missing from the waypoints other viewers get.
- **Values are numbers as stored**, so an integer such as `120` stays `120` and is not turned into `120.0`. A value can be `null` where the source recorded none.
- **A stream is served whole.** There is no downsampling, and a long activity has many waypoints; the page parameters count streams, not waypoints.
- The heart-rate stream also carries `zone_percentages`, computed from the owner's current thresholds. Streams of other types have `null` there.
