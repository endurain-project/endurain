"""Email message builders for account-security change notices."""

import html

import core.email_templates as core_email_templates
import core.i18n as core_i18n
import modules.auth.account_security.events as account_security_events

# Reported by the identity-provider link event, not by an account-security change.
IDENTITY_PROVIDER_LINKED = "identity_provider_linked"

_CHANGES = frozenset(change.value for change in account_security_events.AccountSecurityChange) | {
    IDENTITY_PROVIDER_LINKED
}
_PROVIDER_CHANGES = frozenset(
    {IDENTITY_PROVIDER_LINKED, account_security_events.AccountSecurityChange.IDENTITY_PROVIDER_UNLINKED.value}
)


def get_account_security_changed_email(
    user_name: str,
    change: str,
    idp_name: str | None,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """Build a localized notice that a security setting of the account changed.

    The notice never carries a secret: it names what changed and what to do if the recipient did not do it.

    Args:
        user_name: The recipient's display name.
        change: The kind of change, an ``AccountSecurityChange`` value or ``IDENTITY_PROVIDER_LINKED``.
        idp_name: The identity provider's name for a link or unlink, or None when it no longer exists.
        frontend_host: Base URL of the frontend, used in the footer.
        locale: Preferred locale code for the recipient.

    Returns:
        A 3-tuple of (subject, html_content, text_content).

    Raises:
        ValueError: When the change is not a known one.
    """
    if change not in _CHANGES:
        raise ValueError(f"Unknown account-security change: {change}")

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(f"security_change.{key}", locale, **kwargs)

    named = change in _PROVIDER_CHANGES and idp_name is not None
    if named:
        intro = tr(f"{change}.intro_named", provider=idp_name)
        safe_intro = tr(f"{change}.intro_named", provider=html.escape(idp_name))
    else:
        intro = safe_intro = tr(f"{change}.intro")

    subject = tr(f"{change}.subject")
    heading = tr(f"{change}.heading")
    security_label = tr("security_label")
    notice_key = (
        "security_notice_admin"
        if change == account_security_events.AccountSecurityChange.PASSWORD_SET_BY_ADMIN
        else "security_notice"
    )
    security_notice = tr(notice_key)

    body_inner = f"""
            <p>{tr("greeting", name=html.escape(user_name))}</p>
            <p>{safe_intro}</p>
            <div
                style="background-color: {core_email_templates.WARNING_BG};
                border: 1px solid {core_email_templates.WARNING_BORDER};
                color: {core_email_templates.WARNING_TEXT};
                padding: 15px; border-radius: 8px; margin: 20px 0;"
            >
                <strong>{security_label}</strong> {security_notice}
            </div>"""

    html_content = core_email_templates.wrap_email(
        locale=locale,
        subject=subject,
        heading=heading,
        body_inner=body_inner,
        frontend_host=frontend_host,
        link_color=core_email_templates.LINK_COLOR_SUCCESS,
    )

    labels = core_i18n.common_labels(locale)
    text_content = (
        f"{tr('greeting', name=user_name)}\n\n"
        f"{intro}\n\n"
        f"{security_label} {security_notice}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['team']}"
    )

    return subject, html_content, text_content
