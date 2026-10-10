"""Activity exercise titles sub-module.

Maps FIT exercise category/name identifiers to the human-readable workout
step names used by activity sets.

Importing this package does not pull in its ORM, CRUD or services: reach for
the submodule you need (``.crud``, ``.schema``, ``.router``). A re-export
facade here would hand out the ORM model and the CRUD functions under a
package path, which is a silent bypass of the boundaries the import-linter
contracts enforce against ``*.models`` and ``*.crud``.
"""
