"""Activity reverse-geocoding subsystem.

Resolves an activity's ``city``/``town``/``country`` from its first GPS waypoint
and reacts to the ``activity.created`` domain event. Reverse-geocoding used to run
inline inside the file parsers; moving it here
keeps the parse path free of network I/O and lets the work run durably/async when
durable jobs are enabled, exactly like the thumbnail subsystem.

Two shapes of handler live in ``subscribers``: a durable ``*_for_event`` core that
**raises** so the job runner can retry/dead-letter, and an ``on_*`` bus subscriber
that **swallows** so a geocoding failure never breaks activity import. The
scheduled backfill (:func:`subscribers.run_missing_location_backfill`) is the
reconciliation net for anything the create-path handler misses.
"""
