"""
User weekly streak settings module.

Stores per-user configuration for the weekly activity
streak feature: how many activities a week needs to count
toward the streak, which activity types are counted, and
whether the streak is shown on the user's profile.

Settings rows are created lazily with defaults the first
time they are read or updated, so existing users need no
data migration.
"""
