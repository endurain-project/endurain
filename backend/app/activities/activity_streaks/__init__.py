"""
Activity streaks sub-module for weekly streak tracking.

A week "counts" toward the streak when the user records at
least ``min_activities_per_week`` activities of the selected
types in it (see ``users.users_streak_settings``). Weeks follow
the user's configured first day of the week, and activities
are bucketed by their local start date.

The current week never breaks a streak while it is still in
progress: if its target is not met yet the streak is reported
as "at risk" and counted up to the previous week.

Exports:
    - utils: bucket_activities_by_week, calculate_weekly_streak
    - CRUD: get_weekly_streak
    - Router: /activities_streaks endpoints
"""
