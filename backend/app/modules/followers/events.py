"""Domain event channels owned by the followers module.

Channel names (``event_type`` values) are owned by the publishing domain, not the
platform substrate. The follow service publishes the facts below; the follower
notification subscriber reacts by subscribing to the same constants, so producer
and subscriber cannot drift on the string. Convention: ``<domain>.<fact>``, past
tense.
"""

# Published after a follow-request row has been created (a user requests to
# follow another user), so the target user can be notified.
FOLLOWER_REQUESTED = "follower.requested"

# Published after a pending follow request has been accepted, so the original
# requester can be notified that their request was accepted.
FOLLOWER_ACCEPTED = "follower.accepted"
