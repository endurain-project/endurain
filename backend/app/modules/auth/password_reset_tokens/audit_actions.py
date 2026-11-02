"""Audit actions written by the password-reset package.

Ids are stable forever: rows outlive the code. No ``details``: the row's target names the user, and a reset
token or the address it was requested for never reaches the trail.
"""

import jasil.audit as jasil_audit

PASSWORD_RESET = jasil_audit.AuditAction(
    id="auth.password.reset",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.password.reset",
    description_default="A password was reset with an emailed link",
)

PASSWORD_RESET_REQUEST = jasil_audit.AuditAction(
    id="auth.password_reset.request",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.auth.password_reset.request",
    description_default="A password reset link was requested",
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (PASSWORD_RESET, PASSWORD_RESET_REQUEST)
