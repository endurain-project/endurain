"""
User weekly streak settings module.

Stores per-user configuration for the weekly activity
streak feature: how many activities a week needs to count
toward the streak, which activity types are counted, and
whether the streak is shown on the user's profile.

Reads return defaults until the user first saves their
settings, which is when the row is created, so existing
users need no data migration.
"""
