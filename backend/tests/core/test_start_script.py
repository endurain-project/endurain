"""The container entrypoint writes the same canonical ``ENDURAIN_HOST`` the backend validates."""

import asyncio
import re
import shutil
from pathlib import Path

import pytest

from core.config import Settings

START_SH = Path(__file__).resolve().parents[3] / "docker" / "start.sh"

SHELL = shutil.which("sh")

pytestmark = pytest.mark.skipif(SHELL is None, reason="needs a POSIX shell")


def _canonical_in_shell(value: str) -> str:
    """Run start.sh's ``canonical_endurain_host`` on ``value`` in isolation.

    Args:
        value: The raw ``ENDURAIN_HOST``.

    Returns:
        What the function prints.
    """
    match = re.search(r"^canonical_endurain_host\(\) \{\n.*?^\}\n", START_SH.read_text(), re.DOTALL | re.MULTILINE)
    assert match, "canonical_endurain_host is missing from start.sh"

    async def run() -> str:
        process = await asyncio.create_subprocess_exec(
            SHELL, "-c", f'{match.group(0)}\ncanonical_endurain_host "$1"', "sh", value, stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        assert process.returncode == 0
        return stdout.decode()

    return asyncio.run(run())


@pytest.mark.parametrize(
    "value",
    [
        "HTTPS://Host:443",
        "https://host",
        "http://Host:8080",
        "https://[::1]:443",
        "http://host:80",
        "https://[2001:DB8::1]:8443",
        "https://host:",
    ],
)
def test_shell_matches_backend_canonical_form(value: str) -> None:
    """The shell canonical form equals the Python validator's."""
    assert _canonical_in_shell(value) == Settings._validate_endurain_host(value)


@pytest.mark.parametrize("value", ["https://host/", "ftp://host", "https://user@host", "host", "https://host:abc"])
def test_invalid_value_is_left_for_the_backend_to_reject(value: str) -> None:
    """An invalid value is passed through unchanged so the backend reports it."""
    assert _canonical_in_shell(value) == value
