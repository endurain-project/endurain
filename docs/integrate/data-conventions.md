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

`GET /activities` also takes `gear_id` to keep only the activities recorded with that gear, on top of the other filters; the page and its `total` both follow it. Another user's list (`GET /users/{user_id}/activities`) has no gear filter, so a gear its owner hides cannot be probed.

The activity lists (`GET /activities`, `GET /users/{user_id}/activities` and `GET /activities/feed`) return a summary of each activity: every field of the activity except `private_notes` and `import_info`, which only `GET /activities/{activity_id}` and the detail read carry. Read the activity before editing those fields.

`GET /activities/feed` is a cursor feed rather than a page: pass the `next_cursor` of the previous slice as `cursor` and stop when it is `null`. `scope` picks what it lists: `following` (the default) is the activities of the users the caller follows, as the caller may see them; `mine` is the caller's own activities of every visibility, as their owner sees them. Both are newest first, with a hidden start time ordered by when the activity was recorded, and both carry the owners' public profiles in `users`.

`GET /activities/{activity_id}/detail` returns the activity with the first page of its laps, workout sets, workout steps and legs in one read. Each collection is the page its own route returns, so a `next` page continues on that route. The activity carries its `media` when the caller owns it, as the activity lists do, and `owner` is the owner's public profile (`null` when the owner is not visible). Streams stay on their own route. The `ETag` is the activity's.

## Activity types and sports

Three vocabularies name activities, and they do not all mean the same thing:

- **Activity type**: one of the 48 keys of `GET /activities/types` (`run`, `trail_run`, `ride`, `alpine_ski`, `surf`, ...). Activities, the activity list filter `type` and the summaries use it.
- **Stats sport**: a group of activity types. The keys of the stats response (`GET /users/{user_id}/activities/stats`) are the activity type key when a sport is one type (`hike`, `rowing`, `snowboard`, `windsurf`, `stand_up_paddling`, `surf`, `kayaking`, `sailing`, `snow_shoeing`, `inline_skating`) and a group otherwise: `run` (run, trail run, virtual run, track run, treadmill), `bike` (every ride), `swim` (lap and open water), `walk` (walk and indoor walk) and `snow_ski` (alpine and nordic ski). Types that belong to no sport count under `other`.
- **Goal activity type**: `run`, `bike`, `swim`, `walk`, `strength` or `cardio`, the sports a goal can target. A goal's `run`, `bike` and `swim` count the same types as the stats sport of that name. `walk` is wider: a walking goal also counts hiking and snowshoeing. `strength` and `cardio` have no stats sport; they count strength training and workouts, and cardio training, crossfit, HIIT and jump rope.

So `run`, `bike`, `swim` and `walk` mean a group of types in the stats and in the goals, while the activity type `run` is only plain running.

## Multisport activities

A multisport activity, such as a triathlon, is stored as one activity of type `multisport` and its legs: ordinary activities (swim, transition, bike, transition, run) whose `parent_activity_id` is the id of the multisport activity. Every other activity has `parent_activity_id` `null`, and a leg of a leg does not exist. `parent_activity_id` is read-only: no request carries it. The multisport activity holds the sums of its legs and has no streams, laps, sets, workout steps or gear of its own.

An upload, a Garmin Connect sync or a bulk import of a FIT file the device recorded as one multisport activity creates the multisport activity and all its legs together, or none of them. The legs are named for their sport (`Run`, `Transition`, ...), take the multisport activity's privacy, and the multisport activity's map thumbnail and location come from its legs. The owner gets one new-activity notification, for the multisport activity. A Strava export lists such a file once per leg; it imports once, under the listing whose start is the first leg's, and that listing's name, description and photos go to the multisport activity.

- **Lists show the multisport activity, not its legs.** `GET /activities`, `GET /users/{user_id}/activities`, `GET /activities/feed`, their `total` and the profile overview count, the name search and `GET /activities/types` leave the legs out, so a triathlon counts once. A list filtered by `gear_id` holds the legs on that gear, since a multisport activity carries no gear. `GET /activities/{activity_id}` and the routes under it read a leg like any activity, under the leg's own visibility, and `GET /sync` carries every leg with its `parent_activity_id`.
- **Sums run over the legs.** The stats, the summaries, the goals and the gear usage add up distance, time, calories and elevation over the legs and never over the multisport activity, so nothing is counted twice. A leg counts as an activity of its own sport in per-type and per-sport counts (a run leg is a run), the activity count of a summary without a type filter counts the multisport activity once, and a summary filtered to `multisport` is empty.
- **The legs have a route.** `GET /activities/{activity_id}/legs` and `GET /public/activities/{activity_id}/legs` return a page of the multisport activity's legs, earliest start first, as the list rows `GET /activities` returns, masked for the caller the same way; the page size is that of a child collection (200 by default). Like the other child collections they answer an empty page (`200`, `total` `0`) for an activity that has no legs, does not exist or is not visible to the caller. The `legs` of `GET /activities/{activity_id}/detail` and of the public detail is the first page of the same list, empty for any other activity.
- **A client cannot set `multisport`.** `PATCH /activities/{activity_id}` with `activity_type` `multisport` is `422`.
- **The type and gear of a multisport activity are its legs'.** `PATCH` with `activity_type` or `gear_id` on a multisport activity is `409`. Name, description and notes edit as usual, and each leg keeps its own type, gear, name and notes.
- **Privacy belongs to the multisport activity.** `visibility`, `is_hidden` and every `hide_*` field of a leg are those of its parent: a `PATCH` that sets one on a leg is `409`. Setting one on the multisport activity gives the same values to every leg in the same transaction: each leg that changed gets a new `version` and `ETag`, and an `activity.updated` event. `PATCH /activities` with a `visibility` (the bulk edit) changes the legs of every multisport activity it changes and never a leg by itself.
- **A leg is deleted with its multisport activity.** `DELETE /activities/{activity_id}` on a leg is `409`. On the multisport activity it deletes the legs too, and `GET /sync` lists a deletion for the multisport activity and for each leg.

## Units and money

- **A measurement states its unit** in the field description of the OpenAPI document: meters for distance and elevation, seconds for time, meters per second for speed, seconds per meter for pace, watts for power, beats per minute for heart rate. Where the name can carry the unit it does (`weight_kg`, `amount_ml`, `total_sleep_seconds`, `body_fat_percent`).
- **A gear's distances are meters.** `initial_distance` (the distance the gear had before it was tracked) uses the same unit as `total_distance`, which includes it. A component's `expected_usage` is the wear threshold in meters of activity distance for a distance-tracked gear and in seconds of activity time for a time-tracked one (racquets).
- **A price is a decimal string.** `purchase_value` of a gear or a component, and the gear's `total_components_cost`, are strings with two decimals such as `"129.90"`, in the owner's `currency` user setting; the API does not convert between currencies. A JSON number (`129.9`) or a string with another shape (`"129.9"`, `"129,90"`) is refused with `422`.

## Goals

A goal's target (`goal_calories`, `goal_activities_number`, `goal_distance`, `goal_elevation`, `goal_duration`) must be above zero: `0` is refused with `422`. The progress of a goal (`GET /profile/goals/results`) names its period with `start_date` and `end_date`, which are dates (`YYYY-MM-DD`).
