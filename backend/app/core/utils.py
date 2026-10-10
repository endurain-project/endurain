"""HTTP helpers for serving static-asset responses.

All helpers in this module take an untrusted relative
path and resolve it against a fixed base directory.
The :func:`_safe_resolve` guard prevents directory
traversal (``../`` segments, absolute paths, symlink
escapes) from ever reading files outside the intended
base directory.
"""

import os

from fastapi.responses import FileResponse

import core.config as core_config


def _safe_resolve(base_dir: str, untrusted_path: str) -> str | None:
    """Resolve ``untrusted_path`` inside ``base_dir`` safely.

    Joins the user-supplied path with the base directory,
    follows symlinks, and verifies the final real path is
    contained within the real path of the base. This
    blocks classic traversal payloads (``../../etc/passwd``),
    absolute-path injection, and symlink-escape attempts.

    Args:
        base_dir: The trusted root directory.
        untrusted_path: A caller-supplied relative path.

    Returns:
        The absolute, resolved path when the result is
        inside ``base_dir`` and refers to an existing
        regular file; ``None`` otherwise. Callers can
        therefore treat ``None`` uniformly as "404".
    """
    if not untrusted_path:
        return None
    # ``os.path.join`` would ignore ``base_dir`` if
    # ``untrusted_path`` is absolute, so reject that
    # case explicitly before joining.
    if os.path.isabs(untrusted_path):
        return None

    base_real = os.path.realpath(base_dir)
    candidate = os.path.realpath(os.path.join(base_real, untrusted_path))

    # ``commonpath`` raises on mixed drives (Windows) or
    # when one path is empty; treat any failure as unsafe.
    try:
        if os.path.commonpath([base_real, candidate]) != base_real:
            return None
    except ValueError:
        return None

    if not os.path.isfile(candidate):
        return None

    return candidate


def _serve_from(base_dir: str, untrusted_path: str) -> FileResponse | None:
    """Return a :class:`FileResponse` for a path inside ``base_dir``.

    Returns ``None`` when the path is unsafe or missing
    so callers can convert that into a 404 response
    without leaking which case applied.
    """
    resolved = _safe_resolve(base_dir, untrusted_path)
    if resolved is None:
        return None
    return FileResponse(resolved)


def return_frontend_index(path: str):
    """Serve a file from the built frontend bundle."""
    return _serve_from(core_config.settings.FRONTEND_DIR, path)


def return_server_img_path(server_img: str):
    """Serve a server-managed image asset."""
    return _serve_from(core_config.SERVER_IMAGES_DIR, server_img)
