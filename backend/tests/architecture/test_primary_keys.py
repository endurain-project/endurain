"""Every primary key of the application's tables is a native ``uuid``, and every foreign key matches its target.

The UUID id migration gave each table a ``uuid`` primary key. Five tables keep another key on purpose; each has its
reason in ``_NON_UUID_PRIMARY_KEYS``. The checks are small pure functions over a ``MetaData`` so the self-tests run
the same code on a synthetic one. Tables JASIL owns are left out as ``migrations.schema_scope`` leaves them out.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import model_registry
from core.database import Base
from migrations import schema_scope

#: The tables whose primary key is not a ``uuid``, with the reason.
_NON_UUID_PRIMARY_KEYS: dict[str, str] = {
    "server_settings": "A single row with id 1.",
    "mail_settings": "A single row with id 1.",
    "migrations": "Internal tracking of the data migrations, numbered in order.",
    "activity_exercise_titles": "Lookup data keyed by the FIT exercise category and name enums.",
    "oauth_states": "The id is the OAuth state parameter, a secrets.token_urlsafe(32) secret, not an identifier.",
}


def _tables(metadata: sa.MetaData) -> list[sa.Table]:
    return [
        table for table in metadata.sorted_tables if schema_scope.include_object(None, table.name, "table", False, None)
    ]


def _compiled(column: sa.Column) -> str:
    return column.type.compile(dialect=postgresql.dialect())


def non_uuid_primary_keys(metadata: sa.MetaData, allowed: dict[str, str]) -> list[str]:
    """List the primary-key columns that are not ``uuid`` and whose table is not allowed, as ``table.column``."""
    return [
        f"{table.name}.{column.name}"
        for table in _tables(metadata)
        if table.name not in allowed
        for column in table.primary_key.columns
        if not isinstance(column.type, sa.Uuid)
    ]


def mismatched_foreign_keys(metadata: sa.MetaData) -> list[str]:
    """List the foreign-key columns whose PostgreSQL type differs from the referenced column's, as text."""
    mismatches: list[str] = []
    for table in _tables(metadata):
        for foreign_key in (key for constraint in table.foreign_key_constraints for key in constraint.elements):
            referenced = foreign_key.column
            own = foreign_key.parent
            if _compiled(own) != _compiled(referenced):
                mismatches.append(
                    f"{table.name}.{own.name} {_compiled(own)} -> {referenced.table.name}.{referenced.name} "
                    f"{_compiled(referenced)}"
                )
    return mismatches


def stale_allowlist_entries(metadata: sa.MetaData, allowed: dict[str, str]) -> list[str]:
    """List the allowed tables that do not exist or whose primary key is in fact a ``uuid``."""
    tables = {table.name: table for table in _tables(metadata)}
    return [
        name
        for name in allowed
        if name not in tables or all(isinstance(column.type, sa.Uuid) for column in tables[name].primary_key.columns)
    ]


def _application_metadata() -> sa.MetaData:
    model_registry.import_all_models()
    return Base.metadata


def test_every_primary_key_is_a_uuid_but_the_allowed_ones() -> None:
    assert non_uuid_primary_keys(_application_metadata(), _NON_UUID_PRIMARY_KEYS) == []


def test_every_foreign_key_has_the_type_of_the_column_it_references() -> None:
    assert mismatched_foreign_keys(_application_metadata()) == []


def test_every_allowed_table_exists_and_has_a_non_uuid_primary_key() -> None:
    assert stale_allowlist_entries(_application_metadata(), _NON_UUID_PRIMARY_KEYS) == []


def _synthetic_metadata() -> sa.MetaData:
    metadata = sa.MetaData()
    sa.Table("parents", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    sa.Table("counters", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    sa.Table(
        "children",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("parents.id")),
    )
    return metadata


def test_the_checks_report_an_integer_key_and_a_mistyped_foreign_key() -> None:
    metadata = _synthetic_metadata()

    assert non_uuid_primary_keys(metadata, {}) == ["counters.id"]
    assert non_uuid_primary_keys(metadata, {"counters": "reason"}) == []
    assert mismatched_foreign_keys(metadata) == ["children.parent_id VARCHAR(36) -> parents.id UUID"]


def test_the_check_reports_an_allowed_table_that_is_missing_or_has_a_uuid_key() -> None:
    metadata = _synthetic_metadata()

    assert stale_allowlist_entries(metadata, {"counters": "reason"}) == []
    assert stale_allowlist_entries(metadata, {"parents": "reason", "missing": "reason"}) == ["parents", "missing"]
