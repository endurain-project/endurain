"""API route that reports what changed in the caller's records, served under ``/sync``."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Security

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.auth.dependencies as auth_dependencies
import modules.sync.schema as sync_schema
import modules.sync.service as sync_service

router = APIRouter()

#: Changes a sync page returns when ``num_records`` is not given.
_DEFAULT_NUM_RECORDS = 100


@router.get(
    "",
    response_model=sync_schema.SyncPage,
    # No scope of its own: each record type needs the scope that reads it, so the service checks them.
    dependencies=[Security(auth_dependencies.check_scopes, scopes=[])],
)
def read_sync(
    token_user_id: auth_dependencies.CurrentUserId,
    scopes: auth_dependencies.CurrentScopes,
    db: core_dependencies.DbSession,
    cursor: Annotated[str | None, Query()] = None,
    types: Annotated[list[sync_schema.SyncType] | None, Query()] = None,
    num_records: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_NUM_RECORDS)] = None,
) -> sync_schema.SyncPage:
    """Report what changed in the caller's records since a cursor, oldest first, deletions included.

    Without a cursor the walk starts from the beginning and reports every record. Send the `next_cursor` back as
    `cursor`: while `has_more` is true, ask again at once; once it is false, keep the cursor for the next sync.
    A change carries the record as its owner reads it; a deletion carries `record: null`. `types` limits the walk
    to some record types (repeat the parameter); without it, every type the caller's scopes can read is walked:
    `activities:read` for activities, `health:read` for health records, `health_targets:read` for the targets and
    `gears:read` for gear and components. A type asked for without its scope is `403`. A cursor older than
    90 days is `410` with `urn:endurain:error:sync-expired`: discard the local copy and sync from the start.
    Changes appear about two minutes after they happen.
    """
    return sync_service.sync(
        token_user_id,
        scopes,
        db,
        cursor=cursor,
        types=types,
        num_records=num_records or _DEFAULT_NUM_RECORDS,
        now=datetime.now(UTC),
    )
