"""Followers module for user follow relationships.

Follow requests, acceptance and removal between users. The follow graph is
private, so reads are privacy-checked in ``service``.

Other modules consume it only through ``integration_service`` (plus ``schema``,
``constants`` and ``events``); ``__init__`` exports nothing.
"""
