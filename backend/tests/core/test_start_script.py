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
        "https://host:0",
        "https://host:000000",
        "http://host:080",
    ],
)
def test_shell_matches_backend_canonical_form(value: str) -> None:
    """The shell canonical form equals the Python validator's."""
    assert _canonical_in_shell(value) == Settings._validate_endurain_host(value)


@pytest.mark.parametrize("value", ["https://host/", "ftp://host", "https://user@host", "host", "https://host:abc"])
def test_invalid_value_is_left_for_the_backend_to_reject(value: str) -> None:
    """An invalid value is passed through unchanged so the backend reports it."""
    assert _canonical_in_shell(value) == value


def test_non_ascii_host_is_left_for_the_backend_to_canonicalise() -> None:
    """A host with non-ASCII letters is passed through, because lower-casing it depends on the shell's locale."""
    value = "https://H\u00d4ST:0443"

    assert _canonical_in_shell(value) == value
    assert Settings._validate_endurain_host(_canonical_in_shell(value)) == Settings._validate_endurain_host(value)


def _run_start_script(tmp_path: Path, **env: str) -> tuple[int, str, str]:
    """Run start.sh as the API role with a stub ``uvicorn`` that prints what it was started with.

    Args:
        tmp_path: A scratch directory for the data, log and stub directories.
        **env: Extra environment variables for the script.

    Returns:
        The exit status, standard output and standard error.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "uvicorn"
    stub.write_text('#!/bin/sh\necho "UVICORN $*"\necho "FORWARDED_ALLOW_IPS=$FORWARDED_ALLOW_IPS"\n')
    stub.chmod(0o755)
    environment = {
        "PATH": f"{stub_dir}:/usr/bin:/bin",
        "APP_ROLE": "api",
        "BACKEND_DIR": str(tmp_path / "backend"),
        "DATA_DIR": str(tmp_path / "data"),
        "LOGS_DIR": str(tmp_path / "logs"),
        **env,
    }

    async def run() -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            SHELL,
            str(START_SH),
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        assert process.returncode is not None
        return process.returncode, stdout.decode(), stderr.decode()

    return asyncio.run(run())


@pytest.mark.parametrize("trusted_proxies", ["", "   ", " , "])
def test_start_refuses_behind_proxy_without_a_trusted_proxy(tmp_path: Path, trusted_proxies: str) -> None:
    """BEHIND_PROXY=true with no usable TRUSTED_PROXIES entry stops the start with exit status 1."""
    status, out, err = _run_start_script(tmp_path, BEHIND_PROXY="true", TRUSTED_PROXIES=trusted_proxies)

    assert status == 1
    assert "BEHIND_PROXY=true requires TRUSTED_PROXIES" in err
    assert "UVICORN" not in out


def test_start_honours_forwarded_headers_from_a_trusted_proxy(tmp_path: Path) -> None:
    """A valid TRUSTED_PROXIES entry starts uvicorn with proxy headers and that peer allowed."""
    status, out, _ = _run_start_script(tmp_path, BEHIND_PROXY="true", TRUSTED_PROXIES="10.0.0.1")

    assert status == 0
    assert "--proxy-headers" in out
    assert "FORWARDED_ALLOW_IPS=10.0.0.1" in out
