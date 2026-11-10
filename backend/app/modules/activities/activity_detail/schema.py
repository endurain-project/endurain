"""Pydantic schema for the combined activity detail."""

from pydantic import BaseModel

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema
import modules.users.users.schema as users_schema


class ActivityDetailRead(BaseModel):
    """An activity together with the first page of each child collection the detail view shows.

    Each collection is the page envelope its own route returns, so a client that finds a ``next`` page
    continues with that route. A collection hidden from the viewer, or one the activity has none of,
    is an empty page.

    Attributes:
        activity: The activity, masked as the viewer may see it. Its ``media`` is filled for its owner
            only, as in the list responses.
        owner: The activity owner's public profile, the projection ``GET /users/{user_id}`` returns.
            ``null`` for an anonymous viewer when the server does not share user info publicly, and
            for an owner who is inactive or awaiting approval.
        laps: The activity's laps.
        sets: The activity's performed workout sets.
        workout_steps: The activity's planned workout steps.
    """

    activity: activity_schema.ActivityRead
    owner: users_schema.UserPublicRead | None
    laps: activity_laps_schema.ActivityLapsPage
    sets: activity_sets_schema.ActivitySetsPage
    workout_steps: activity_workout_steps_schema.ActivityWorkoutStepsPage
