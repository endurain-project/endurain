# Data conventions

The vocabulary the list filters, dates, units and money share across the API. All paths are under `/api/v1`. The exact schemas are in the [API reference](api-reference.md).

## Gear components and their usage

A gear component is returned without usage by `GET /gear-components`, `GET /gear-components/{gear_component_id}`, `POST /gear-components` and `PATCH /gear-components/{gear_component_id}`. Only `GET /gears/{gear_id}/components` also carries `current_distance` (meters) and `current_time` (seconds): the distance and time of the gear's activities between the component's `purchase_date` and `retired_date`. A component without a `purchase_date` reports `0` for both.
