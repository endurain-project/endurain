"""User goals module for managing user fitness goals.

Goal definitions per activity type and interval, and the progress calculation against the
user's activities.

Other modules consume it only through ``integration_service`` (plus ``schema``);
``__init__`` exports nothing.
"""
