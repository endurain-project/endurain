"""Audit actions written by the password-reset package.

Ids are stable forever: rows outlive the code. No ``details``: the row's target names the user, and a reset
token never reaches the trail.
"""

import jasil.audit as jasil_audit

PASSWORD_RESET = jasil_audit.AuditAction(
    id="auth.password.reset",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.password.reset",
    description_default="A password was reset with an emailed link",
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (PASSWORD_RESET,)
