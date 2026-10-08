"""Shared HTML email template helpers for all Endurain email builders."""

import html

import core.i18n as core_i18n

# Endurain brand palette (light surface), mirrored from the frontend design
# tokens in frontend/src/assets/main.css so transactional emails match the UI.
BRAND_PRIMARY = "#1d9e75"  # --primary           (brand green)
BRAND_PRIMARY_DARK = "#0f6e56"  # --secondary-foreground (brand mid)
BRAND_FOREGROUND = "#2c2c2a"  # --foreground        (body text)
BRAND_BACKGROUND = "#f1efe8"  # --background        (page backdrop)
BRAND_MUTED_FOREGROUND = "#888780"  # --muted-foreground  (footer text)
BRAND_BORDER = "#e2e0d8"  # subtle hairline border

# The new Endurain brand is green throughout, so every transactional email
# shares one accent colour (previously Bootstrap blue/green per flow).
LINK_COLOR_PRIMARY = BRAND_PRIMARY  # password reset
LINK_COLOR_SUCCESS = BRAND_PRIMARY  # sign-up flows

# Inline notice-box palettes used by the email body builders.
WARNING_BG = "#fdf3e3"  # soft amber surface for security notices
WARNING_BORDER = "#f3dcae"
WARNING_TEXT = "#92570a"
INFO_BG = "#e1f5ee"  # brand secondary tint for informational details
INFO_BORDER = "#bfe6d8"
INFO_TEXT = BRAND_PRIMARY_DARK

_LOGO_URL = "https://raw.githubusercontent.com/endurain-project/endurain/master/frontend/public/logo_light.png"


def html_header(title: str, heading: str, lang: str = "en") -> str:
    """
    Return the opening HTML block shared by all Endurain emails.

    Includes the doctype, ``<head>``, ``<body>`` wrapper, branded logo
    header with ``heading``, and the opening tag of the content
    ``<div>`` that callers must fill and then close with
    :func:`html_footer`.

    Args:
        title: Value placed in ``<title>`` (typically the email
            subject).
        heading: Text rendered inside the ``<h3>`` below the logo.
        lang: BCP 47 language tag for the ``<html lang>`` attribute.
            Defaults to ``"en"``.

    Returns:
        A partial HTML string ending with an open ``<div
        style="margin-bottom: 30px;">``.
    """
    return f"""\
<!DOCTYPE html>
<html lang="{lang}">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>

<body
    style="font-family: 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.6; color: {BRAND_FOREGROUND}; max-width: 600px;
    margin: 0 auto; padding: 20px;
    background-color: {BRAND_BACKGROUND};"
>
    <div
        style="background-color: #ffffff; padding: 30px;
        border-radius: 12px; border: 1px solid {BRAND_BORDER};
        box-shadow: 0 2px 10px rgba(15, 110, 86, 0.08);"
    >
        <div style="text-align: center; margin-bottom: 30px;">
            <div
                style="font-size: 30px; font-weight: 600;
                margin-bottom: 10px; display: flex; align-items: center;
                justify-content: center; gap: 10px;
                color: {BRAND_PRIMARY_DARK};"
            >
                <img src="{_LOGO_URL}"
                    alt="Endurain logo" style="height: 32px; width: auto;">
                <span>Endurain</span>
            </div>
            <h3 style="margin: 0; font-weight: 600;
                color: {BRAND_FOREGROUND};">{heading}</h3>
        </div>

        <div style="margin-bottom: 30px;">"""


def html_footer(
    frontend_host: str,
    link_color: str,
    best_regards: str = "Best regards,",
    sign_off: str = "The Endurain team",
    visit_label: str = "Visit Endurain at:",
    source_code_label: str = "Source code at:",
) -> str:
    """
    Return the closing HTML block shared by all Endurain emails.

    Closes the content ``<div>`` opened by :func:`html_header`,
    renders the footer with a sign-off greeting and links to the
    frontend host and the GitHub repository, then closes the outer
    wrapper, ``<body>``, and ``<html>``.

    Args:
        frontend_host: Base URL of the Endurain frontend, shown in
            the footer link.
        link_color: CSS colour string applied to all footer anchor
            tags. Use module-level constants
            :data:`LINK_COLOR_PRIMARY` or
            :data:`LINK_COLOR_SUCCESS` for consistency.
        best_regards: Localized salutation line.
            Defaults to ``"Best regards,"``.
        sign_off: Localized team or system name for the sign-off.
            Defaults to ``"The Endurain team"``.
        visit_label: Localized label before the frontend URL.
            Defaults to ``"Visit Endurain at:"``.
        source_code_label: Localized label before the repo link.
            Defaults to ``"Source code at:"``.

    Returns:
        A partial HTML string that closes all tags opened by
        :func:`html_header`.
    """
    return f"""
        </div>

        <div
            style="text-align: center; font-size: 12px;
            color: {BRAND_MUTED_FOREGROUND}; margin-top: 30px;
            padding-top: 20px; border-top: 1px solid {BRAND_BORDER};"
        >
            <p>{best_regards}<br>{sign_off}</p>
            <p>
                {visit_label}
                <a style="color: {link_color};" href="{frontend_host}">
                    {frontend_host}
                </a> - {source_code_label}
                <a
                    style="color: {link_color};"
                    href="https://github.com/endurain-project/endurain"
                >
                    GitHub
                </a>
            </p>
        </div>
    </div>
</body>

</html>"""


def wrap_email(
    *,
    locale: str | None,
    subject: str,
    heading: str,
    body_inner: str,
    frontend_host: str,
    link_color: str,
    sign_off_key: str = "team",
) -> str:
    """
    Render a complete localized email by wrapping ``body_inner`` in the
    shared header/footer chrome.

    Centralizes the boilerplate that every email builder used to repeat
    (HTML escaping of header/footer fields, fetching the six common
    catalog labels, computing the BCP 47 ``lang`` tag, and threading
    them into :func:`html_header` and :func:`html_footer`).

    Args:
        locale: Raw recipient locale string or None.
        subject: Pre-translated subject line. Will be HTML-escaped
            before insertion into ``<title>``.
        heading: Pre-translated ``<h3>`` heading. Will be HTML-escaped.
        body_inner: HTML fragment for the email body. The caller is
            responsible for escaping any user-controlled values inside
            this fragment.
        frontend_host: Base URL of the Endurain frontend. Will be
            HTML-escaped before use in attribute and text contexts.
        link_color: CSS colour for footer anchors (use
            :data:`LINK_COLOR_PRIMARY` or :data:`LINK_COLOR_SUCCESS`).
        sign_off_key: Which common label to use as the sign-off; one
            of ``"team"`` or ``"system"``. Defaults to ``"team"``.

    Returns:
        A complete HTML document string.
    """
    labels = core_i18n.common_labels(locale)
    sign_off = labels.get(sign_off_key, labels["team"])
    lang = core_i18n.html_lang(locale)
    safe_host = html.escape(frontend_host, quote=True)

    return (
        html_header(html.escape(subject), html.escape(heading), lang)
        + body_inner
        + html_footer(
            frontend_host=safe_host,
            link_color=link_color,
            best_regards=labels["best_regards"],
            sign_off=sign_off,
            visit_label=labels["visit"],
            source_code_label=labels["source_code"],
        )
    )
