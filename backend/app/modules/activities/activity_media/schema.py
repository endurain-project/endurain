"""Pydantic schemas for activity media."""

import core.pagination as core_pagination
import modules.activities.activity.schema as activity_schema


class ActivityMediaRead(activity_schema.ActivityMediaEmbedded):
    """A photo attached to an activity, as returned to a client.

    Read-only by construction: every field is populated for a media record that
    exists, so none is optional. The stored ``StorageProvider`` key is
    deliberately absent — it is not an address, and a client has nothing to do
    with it; see :class:`~modules.activities.activity_media.contracts.ActivityMediaRecord`.
    """


#: One page of an activity's media, the same envelope every child collection returns.
ActivityMediaPage = core_pagination.Page[ActivityMediaRead]
