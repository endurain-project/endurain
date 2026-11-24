# Device file fixtures

Real Garmin files recorded and contributed by the maintainer, published with their GPS data with the maintainer's
consent and licensed AGPL-3.0 like the repository; the goldens next to them are regenerated with
`uv run pytest tests/activities/activity_file_import/test_device_files.py --update-golden` and every golden diff is
reviewed.

| Case | Files | Device | What it covers |
| --- | --- | --- | --- |
| `outdoor_run` | FIT, GPX, TCX | Forerunner 955 | Outdoor run with GPS, record distance and speed, wrist power, running dynamics, a workout step; GPX HR/cadence/elevation; TCX position/HR/watts/speed/run cadence/altitude/distance. |
| `outdoor_ride` | FIT, GPX, TCX, Strava GPX | Edge 130 Plus | Road ride, barometric altitude (`altitude` and `enhanced_altitude`), 4 timer stops (pauses), course-point markers, temperature, no power; GPX with `atemp`; `_from_strava.gpx` is Strava's export of the same ride (`StravaGPX`, `<type>cycling</type>`, cadence 0 written where Garmin leaves it out). |
| `treadmill_run` | FIT, GPX, TCX | Forerunner 955 | Treadmill, no GPS, record distance/speed, wrist power, running dynamics; Garmin's GPX is an empty track. |
| `indoor_ride` | FIT, GPX, TCX | Garmin product 4565 | Indoor trainer, no GPS, record distance/speed, power, cadence, resistance, a workout step; GPX empty track. |
| `pool_swim` | FIT, GPX, TCX | Garmin product 4565 | 25 m pool, 63 active and 5 idle lengths, records carry HR only; GPX empty track. |
| `open_water_swim` | FIT, GPX, TCX | Forerunner 955 | Open water with GPS, temperature, strokes; GPX with `atemp`. |
| `triathlon` | FIT | Garmin product 4565 | Multisport FIT only: 5 sessions (open-water swim, transition, ride, transition, run), 9 laps, smart recording on the ride. |
| `strength` | FIT, GPX, TCX | Garmin product 4565 | Strength training, 43 sets, 15 workout steps, smart recording; GPX empty track. |
| `hiit` | FIT, GPX, TCX | Forerunner 955 | A session Garmin Connect labels HIIT (GPX `<type>hiit</type>`) while the FIT says training/strength_training; 78 sets; smart recording; GPX empty track. |

## Synthetic cases

These cases are built in code by `synthetic_files.py` because no real file exists for them; their goldens live under
`synthetic/<format>/`.

| Name | What it pins |
| --- | --- |
| `gpx/multi_track.gpx` | Two tracks with different name, type and calories, the second two hours later. |
| `gpx/two_segments_pause.gpx` | One track with two segments of about 600 m, five minutes apart. |
| `gpx/strava_style_ride.gpx` | StravaGPX creator, metadata name, cycling type, TrackPointExtension hr/cad/atemp and a bare `<power>` extension. |
| `gpx/phone_app_subsecond.gpx` | Phone-app walk with millisecond times, `hdop`, a `speed` extension, no HR and two waypoints. |
| `gpx/power_extension.gpx` | Power from the Garmin PowerExtension `PowerInWatts`. |
| `gpx/null_island.gpx` | Every point at latitude 0, longitude 0, with times and HR. |
| `gpx/null_island_dropouts.gpx` | A normal track with five middle points written as 0,0 (phone GPS dropout). |
| `gpx/untimed_points.gpx` | Every third trackpoint has no time but has HR and elevation. |
| `gpx/mixed_time_formats.gpx` | Times with `Z`, with `+01:00` and with no zone, interleaved. |
| `gpx/bad_sensor_values.gpx` | HR `NaN`, `-5`, empty, `abc` and `180.7`; elevation `nan` on one point. |
| `gpx/infinite_heart_rate.gpx` | One heart rate written as `inf`. |
| `gpx/out_of_order.gpx` | Two adjacent trackpoints swapped, so one point is out of time order. |
| `gpx/duplicate_timestamps.gpx` | Five consecutive points share one timestamp. |
| `gpx/sensor_zeros.gpx` | HR 0 dropouts for 20 points and cadence 0 (coasting) for 30 points. |
| `gpx/standing_still.gpx` | Ten minutes standing with +-2 m jitter, then five minutes moving at 3 m/s. |
| `gpx/gps_spike.gpx` | A steady track where one point jumps about 150 m sideways and back. |
| `gpx/noisy_flat_elevation.gpx` | 1800 points on flat ground with +-1.5 m elevation noise. |
| `gpx/sparse_recording.gpx` | Smart recording, five seconds between points. |
| `gpx/route_only.gpx` | Only `rte`/`rtept` and `wpt`, no track. |
| `gpx/single_point.gpx` | One timed trackpoint. |
| `gpx/malformed.gpx` | Truncated XML, cut in the middle of an element. |
| `gpx/not_gpx_root.gpx` | Well-formed XML whose root is not `gpx`. |
| `tcx/lost_fix.tcx` | A run with 30 middle trackpoints that have no position but keep HR, watts and distance. |
| `tcx/multi_activity.tcx` | A run and a ride an hour later in one file. |
| `tcx/short_laps.tcx` | Laps of 1 and 2 trackpoints between laps of 60. |
| `tcx/ride_power.tcx` | Outdoor ride with positions, altitude, Cadence, TPX Speed and Watts, LX AvgWatts on three laps. |
| `tcx/lap_summary_only.tcx` | A lap with totals, calories and average HR but no `Track`. |
| `tcx/missing_watts.tcx` | TPX on every trackpoint, Watts missing on some, no HR. |
| `tcx/paused.tcx` | A ten-minute gap inside a lap whose total time excludes the gap. |
| `tcx/subsecond.tcx` | Trackpoint times with milliseconds. |
| `tcx/other_sport_gps.tcx` | `Sport="Other"` with positions. |
| `tcx/malformed.tcx` | Truncated XML. |
| `fit/stryd_developer_power.fit` | Running records with Stryd-style developer fields (Power, Form Power, Leg Spring Stiffness) and no native power. |
| `fit/padel.fit` | Sport 64 with sub sport 85 (padel). |
| `fit/hiit.fit` | Sport 62 (hiit) with heart rate only. |
| `fit/ride_power_pauses.fit` | Ride with timer stop/start events around a five-minute pause; timer time below elapsed time. |
| `fit/no_session.fit` | Records only. |
| `fit/session_without_start_time.fit` | A session with a timestamp and elapsed time but no `start_time`. |
| `fit/record_without_timestamp.fit` | One record mid-file without a timestamp. |
| `fit/unset_clock.fit` | Timestamps below 0x10000000 (device clock not set). |
| `fit/multisport_boundary.fit` | Run then bike sessions sharing second 60, with a record and a lap on it and `num_sessions` 2. |
| `fit/two_pool_sessions.fit` | Two lap swimming sessions, each with active and idle lengths. |
| `fit/lap_swim_missing_length_time.fit` | A pool swim with an active length whose `total_timer_time` is invalid. |
| `fit/gps_spike.fit` | Records with one position jump of about 150 m. |
| `fit/no_records.fit` | `file_id`, lap and session only (a manual entry). |
| `fit/many_sessions.fit` | Twelve short sessions in one file. |
