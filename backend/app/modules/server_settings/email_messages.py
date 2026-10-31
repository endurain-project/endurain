"""Email message builder for the server-settings test email."""

import html

import core.email_templates as core_email_templates
import core.i18n as core_i18n


def get_test_email(
    user_name: str,
    smtp_server: str,
    frontend_host: str,
    locale: str | None = None,
) -> tuple[str, str, str]:
    """
    Build a localized test email.

    Args:
        user_name: The recipient's display name.
        smtp_server: ``host:port`` of the configured SMTP server.
        frontend_host: Base URL of the frontend, used in the footer.
        locale: Preferred locale code for the recipient.

    Returns:
        A 3-tuple of (subject, html_content, text_content).
    """

    def tr(key: str, **kwargs: str) -> str:
        return core_i18n.t(key, locale, **kwargs)

    subject = tr("test_email.subject")
    heading = tr("test_email.heading")
    intro = tr("test_email.intro")
    detail_label = tr("test_email.detail_label")
    ignore = tr("test_email.ignore")

    color = core_email_templates.LINK_COLOR_PRIMARY
    body_inner = f"""
            <p>{tr("test_email.greeting", name=html.escape(user_name))}</p>
            <p>{intro}</p>
            <div
                style="background-color: {core_email_templates.INFO_BG};
                border: 1px solid {core_email_templates.INFO_BORDER};
                color: {core_email_templates.INFO_TEXT};
                padding: 15px; border-radius: 8px; margin: 20px 0;"
            >
                <strong>{detail_label}</strong> {html.escape(smtp_server)}
            </div>
            <p>{ignore}</p>"""

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
        f"{tr('test_email.greeting', name=user_name)}\n\n"
        f"{intro}\n"
        f"{detail_label} {smtp_server}\n\n"
        f"{ignore}\n\n"
        f"{labels['best_regards']}\n"
        f"{labels['system']}"
    )

    return subject, html_content, text_content
