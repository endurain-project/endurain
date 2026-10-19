"""Domain metadata keys stamped onto published events.

JASIL owns only ``META_REQUEST_ID``: the correlation id is the substrate's
business, and every other key in an event's ``metadata`` belongs to the
application. These are the keys more than one module writes, so they live here
rather than in whichever module happened to need them first — otherwise
``followers`` would import ``activities`` for the sake of a shared string.
"""

#: Id of the activity an event concerns.
META_ACTIVITY_ID = "activity_id"

#: Id of the user an event concerns.
META_USER_ID = "user_id"
