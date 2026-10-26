"""Realtime hint types a module may push through ``integration_service.push_to_user``.

A hint says that data changed; the client fetches the data through the normal API. The
notification hints live in :mod:`modules.notifications.constants`.
"""

#: A provider sync stored or changed the user's gear.
GEARS_CHANGED_MESSAGE = "GEARS_CHANGED"

#: A provider sync stored or changed the user's health data.
HEALTH_CHANGED_MESSAGE = "HEALTH_CHANGED"
