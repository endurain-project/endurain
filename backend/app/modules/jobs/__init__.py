"""Jobs module: one place to read every background job by id.

Each feature that answers ``202`` owns its job's record and its status model; this module resolves a job id to
the owning feature, checks the caller may read it and lists the caller's jobs. It calls the features only through
their ``integration_service``, ``schema`` and ``constants``, and no module imports it; ``__init__`` exports
nothing.
"""
