"""Activity streams sub-module for time-series stream data.

Heart rate, power, cadence, elevation, speed, pace and map streams, plus the
visibility filtering applied before a stream is served.

Importing this package does not pull in its ORM, CRUD or services: reach for
the submodule you need (``.crud``, ``.schema``, ``.router``). A re-export
facade here would hand out the ORM model and the CRUD functions under a
package path, which is a silent bypass of the boundaries the import-linter
contracts enforce against ``*.models`` and ``*.crud``.
"""
