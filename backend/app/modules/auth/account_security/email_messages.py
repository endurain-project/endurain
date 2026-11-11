"""Email message builders for account-security change, new-device sign-in and administrator-promotion notices."""

import html
from datetime import datetime

import core.email_templates as core_email_templates
import core.i18n as core_i18n
import modules.auth.account_security.events as account_security_events
import modules.auth.known_devices.events as known_devices_events

# Reported by the identity-provider link event, not by an account-security change.
IDENTITY_PROVIDER_LINKED = "identity_provider_linked"

_CHANGES = frozenset(change.value for change in account_security_events.AccountSecurityChange) | {
    IDENTITY_PROVIDER_LINKED
}
# The notice that follows the intro, for the changes whose advice is not "reset your password".
_NOTICE_KEYS = {
    account_security_events.AccountSecurityChange.PASSWORD_SET_BY_ADMIN.value: "security_notice_admin",
    account_security_events.AccountSecurityChange.MFA_RESET_BY_ADMIN.value: "security_notice_admin",
    account_security_events.AccountSecurityChange.PASSWORD_CHANGE_REQUIRED_BY_ADMIN.value: "security_notice_admin",
    account_security_events.AccountSecurityChange.API_KEYS_REVOKED_BY_ADMIN.value: "security_notice_admin",
    account_security_events.AccountSecurityChange.ACCOUNT_LOCKED.value: "security_notice_account_locked",
    account_security_events.AccountSecurityChange.MFA_LOCKED.value: "security_notice_mfa_locked",
    account_security_events.AccountSecurityChange.ROLE_CHANGED_BY_ADMIN.value: "security_notice_admin",
    account_security_events.AccountSecurityChange.ACCOUNT_DEACTIVATED_BY_ADMIN.value: "security_notice_admin",
    account_security_events.AccountSecurityChange.ACCOUNT_DELETION_REQUESTED.value: "security_notice_admin",
    account_security_events.AccountSecurityChange.REFRESH_TOKEN_REUSE_DETECTED.value: "security_notice_session",
    account_security_events.AccountSecurityChange.STEP_UP_SESSION_ENDED.value: "security_notice_session",
    account_security_events.AccountSecurityChange.STEP_UP_LOCKED.value: "security_notice_step_up_locked",
    account_security_events.AccountSecurityChange.BACKUP_CODE_USED.value: "security_notice_backup_code",
}
# The changes that also end the account's API keys and pending email change, which the notice says.
_RECOVERY_CHANGES = frozenset(
    {
        account_security_events.AccountSecurityChange.PASSWORD_RESET.value,
        account_security_events.AccountSecurityChange.PASSWORD_SET_BY_ADMIN.value,
    }
)
# The access types a role-change notice names; any other value gets the notice that names none.
_ACCESS_TYPES = frozenset({"admin", "regular"})
_PROVIDER_CHANGES = frozenset(
    {IDENTITY_PROVIDER_LINKED, account_security_events.AccountSecurityChange.IDENTITY_PROVIDER_UNLINKED.value}
)


def get_account_security_changed_email(
    user_name: str,
    change: str,
    idp_name: str | None,
    frontend_host: str,
    locale: str | None = None,
    *,
    access_type: str | None = None,
    backup_codes_remaining: int | None = None,
) -> tuple[str, str, str]:
    """Build a localized notice that a security setting of the account changed.

    The notice never carries a secret: it names what changed and what to do if the recipient did not do it.

    Args:
        user_name: The recipient's display name.
        change: The kind of change, an ``AccountSecurityChange`` value or ``IDENTITY_PROVIDER_LINKED``.
        idp_name: The identity provider's name for a link or unlink, or None when it no longer exists.
        frontend_host: Base URL of the frontend, used in the footer.
        locale: Preferred locale code for the recipient.
        access_type: The access type the account now has, for a role change.
        backup_codes_remaining: How many unused backup codes are left, for a backup code that was used.

    Returns:
        A 3-tuple of (subject, html_content, text_content).

    Raises:
        ValueError: When the change is not a known one.
    """
    if change not in _CHANGES:
        raise ValueError(f"Unknown account-security change: {change}")

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(f"security_change.{key}", locale, **kwargs)

    if change in _PROVIDER_CHANGES and idp_name is not None:
        intro = tr(f"{change}.intro_named", provider=idp_name)
        safe_intro = tr(f"{change}.intro_named", provider=html.escape(idp_name))
    elif change == account_security_events.AccountSecurityChange.ROLE_CHANGED_BY_ADMIN and access_type in _ACCESS_TYPES:
        intro = safe_intro = tr(f"{change}.intro_{access_type}")
    else:
        intro = safe_intro = tr(f"{change}.intro")
    if change == account_security_events.AccountSecurityChange.BACKUP_CODE_USED and backup_codes_remaining is not None:
        remaining = (
            tr(f"{change}.remaining", count=str(backup_codes_remaining))
            if backup_codes_remaining > 0
            else tr(f"{change}.remaining_none")
        )
        intro = safe_intro = f"{intro} {remaining}"

    subject = tr(f"{change}.subject")
    heading = tr(f"{change}.heading")
    security_label = tr("security_label")
    security_notice = tr(_NOTICE_KEYS.get(change, "security_notice"))
    recovery_effects = tr("recovery_effects") if change in _RECOVERY_CHANGES else ""
    recovery_html = f"<p>{recovery_effects}</p>" if recovery_effects else ""
    recovery_text = f"{recovery_effects}\n\n" if recovery_effects else ""

    body_inner = f"""
            <p>{tr("greeting", name=html.escape(user_name))}</p>
            <p>{safe_intro}</p>
            {recovery_html}
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
        f"{recovery_text}"
        f"{security_label} {security_notice}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['team']}"
    )

    return subject, html_content, text_content


def get_new_device_sign_in_email(
    user_name: str,
    browser: str,
    operating_system: str,
    ip_address: str,
    method: str,
    signed_in_at: datetime,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """Build a localized notice that the account was signed in to from a new device.

    Args:
        user_name: The recipient's display name.
        browser: The browser family the sign-in's user agent names.
        operating_system: The operating-system family the sign-in's user agent names.
        ip_address: The client address of the sign-in.
        method: How the user signed in, a ``SignInMethod`` value.
        signed_in_at: When the sign-in happened, in the timezone the recipient reads it in.
        frontend_host: Base URL of the frontend, used in the footer.
        locale: Preferred locale code for the recipient.

    Returns:
        A 3-tuple of (subject, html_content, text_content).

    Raises:
        ValueError: When the method is not a known one.
    """
    if method not in known_devices_events.SignInMethod:
        raise ValueError(f"Unknown sign-in method: {method}")

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(f"new_device_sign_in.{key}", locale, **kwargs)

    subject = tr("subject")
    heading = tr("heading")
    intro = tr("intro")
    when = signed_in_at.strftime("%Y-%m-%d %H:%M %Z")
    device = tr("device", browser=browser, operating_system=operating_system)
    safe_device = tr("device", browser=html.escape(browser), operating_system=html.escape(operating_system))
    method_name = tr(f"method.{method}")
    details = (
        (tr("time_label"), when, html.escape(when)),
        (tr("device_label"), device, safe_device),
        (tr("ip_label"), ip_address, html.escape(ip_address)),
        (tr("method_label"), method_name, method_name),
    )
    security_label = core_i18n.t("security_change.security_label", locale)
    security_notice = tr("security_notice")
    greeting = core_i18n.t("security_change.greeting", locale, name=user_name)
    safe_greeting = core_i18n.t("security_change.greeting", locale, name=html.escape(user_name))

    detail_lines = "<br>".join(f"<strong>{label}</strong> {safe_value}" for label, _, safe_value in details)
    body_inner = f"""
            <p>{safe_greeting}</p>
            <p>{intro}</p>
            <div
                style="background-color: {core_email_templates.INFO_BG};
                border: 1px solid {core_email_templates.INFO_BORDER};
                color: {core_email_templates.INFO_TEXT};
                padding: 15px; border-radius: 8px; margin: 20px 0;"
            >
                {detail_lines}
            </div>
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
    detail_text = "\n".join(f"{label} {value}" for label, value, _ in details)
    text_content = (
        f"{greeting}\n\n"
        f"{intro}\n\n"
        f"{detail_text}\n\n"
        f"{security_label} {security_notice}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['team']}"
    )

    return subject, html_content, text_content


def get_admin_promoted_email(
    admin_name: str,
    user_name: str,
    username: str,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """Build a localized notice to an administrator that a user was given administrator access.

    Args:
        admin_name: The recipient administrator's display name.
        user_name: The promoted user's display name.
        username: The promoted user's username.
        frontend_host: Base URL of the frontend, used in the footer.
        locale: Preferred locale code for the recipient.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(f"admin_promoted.{key}", locale, **kwargs)

    subject = tr("subject")
    heading = tr("heading")
    intro = tr("intro", name=user_name, username=username)
    safe_intro = tr("intro", name=html.escape(user_name), username=html.escape(username))
    security_label = core_i18n.t("security_change.security_label", locale)
    security_notice = tr("security_notice")
    greeting = core_i18n.t("security_change.greeting", locale, name=admin_name)
    safe_greeting = core_i18n.t("security_change.greeting", locale, name=html.escape(admin_name))

    body_inner = f"""
            <p>{safe_greeting}</p>
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
        f"{greeting}\n\n{intro}\n\n{security_label} {security_notice}\n\n{labels['best_regards']}\n{labels['team']}"
    )

    return subject, html_content, text_content
