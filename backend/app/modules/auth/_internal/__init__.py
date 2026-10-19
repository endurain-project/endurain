"""Private auth internals — the enforced-private plumbing of the auth package.

Modules here (credential hashing, token minting/verification, the principal
resolution dependencies, and the ephemeral security stores) are **private to the
``auth`` package**. The ``auth-boundary`` import-linter contract forbids any
non-auth module from importing ``modules.auth._internal`` directly: outside code must
consume identity through the public surface (``modules.auth.dependencies`` and
``modules.auth.identity_service.IdentityService``) instead.

Making privacy structural — a single ``_internal`` package rather than a growing
denylist of individual modules — is the point: what is public is now obvious from
the tree, and adding another internal module needs no import-linter change.
"""
