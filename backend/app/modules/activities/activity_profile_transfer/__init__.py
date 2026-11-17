"""Activity profile transfer sub-module: the activities' section of a profile export and import.

It writes and reads the activities, their components, source files and media through the
contributors the activity packages register, and hands the profile package a section to run.

This package exports nothing from ``__init__``; other modules use it only through
``integration_service`` (see ``tests/architecture``).
"""
