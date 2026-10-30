"""Email message builders for sign-up notifications."""

import html
from urllib.parse import quote as url_quote

import core.email_templates as core_email_templates
import core.i18n as core_i18n


def _verification_email(
    key_prefix: str,
    user_name: str,
    verification_link: str,
    frontend_host: str,
    locale: str | None,
) -> tuple[str, str, str]:
    """Build a localized email that asks the recipient to confirm their address through a link.

    Args:
        key_prefix: The catalog prefix holding the email's texts.
        user_name: The recipient's display name.
        verification_link: The URL that confirms the address.
        frontend_host: Base URL of the frontend, used in links and the footer.
        locale: Preferred locale code for the recipient.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """
    safe_name = html.escape(user_name)

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(f"{key_prefix}.{key}", locale, **kwargs)

    subject = tr("subject")
    heading = tr("heading")
    intro = tr("intro")
    cta = tr("cta")
    security_label = tr("security_label")
    security_notice = tr("security_notice")
    ignore = tr("ignore")
    copy_link = core_i18n.t("common.copy_link", locale)

    color = core_email_templates.LINK_COLOR_SUCCESS
    # Defense in depth: percent-encode then HTML-escape the link
    # before it lands in href and visible-text contexts.
    safe_verification_link = html.escape(url_quote(verification_link, safe=":/?=&%#@"), quote=True)

    body_inner = f"""
            <p>{tr("greeting", name=safe_name)}</p>
            <p>{intro}</p>
            <div style="text-align: center; margin: 30px 0;">
                <a
                    href="{safe_verification_link}"
                    style="background-color: {color}; color: #ffffff;
                    padding: 12px 30px; text-decoration: none;
                    border-radius: 8px; display: inline-block;
                    font-weight: 600;"
                >{cta}</a>
            </div>
            <div
                style="background-color: {core_email_templates.WARNING_BG};
                border: 1px solid {core_email_templates.WARNING_BORDER};
                color: {core_email_templates.WARNING_TEXT};
                padding: 15px; border-radius: 8px; margin: 20px 0;"
            >
                <strong>{security_label}</strong> {security_notice}
            </div>
            <p>{ignore}</p>
            <p>{copy_link}</p>
            <p style="word-break: break-all; color: {color};">{safe_verification_link}</p>"""

    html_content = core_email_templates.wrap_email(
        locale=locale,
        subject=subject,
        heading=heading,
        body_inner=body_inner,
        frontend_host=frontend_host,
        link_color=color,
    )

    labels = core_i18n.common_labels(locale)
    text_content = (
        f"{tr('greeting', name=user_name)}\n\n"
        f"{intro}\n"
        f"{verification_link}\n\n"
        f"{security_notice}\n\n"
        f"{ignore}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['team']}"
    )

    return subject, html_content, text_content


def get_signup_confirmation_email(
    user_name: str,
    signup_link: str,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """Build a localized sign-up confirmation email.

    Args:
        user_name: The recipient's display name.
        signup_link: The URL to confirm the account.
        frontend_host: Base URL of the frontend, used in links and the footer.
        locale: Preferred locale code for the recipient.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """
    return _verification_email("signup_confirmation", user_name, signup_link, frontend_host, locale)


def get_email_change_confirmation_email(
    user_name: str,
    verification_link: str,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """Build a localized email asking the recipient to confirm their changed email address.

    Args:
        user_name: The recipient's display name.
        verification_link: The URL that confirms the new address.
        frontend_host: Base URL of the frontend, used in links and the footer.
        locale: Preferred locale code for the recipient.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """
    return _verification_email("email_change_confirmation", user_name, verification_link, frontend_host, locale)


def mask_email(email: str) -> str:
    """Hide all but the first character of an address's local part, e.g. ``alice@example.org`` -> ``a***@example.org``.

    Args:
        email: The address to mask.

    Returns:
        The first character, ``***`` and the domain.
    """
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def get_email_changed_email(
    user_name: str,
    new_email: str,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """Build a localized notice, for the previous address, that the account's email address changed.

    The new address is shown masked, so the notice does not disclose it in full to the old inbox.

    Args:
        user_name: The recipient's display name.
        new_email: The address the account now uses.
        frontend_host: Base URL of the frontend, used in the footer.
        locale: Preferred locale code for the recipient.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """
    safe_name = html.escape(user_name)
    masked_email = mask_email(new_email)

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(f"email_changed.{key}", locale, **kwargs)

    subject = tr("subject")
    heading = tr("heading")
    safe_intro = tr("intro", new_email=html.escape(masked_email))
    security_label = tr("security_label")
    security_notice = tr("security_notice")

    body_inner = f"""
            <p>{tr("greeting", name=safe_name)}</p>
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
        f"{tr('intro', new_email=masked_email)}\n\n"
        f"{security_label} {security_notice}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['team']}"
    )

    return subject, html_content, text_content


def get_admin_signup_notification_email(
    user_name: str,
    sign_up_user_name: str,
    sign_up_user_username: str,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """Build a localized admin notification email.

    Args:
        user_name: Display name of the admin recipient.
        sign_up_user_name: Display name of the signed-up user.
        sign_up_user_username: Username of the signed-up user.
        frontend_host: Base URL of the frontend, used in links and the footer.
        locale: Preferred locale code for the admin recipient.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """
    safe_name = html.escape(user_name)
    safe_sign_up_name = html.escape(sign_up_user_name)

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(key, locale, **kwargs)

    subject = tr("admin_signup.subject")
    heading = tr("admin_signup.heading")
    intro = tr("admin_signup.intro")
    user_label = tr("admin_signup.user_label")
    review = tr("admin_signup.review")
    cta = tr("admin_signup.cta")
    copy_link = tr("common.copy_link")

    color = core_email_templates.LINK_COLOR_SUCCESS

    # URL-encode username for query-string safety, then HTML-escape
    # the assembled URL before placing it into href and text contexts.
    encoded_username = url_quote(sign_up_user_username, safe="")
    admin_link = f"{frontend_host}/settings?tab=users&username={encoded_username}"
    safe_admin_link = html.escape(admin_link, quote=True)

    body_inner = f"""
            <p>{tr("admin_signup.greeting", name=safe_name)}</p>
            <p>{intro}</p>
            <div
                style="background-color: {core_email_templates.INFO_BG};
                border: 1px solid {core_email_templates.INFO_BORDER};
                color: {core_email_templates.INFO_TEXT}; padding: 15px;
                border-radius: 8px; margin: 20px 0;"
            >
                <strong>{user_label}</strong> {safe_sign_up_name}
            </div>
            <p>{review}</p>
            <div style="text-align: center; margin: 30px 0;">
                <a
                    href="{safe_admin_link}"
                    style="background-color: {color}; color: #ffffff;
                    padding: 12px 30px; text-decoration: none;
                    border-radius: 8px; display: inline-block;
                    font-weight: 600;"
                >{cta}</a>
            </div>
            <p>{copy_link}</p>
            <p style="word-break: break-all; color: {color};">{safe_admin_link}</p>"""

    html_content = core_email_templates.wrap_email(
        locale=locale,
        subject=subject,
        heading=heading,
        body_inner=body_inner,
        frontend_host=frontend_host,
        link_color=color,
        sign_off_key="system",
    )

    labels = core_i18n.common_labels(locale)
    text_content = (
        f"{tr('admin_signup.greeting', name=user_name)}\n\n"
        f"{intro}\n"
        f"{user_label} {sign_up_user_name}\n\n"
        f"{review}\n"
        f"{admin_link}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['system']}"
    )

    return subject, html_content, text_content


def get_user_signup_approved_email(
    sign_up_user_name: str,
    sign_up_user_username: str,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """Build a localized account-approved notification email.

    Args:
        sign_up_user_name: Display name of the approved user.
        sign_up_user_username: Username of the approved user.
        frontend_host: Base URL of the frontend, used in links and the footer.
        locale: Preferred locale code for the approved user.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """
    safe_name = html.escape(sign_up_user_name)
    safe_username = html.escape(sign_up_user_username)

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(key, locale, **kwargs)

    subject = tr("signup_approved.subject")
    heading = tr("signup_approved.heading")
    intro = tr("signup_approved.intro")
    username_label = tr("signup_approved.username_label")
    login_intro = tr("signup_approved.login_intro")
    cta = tr("signup_approved.cta")
    copy_link = tr("common.copy_link")

    color = core_email_templates.LINK_COLOR_SUCCESS
    login_link = f"{frontend_host}/login"
    # Defense in depth: HTML-escape before insertion into HTML contexts.
    safe_login_link = html.escape(login_link, quote=True)

    body_inner = f"""
            <p>{tr("signup_approved.greeting", name=safe_name)}</p>
            <p>{intro}</p>
            <div
                style="background-color: {core_email_templates.INFO_BG};
                border: 1px solid {core_email_templates.INFO_BORDER};
                color: {core_email_templates.INFO_TEXT}; padding: 15px;
                border-radius: 8px; margin: 20px 0;"
            >
                <strong>{username_label}</strong> {safe_username}
            </div>
            <p>{login_intro}</p>
            <div style="text-align: center; margin: 30px 0;">
                <a
                    href="{safe_login_link}"
                    style="background-color: {color}; color: #ffffff;
                    padding: 12px 30px; text-decoration: none;
                    border-radius: 8px; display: inline-block;
                    font-weight: 600;"
                >{cta}</a>
            </div>
            <p>{copy_link}</p>
            <p style="word-break: break-all; color: {color};">{safe_login_link}</p>"""

    html_content = core_email_templates.wrap_email(
        locale=locale,
        subject=subject,
        heading=heading,
        body_inner=body_inner,
        frontend_host=frontend_host,
        link_color=color,
    )

    labels = core_i18n.common_labels(locale)
    text_content = (
        f"{tr('signup_approved.greeting', name=sign_up_user_name)}\n\n"
        f"{intro}\n"
        f"{username_label} {sign_up_user_username}\n\n"
        f"{login_intro}\n"
        f"{login_link}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['team']}"
    )

    return subject, html_content, text_content


def get_existing_account_email(
    user_name: str,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """Build a localized notice that someone signed up with an existing account's email.

    Args:
        user_name: Display name of the existing account's owner.
        frontend_host: Base URL of the frontend, used in links and the footer.
        locale: Preferred locale code for the owner.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """
    safe_name = html.escape(user_name)

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(key, locale, **kwargs)

    subject = tr("signup_existing_account.subject")
    heading = tr("signup_existing_account.heading")
    intro = tr("signup_existing_account.intro")
    login_intro = tr("signup_existing_account.login_intro")
    cta = tr("signup_existing_account.cta")
    ignore = tr("signup_existing_account.ignore")
    copy_link = tr("common.copy_link")

    color = core_email_templates.LINK_COLOR_SUCCESS
    login_link = f"{frontend_host}/login"
    safe_login_link = html.escape(login_link, quote=True)

    body_inner = f"""
            <p>{tr("signup_existing_account.greeting", name=safe_name)}</p>
            <p>{intro}</p>
            <p>{login_intro}</p>
            <div style="text-align: center; margin: 30px 0;">
                <a
                    href="{safe_login_link}"
                    style="background-color: {color}; color: #ffffff;
                    padding: 12px 30px; text-decoration: none;
                    border-radius: 8px; display: inline-block;
                    font-weight: 600;"
                >{cta}</a>
            </div>
            <p>{ignore}</p>
            <p>{copy_link}</p>
            <p style="word-break: break-all; color: {color};">{safe_login_link}</p>"""

    html_content = core_email_templates.wrap_email(
        locale=locale,
        subject=subject,
        heading=heading,
        body_inner=body_inner,
        frontend_host=frontend_host,
        link_color=color,
    )

    labels = core_i18n.common_labels(locale)
    text_content = (
        f"{tr('signup_existing_account.greeting', name=user_name)}\n\n"
        f"{intro}\n"
        f"{login_intro}\n"
        f"{login_link}\n\n"
        f"{ignore}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['team']}"
    )

    return subject, html_content, text_content
