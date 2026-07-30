"""Email message builders for password reset notifications."""

import html
from urllib.parse import quote as url_quote

import core.apprise as core_apprise
import core.email_templates as core_email_templates
import core.i18n as core_i18n


def get_password_reset_email(
    user_name: str,
    reset_link: str,
    email_service: core_apprise.AppriseService,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """
    Build a localized password reset email.

    Args:
        user_name: The recipient's display name.
        reset_link: The URL for resetting the password.
        email_service: AppriseService for footer metadata.
        locale: Preferred locale code for the recipient. Falls back
            to ``"en"`` if unsupported or ``None``.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """
    safe_name = html.escape(user_name)

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(key, locale, **kwargs)

    subject = tr("password_reset.subject")
    heading = tr("password_reset.heading")
    intro = tr("password_reset.intro")
    cta = tr("password_reset.cta")
    security_label = tr("password_reset.security_label")
    security_notice = tr("password_reset.security_notice")
    ignore = tr("password_reset.ignore")
    copy_link = tr("common.copy_link")

    color = core_email_templates.LINK_COLOR_PRIMARY
    # Defense in depth: percent-encode the URL, then HTML-escape it
    # before placing it into href and <p> contexts so a future change
    # that puts user-controlled data into the link cannot break out.
    safe_reset_link = html.escape(url_quote(reset_link, safe=":/?=&%#@"), quote=True)

    body_inner = f"""
            <p>{tr("password_reset.greeting", name=safe_name)}</p>
            <p>{intro}</p>
            <div style="text-align: center; margin: 30px 0;">
                <a
                    href="{safe_reset_link}"
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
            <p style="word-break: break-all; color: {color};">{safe_reset_link}</p>"""

    html_content = core_email_templates.wrap_email(
        locale=locale,
        subject=subject,
        heading=heading,
        body_inner=body_inner,
        frontend_host=email_service.frontend_host,
        link_color=color,
    )

    labels = core_i18n.common_labels(locale)
    text_content = (
        f"{tr('password_reset.greeting', name=user_name)}\n\n"
        f"{intro}\n"
        f"{reset_link}\n\n"
        f"{security_notice}\n\n"
        f"{ignore}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['team']}"
    )

    return subject, html_content, text_content
