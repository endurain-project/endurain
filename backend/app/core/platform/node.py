"""Process identity for competing-consumer coordination.

A single helper so the durable-job worker and the Redis Streams consumer derive
their identifier the same way. The value distinguishes competing consumers
across replicas in logs, lease holders (``processing_jobs.locked_by``), and
Redis pending-entry lists.
"""

import os
import socket


def process_identity() -> str:
    """Return a stable per-process identifier (hostname + PID).

    Returns:
        ``"{hostname}-{pid}"`` — unique per process, stable for its lifetime.
    """
    return f"{socket.gethostname()}-{os.getpid()}"
