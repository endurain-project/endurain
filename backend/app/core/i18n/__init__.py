"""Backend localization helpers for transactional emails.

Translation catalogs are JSON files shipped in ``locales/<code>/email.json``
relative to this package. Catalogs are trusted source-controlled content and
must never be sourced from user input — :func:`t` calls ``str.format`` on
catalog values, which would otherwise allow attribute traversal attacks.
"""

import functools
import json
import pathlib
from typing import Final

import core.logger as core_logger

logger = core_logger.get_logger(__name__)

DEFAULT_LOCALE: Final[str] = "en"


def _load_supported_locales() -> frozenset[str]:
    """
    Derive the set of supported locales from the ``Language`` enum.

    Lazy import avoids a circular import at ``core`` package load time
    (``modules.users.users.schema`` transitively imports auth/CRUD modules
    that require runtime configuration such as ``SECRET_KEY``).

    Returns:
        Frozen set of locale code strings.
    """
    from modules.users.users.schema import Language

    return frozenset(language.value for language in Language)


# Cached holder so the enum import only happens once, on first access.
_supported_locales_cache: frozenset[str] | None = None


def _supported() -> frozenset[str]:
    """
    Return the cached set of supported locales (lazy).

    Used internally; external callers should read
    ``core.i18n.SUPPORTED_LOCALES`` (resolved by ``__getattr__``).
    """
    global _supported_locales_cache
    if _supported_locales_cache is None:
        _supported_locales_cache = _load_supported_locales()
    return _supported_locales_cache


def __getattr__(name: str) -> frozenset[str]:
    """
    Module-level ``__getattr__`` (PEP 562) that lazily exposes
    :data:`SUPPORTED_LOCALES`.

    Defers importing :class:`modules.users.users.schema.Language` until the
    constant is actually read so simply importing ``core.i18n`` cannot
    trigger the heavy ``users`` / ``auth`` import chain.
    """
    if name == "SUPPORTED_LOCALES":
        return _supported()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# BCP 47 language tags for each supported locale. Region subtags are
# included for every locale so the HTML ``lang`` attribute is consistent
# across emails. Keep this table in sync when ``Language`` gains entries.
HTML_LANG_BY_LOCALE: Final[dict[str, str]] = {
    "en": "en-US",
    "pt-PT": "pt-PT",
    "zh-Hans": "zh-Hans",
    "zh-Hant": "zh-Hant",
    "ca": "ca-ES",
    "de": "de-DE",
    "fr": "fr-FR",
    "gl": "gl-ES",
    "it": "it-IT",
    "nl": "nl-NL",
    "sl": "sl-SI",
    "sv": "sv-SE",
    "es": "es-ES",
    "pl": "pl-PL",
    "tr": "tr-TR",
    "uk": "uk-UA",
    "ro": "ro-RO",
    "nb": "nb-NO",
    "da": "da-DK",
    "fi": "fi-FI",
    "cs": "cs-CZ",
    "el": "el-GR",
    "hu": "hu-HU",
    "bg": "bg-BG",
    "hr": "hr-HR",
    "sr": "sr-RS",
    "sk": "sk-SK",
    "lt": "lt-LT",
    "lv": "lv-LV",
    "et": "et-EE",
}

_LOCALES_DIR = pathlib.Path(__file__).parent / "locales"

# Catalog keys whose values are reused by every email body. Centralized
# here so :func:`common_labels` is the single source of truth for the
# render helper in :mod:`core.email_templates`.
_COMMON_LABEL_KEYS: Final[tuple[str, ...]] = (
    "common.best_regards",
    "common.team",
    "common.system",
    "common.visit",
    "common.source_code",
    "common.copy_link",
)


def normalize_locale(locale: str | None) -> str:
    """
    Return a supported backend locale, falling back to English.

    Args:
        locale: Raw locale string from user preference or None.

    Returns:
        A locale code guaranteed to be in :data:`SUPPORTED_LOCALES`.
    """
    if not locale:
        return DEFAULT_LOCALE
    candidate = locale.strip()
    if not candidate:
        return DEFAULT_LOCALE
    # Case-insensitive match that preserves the canonical BCP 47 casing
    # (e.g. "ZH-HANS" -> "zh-Hans"). Script and region subtags in the
    # supported set are title/upper-cased, so a naive ``.lower()`` compare
    # would never match them.
    lowered = candidate.lower()
    return next(
        (code for code in _supported() if code.lower() == lowered),
        DEFAULT_LOCALE,
    )


def html_lang(locale: str | None) -> str:
    """
    Return the BCP 47 HTML lang value for a backend locale.

    Args:
        locale: Raw locale string or None.

    Returns:
        A BCP 47 language tag string (e.g. ``"en-US"``).
    """
    normalized = normalize_locale(locale)
    return HTML_LANG_BY_LOCALE.get(normalized, normalized)


@functools.lru_cache(maxsize=32)
def _load_catalog(locale: str) -> dict[str, str]:
    """
    Load and cache a translation catalog JSON file.

    Args:
        locale: A normalized locale code (must be in
            :data:`SUPPORTED_LOCALES`).

    Returns:
        A dict mapping translation keys to localized strings. Falls
        back to the ``en`` catalog if the locale file does not exist
        and logs a one-time warning (cached, so it fires once per
        missing locale per process).
    """
    # Defense-in-depth: callers are expected to pass a normalized
    # locale, but we re-check before using it to build a filesystem
    # path so a future caller bug cannot become a path-traversal bug.
    if locale not in _supported():
        locale = DEFAULT_LOCALE

    catalog_path = _LOCALES_DIR / locale / "email.json"
    if not catalog_path.exists():
        if locale != DEFAULT_LOCALE:
            logger.warning(f"i18n: missing email catalog for locale '{locale}', falling back to '{DEFAULT_LOCALE}'")
        catalog_path = _LOCALES_DIR / DEFAULT_LOCALE / "email.json"
    with catalog_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def t(key: str, locale: str | None, **kwargs: str) -> str:
    """
    Translate a key for the given locale.

    Named placeholders in the catalog value (``{name}``) are replaced
    with the keyword arguments supplied.

    Args:
        key: Dot-separated translation key.
        locale: Raw locale string or None; normalized internally.
        **kwargs: Named placeholder values for string formatting.

    Returns:
        The translated, formatted string. Returns ``key`` itself if
        the key is missing from both the requested catalog and the
        default catalog.
    """
    normalized = normalize_locale(locale)
    catalog = _load_catalog(normalized)
    if key not in catalog and normalized != DEFAULT_LOCALE:
        catalog = _load_catalog(DEFAULT_LOCALE)
    value = catalog.get(key, key)
    if kwargs:
        value = value.format(**kwargs)
    return value


def common_labels(locale: str | None) -> dict[str, str]:
    """
    Return the localized common labels reused by every email layout.

    Args:
        locale: Raw locale string or None.

    Returns:
        Mapping of bare label name (``best_regards``, ``team``,
        ``system``, ``visit``, ``source_code``, ``copy_link``) to
        translated string.
    """
    return {key.split(".", 1)[1]: t(key, locale) for key in _COMMON_LABEL_KEYS}
