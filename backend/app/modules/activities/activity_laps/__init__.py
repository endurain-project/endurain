"""Activity laps sub-module for per-lap metrics within an activity.

Per-lap distance, duration, heart rate, power, cadence and altitude parsed
from fitness files (.fit, .tcx, .gpx) or third-party providers.

Importing this package does not pull in its ORM, CRUD or services: reach for
the submodule you need (``.crud``, ``.schema``, ``.router``). A re-export
facade here would hand out the ORM model and the CRUD functions under a
package path, which is a silent bypass of the boundaries the import-linter
contracts enforce against ``*.models`` and ``*.crud``.
"""
