"""Which database objects the application's Alembic history manages."""

import jasil.orm as jasil_orm
from sqlalchemy.schema import SchemaItem

_JASIL_TABLE_PREFIX = "jasil_"


def include_object(
    obj: SchemaItem, name: str | None, type_: str, reflected: bool, compare_to: SchemaItem | None
) -> bool:
    """Keep this history off the tables JASIL owns.

    Two kinds of table name are left to JASIL's own migrations (``jasil.migrations``, which keeps its own version
    table):

    * Names starting with ``jasil_``. JASIL documents that every table it owns carries the prefix: its mapped tables,
      ``jasil_alembic_version`` and the audit-log partitions it creates on demand (``jasil_audit_log_p<date>``).
      ``jasil.orm.map_models`` maps its models into the same registry as the application's, so autogenerate would
      otherwise diff them and propose dropping them the day the substrate changes one.
    * The unprefixed names JASIL's tables had before it renamed them (``event_log``, ``event_outbox``,
      ``processing_jobs``, ...). The baseline does not create them; only a v0.21 database whose startup stopped
      before JASIL adopted its tables still holds them, and JASIL renames them on its next start.

    Args:
        obj: The schema object being considered.
        name: Its name.
        type_: The kind of object (``table``, ``column``, ``index``, ...).
        reflected: Whether it came from the database rather than the metadata.
        compare_to: The object it is being compared against, if any.

    Returns:
        False for a table JASIL owns or used to own under an unprefixed name, True otherwise.
    """
    if type_ == "table" and name is not None:
        return not (name.startswith(_JASIL_TABLE_PREFIX) or name in jasil_orm.legacy_table_names())
    return True
