"""The real worker entry point, with upload processing delayed.

Keeps an upload job in flight for ``SLOW_SECONDS`` so a test can kill the worker
mid-job or let the job outlive its lease. Everything after the delay is the
unmodified import.
"""

# ruff: noqa: E402, T201 - a process entry point: it extends sys.path before importing, and prints for its parent.

import os
import sys
import time

sys.path.insert(0, ".")

import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service

_original = upload_entry_service.process_staged_upload
_delay = float(os.environ["SLOW_SECONDS"])


def _delayed(*args, **kwargs):
    print(f"SLOW-START pid={os.getpid()} delay={_delay}", flush=True)
    time.sleep(_delay)
    return _original(*args, **kwargs)


upload_entry_service.process_staged_upload = _delayed

import worker

worker.main()
