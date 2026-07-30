"""Local-filesystem ``StorageProvider`` backend."""

from pathlib import Path


class LocalStorage:
    """``StorageProvider`` storing blobs as files under a per-area subdirectory.

    A blob for ``(area, key)`` lives at ``{base_dir}/{area}/{key}`` and is served
    at ``{url_prefix}/{area}/{key}``. Keys are server-generated (e.g. ``42.webp``);
    both area and key are validated so a stray value can never escape the base
    directory.

    Args:
        base_dir: Absolute storage root every area subdirectory lives under.
        url_prefix: URL path prefix returned by :meth:`url` (default: root).
    """

    def __init__(self, base_dir: str, url_prefix: str = "") -> None:
        self._base = Path(base_dir)
        self._url_prefix = url_prefix.rstrip("/")

    def _ensure_safe_segment(self, value: str, label: str) -> None:
        """Reject absolute or parent-traversal area/key values (no filesystem access)."""
        if value.startswith(("/", "\\")) or ".." in Path(value).parts:
            raise ValueError(f"Storage {label} escapes base directory: {value!r}")

    def _resolve(self, area: str, key: str) -> Path:
        """Resolve ``(area, key)`` to an absolute path, rejecting traversal outside base."""
        self._ensure_safe_segment(area, "area")
        self._ensure_safe_segment(key, "key")
        base = self._base.resolve()
        candidate = (base / area / key).resolve()
        if not candidate.is_relative_to(base):
            raise ValueError(f"Storage key escapes base directory: {area}/{key!r}")
        return candidate

    def save(self, area: str, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._resolve(area, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def exists(self, area: str, key: str) -> bool:
        return self._resolve(area, key).is_file()

    def delete(self, area: str, key: str) -> None:
        path = self._resolve(area, key)
        if path.is_file():
            path.unlink()

    def url(self, area: str, key: str, expires_in: int = 3600) -> str:
        self._ensure_safe_segment(area, "area")
        self._ensure_safe_segment(key, "key")
        return f"{self._url_prefix}/{area}/{key}"
