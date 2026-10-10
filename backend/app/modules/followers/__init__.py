"""Followers module for user follow relationships.

Follow requests, acceptance and removal between users. Other modules consume
this module through ``integration_service``; the follow graph is private, so
reads are privacy-checked in ``service``.

Importing this package does not pull in its ORM, CRUD or services: reach for
the submodule you need (``.crud``, ``.schema``, ``.router``). A re-export
facade here would hand out the ORM model and the CRUD functions under a
package path, which is a silent bypass of the boundaries the import-linter
contracts enforce against ``*.models`` and ``*.crud``.
"""
