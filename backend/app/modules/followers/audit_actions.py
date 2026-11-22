"""Audit actions written by the followers package: changes to who can see a user's data.

Ids are stable forever: rows outlive the code.
"""

import jasil.audit as jasil_audit

FOLLOW_ACCEPT = jasil_audit.AuditAction(
    id="followers.follow.accept",
    category=jasil_audit.Category.AUTHORIZATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.followers.follow.accept",
    description_default="A follow request was accepted",
)

FOLLOW_REMOVE = jasil_audit.AuditAction(
    id="followers.follow.remove",
    category=jasil_audit.Category.AUTHORIZATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.followers.follow.remove",
    description_default="An accepted follow relationship was removed",
)

BLOCK_ADD = jasil_audit.AuditAction(
    id="followers.block.add",
    category=jasil_audit.Category.AUTHORIZATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.followers.block.add",
    description_default="A user was blocked",
)

BLOCK_REMOVE = jasil_audit.AuditAction(
    id="followers.block.remove",
    category=jasil_audit.Category.AUTHORIZATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.followers.block.remove",
    description_default="A user was unblocked",
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (FOLLOW_ACCEPT, FOLLOW_REMOVE, BLOCK_ADD, BLOCK_REMOVE)
