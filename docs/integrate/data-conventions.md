# Data conventions

The vocabulary the list filters, dates, units and money share across the API. All paths are under `/api/v1`. The exact schemas are in the [API reference](api-reference.md).

## Gear components and their usage

A gear component is returned without usage by `GET /gear-components`, `GET /gear-components/{gear_component_id}`, `POST /gear-components` and `PATCH /gear-components/{gear_component_id}`. Only `GET /gears/{gear_id}/components` also carries `current_distance` (meters) and `current_time` (seconds): the distance and time of the gear's activities between the component's `purchase_date` and `retired_date`. A component without a `purchase_date` reports `0` for both.

## Dates and times

- **An instant carries a UTC offset.** Every request field that is a point in time (`fast_start_time`, `fast_end_time`, a poop record's `date_time`, a sleep's `sleep_start_time_gmt` and `sleep_end_time_gmt`, its stage times, an API key's `expires_at`) must be a timestamp such as `2025-03-01T08:30:00Z` or `2025-03-01T10:30:00+02:00`. A timestamp without an offset is refused with `422`. Responses are UTC.
- **A wall clock is named `*_local`.** `sleep_start_time_local` and `sleep_end_time_local` are the reading on the athlete's own clock, sent without an offset and kept as given; the server does not convert them.
- **A time must be between 1900-01-01 and one day from now.** This includes the `fast_end_time` that ends a fasting session (`POST /health/fasting/{id}/complete`).

## List filters

Every collection answers a page (`items`, `total`, `page`, `num_records`, `next`) and filters through query parameters named the same way:

| Kind | Name | Meaning |
| ---- | ---- | ------- |
| Text | `<field>_contains` | Keeps records whose field contains the text, ignoring case. `GET /activities` takes `name_contains` and `GET /gears` takes `nickname_contains`. |
| State | `active` | `true` keeps only active records and `false` only inactive ones; leave it out for both. `GET /gears` and `GET /gears/{gear_id}/components` take it. |
| Dates | `start_date`, `end_date` | An inclusive range of local dates, `YYYY-MM-DD`. A `start_date` after the `end_date` is refused with `422`, whose `errors` name `end_date`. |
| Window | `interval` | A rolling window that looks back from today (`last_7_days`, `last_30_days`, ...). A date range replaces it. |
| Period | `period` | A calendar period around the day or year the summary and stats routes take: `week` or `month` for the stats, and also `year` or `lifetime` for the summaries. |

`interval` and `period` stay separate because they answer different questions: how far back from now, or which calendar week, month or year.

A collection that is not a child of another resource (`/gears`, `/gear-components`, `/activities`, `/activities/exercise-titles`) pages 25 records by default and at most 200. A child collection (`/activities/{activity_id}/laps`, `/gears/{gear_id}/components`) pages 200 by default.

## Activity types and sports

Three vocabularies name activities, and they do not all mean the same thing:

- **Activity type**: one of the 47 keys of `GET /activities/types` (`run`, `trail_run`, `ride`, `alpine_ski`, `surf`, ...). Activities, the activity list filter `type` and the summaries use it.
- **Stats sport**: a group of activity types. The keys of the stats response (`GET /users/{user_id}/activities/stats`) are the activity type key when a sport is one type (`hike`, `rowing`, `snowboard`, `windsurf`, `stand_up_paddling`, `surf`, `kayaking`, `sailing`, `snow_shoeing`, `inline_skating`) and a group otherwise: `run` (run, trail run, virtual run, track run, treadmill), `bike` (every ride), `swim` (lap and open water), `walk` (walk and indoor walk) and `snow_ski` (alpine and nordic ski). Types that belong to no sport count under `other`.
- **Goal activity type**: `run`, `bike`, `swim`, `walk`, `strength` or `cardio`, the sports a goal can target. A goal's `run`, `bike` and `swim` count the same types as the stats sport of that name. `walk` is wider: a walking goal also counts hiking and snowshoeing. `strength` and `cardio` have no stats sport; they count strength training and workouts, and cardio training, crossfit, HIIT and jump rope.

So `run`, `bike`, `swim` and `walk` mean a group of types in the stats and in the goals, while the activity type `run` is only plain running.

## Units and money

- **A measurement states its unit** in the field description of the OpenAPI document: meters for distance and elevation, seconds for time, meters per second for speed, seconds per meter for pace, watts for power, beats per minute for heart rate. Where the name can carry the unit it does (`weight_kg`, `amount_ml`, `total_sleep_seconds`, `body_fat_percent`).
- **A gear's distances are meters.** `initial_distance` (the distance the gear had before it was tracked) uses the same unit as `total_distance`, which includes it. A component's `expected_kms` is the wear threshold in meters of activity distance for a distance-tracked gear and in seconds of activity time for a time-tracked one (racquets), whatever its name says.
- **A price is a decimal string.** `purchase_value` of a gear or a component, and the gear's `total_components_cost`, are strings with two decimals such as `"129.90"`, in the owner's `currency` user setting; the API does not convert between currencies. A JSON number (`129.9`) or a string with another shape (`"129.9"`, `"129,90"`) is refused with `422`.
- **An export from an earlier release still imports.** A gear archive with `initial_kms` (kilometers) or a numeric `purchase_value` is read as `initial_distance` in meters and a decimal string.

## Goals

A goal's target (`goal_calories`, `goal_activities_number`, `goal_distance`, `goal_elevation`, `goal_duration`) must be above zero: `0` is refused with `422`. The progress of a goal (`GET /profile/goals/results`) names its period with `start_date` and `end_date`, which are dates (`YYYY-MM-DD`).
