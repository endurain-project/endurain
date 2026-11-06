# Data conventions

The vocabulary the list filters, dates, units and money share across the API. All paths are under `/api/v1`. The exact schemas are in the [API reference](api-reference.md).

## Gear components and their usage

A gear component is returned without usage by `GET /gear-components`, `GET /gear-components/{gear_component_id}`, `POST /gear-components` and `PATCH /gear-components/{gear_component_id}`. Only `GET /gears/{gear_id}/components` also carries `current_distance` (meters) and `current_time` (seconds): the distance and time of the gear's activities between the component's `purchase_date` and `retired_date`. A component without a `purchase_date` reports `0` for both.

## Dates and times

- **An instant carries a UTC offset.** Every request field that is a point in time (`fast_start_time`, `fast_end_time`, a poop record's `date_time`, a sleep's `sleep_start_time_gmt` and `sleep_end_time_gmt`, its stage times, an API key's `expires_at`) must be a timestamp such as `2025-03-01T08:30:00Z` or `2025-03-01T10:30:00+02:00`. A timestamp without an offset is refused with `422`. Responses are UTC.
- **A wall clock is named `*_local`.** `sleep_start_time_local` and `sleep_end_time_local` are the reading on the athlete's own clock, sent without an offset and kept as given; the server does not convert them.
- **A time must be between 1900-01-01 and one day from now.** This includes the `fast_end_time` that ends a fasting session (`POST /health/fasting/{id}/complete`).
