"""
User weekly activity streaks.

A week "counts" toward the streak when the user records at
least ``min_activities_per_week`` activities of the selected
types in it (see ``users.users_streak_settings``). Weeks follow
the user's configured first day of the week, and activities
are bucketed by their local start date.

The current week, taken in the user's timezone, never breaks
a streak while it is still in progress: if its target is not
met yet the streak is reported as "at risk" and counted up to
the previous week.
"""
