"""Build the password blocklist from pinned SecLists files.

Downloads each source list from a fixed SecLists commit, keeps the entries long enough to matter, normalizes them the
way passwords are compared (NFC, lowercase) and writes a sorted, gzipped list plus a manifest naming the commit, the
SHA-256 of every source file and of the output. The output is byte-identical for the same commit, so the manifest test
and code review can tell exactly what changed.

Usage:
    python scripts/build_password_blocklist.py <seclists-commit-sha>

Run from the ``backend/`` directory. Only the standard library is used, and nothing downloaded is ever executed.
"""

import gzip
import hashlib
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

SOURCE_REPOSITORY = "https://github.com/danielmiessler/SecLists"
RAW_URL = "https://raw.githubusercontent.com/danielmiessler/SecLists/{commit}/{path}"

#: Each source list and the shortest entry kept from it. 8 is the lowest minimum password length an administrator can
#: set; the long-password list only adds entries a 12-character minimum would let through.
SOURCES: tuple[tuple[str, int], ...] = (
    ("Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt", 8),
    ("Passwords/Common-Credentials/Pwdb_top-1000000.txt", 12),
)

#: Longest entry kept; longer lines are not passwords anyone types.
MAX_ENTRY_LENGTH = 128
#: Largest source file accepted, and the bounds on the number of entries written.
MAX_SOURCE_BYTES = 20 * 1024 * 1024
MIN_ENTRIES = 10_000
MAX_ENTRIES = 200_000

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "modules" / "auth" / "credentials" / "data"
LIST_PATH = DATA_DIR / "password_blocklist.txt.gz"
MANIFEST_PATH = DATA_DIR / "password_blocklist.json"

_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_HEX_ENTRY = re.compile(r"\$HEX\[([0-9a-fA-F]*)\]")


def normalize(password: str) -> str:
    """Return the form a password is compared in: NFC, then lowercase.

    Args:
        password: A password or blocklist entry.

    Returns:
        The normalized text.
    """
    return unicodedata.normalize("NFC", password).lower()


def _download(commit: str, path: str) -> bytes:
    """Fetch one source file from the pinned commit, refusing an oversized body.

    Args:
        commit: The SecLists commit to read from.
        path: The file's path inside the repository.

    Returns:
        The file's bytes.

    Raises:
        ValueError: If the file is larger than ``MAX_SOURCE_BYTES``.
    """
    url = RAW_URL.format(commit=commit, path=path)
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - fixed https URL
        body = response.read(MAX_SOURCE_BYTES + 1)
    if len(body) > MAX_SOURCE_BYTES:
        raise ValueError(f"{path} is larger than {MAX_SOURCE_BYTES} bytes")
    return body


def _entries(body: bytes, min_length: int) -> set[str]:
    """Return the normalized entries of a source file that are between the length bounds.

    Hashcat-style ``$HEX[...]`` lines are decoded; lines that are not valid UTF-8 or contain control characters are
    dropped.

    Args:
        body: The source file.
        min_length: The shortest entry kept.

    Returns:
        The kept entries.

    Raises:
        UnicodeDecodeError: If the file is not UTF-8.
    """
    kept: set[str] = set()
    for line in body.decode("utf-8").splitlines():
        hex_entry = _HEX_ENTRY.fullmatch(line)
        if hex_entry:
            try:
                line = bytes.fromhex(hex_entry.group(1)).decode("utf-8")
            except ValueError:
                continue
        entry = normalize(line)
        if any(unicodedata.category(char) == "Cc" for char in entry):
            continue
        if min_length <= len(entry) <= MAX_ENTRY_LENGTH:
            kept.add(entry)
    return kept


def build(commit: str) -> dict[str, object]:
    """Download the sources at ``commit``, write the list and return its manifest.

    Args:
        commit: The full SHA of the SecLists commit to build from.

    Returns:
        The manifest that was written.

    Raises:
        ValueError: If the commit is not a full SHA, a source is too large, or the entry count is out of bounds.
    """
    if not _COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("pass the full 40-character SecLists commit SHA")
    entries: set[str] = set()
    sources = []
    for path, min_length in SOURCES:
        body = _download(commit, path)
        entries |= _entries(body, min_length)
        sources.append({"path": path, "sha256": hashlib.sha256(body).hexdigest(), "min_length": min_length})
    if not MIN_ENTRIES <= len(entries) <= MAX_ENTRIES:
        raise ValueError(f"{len(entries)} entries is outside {MIN_ENTRIES}-{MAX_ENTRIES}; check the sources")

    payload = gzip.compress(("\n".join(sorted(entries)) + "\n").encode("utf-8"), compresslevel=9, mtime=0)
    manifest: dict[str, object] = {
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": commit,
        "sources": sources,
        "max_entry_length": MAX_ENTRY_LENGTH,
        "entries": len(entries),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LIST_PATH.write_bytes(payload)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    """Build the list from the commit named on the command line."""
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    manifest = build(sys.argv[1])
    sys.stdout.write(f"Wrote {manifest['entries']} entries from SecLists {manifest['source_commit']}\n")


if __name__ == "__main__":
    main()
