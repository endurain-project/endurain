#!/usr/bin/env python3
"""Validate that messages follow the Conventional Commits 1.0.0 specification.

Reads one or more messages (either from CLI arguments or, when ``--stdin`` is
passed, one message per line from standard input) and exits non-zero if any of
them is invalid.

Spec reference: https://www.conventionalcommits.org/en/v1.0.0/

Usage::

    check_conventional_commits.py "feat(api): add endpoint"
    git log --format=%s base..head | check_conventional_commits.py --stdin

Designed to run with the Python interpreter already available on the GitHub
runner image. Uses only the standard library so there is no third-party
supply-chain surface.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable

# Allowed types. This whitelist is a *project policy* layered on top of the
# Conventional Commits 1.0.0 spec (the spec recommends but does not mandate a
# fixed set of types). Keep this list in sync with the project's commit
# conventions documented in ``.github/copilot-instructions.md``.
#
# Per the spec, types are matched case-insensitively.
ALLOWED_TYPES: tuple[str, ...] = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
)

# Subject pattern: ``type(scope)!: description``. Scope and ``!`` are optional.
# Per CC 1.0.0:
#   - the type is a noun (matched case-insensitively against ALLOWED_TYPES);
#   - the scope is any noun describing a section of the codebase, enclosed in
#     parentheses, so we accept any non-empty string that is not a closing
#     parenthesis;
#   - the description is free-form text.
_HEADER_RE = re.compile(
    r"""
    ^
    (?P<type>[A-Za-z]+)
    (?:\((?P<scope>[^)]+)\))?
    (?P<breaking>!)?
    :\ 
    (?P<description>.+?)
    \s*$
    """,
    re.VERBOSE,
)


def _validate_message(message: str) -> list[str]:
    """Return a list of validation errors for ``message`` (empty if valid)."""
    errors: list[str] = []

    # Conventional Commits only constrains the first line (the header).
    header = message.splitlines()[0] if message else ""

    if not header.strip():
        return ["message is empty"]

    match = _HEADER_RE.match(header)
    if match is None:
        errors.append(
            "header does not match '<type>(<scope>)!: <description>' "
            "(see https://www.conventionalcommits.org/en/v1.0.0/)"
        )
        return errors

    commit_type = match.group("type")

    # Project policy: restrict to a known set of types. Types are matched
    # case-insensitively per the Conventional Commits spec.
    if commit_type.lower() not in ALLOWED_TYPES:
        errors.append(
            f"type '{commit_type}' is not allowed; "
            f"use one of: {', '.join(ALLOWED_TYPES)}"
        )

    return errors


def _safe_log_value(value: str) -> str:
    """Return ``value`` escaped for safe CI log output."""
    return value.encode("unicode_escape").decode("ascii")


def _iter_messages(args: argparse.Namespace) -> Iterable[str]:
    if args.stdin:
        for line in sys.stdin:
            stripped = line.rstrip("\n")
            if stripped:
                yield stripped
    else:
        yield from args.messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Conventional Commits headers.",
    )
    parser.add_argument(
        "messages",
        nargs="*",
        help="One or more commit messages (or PR titles) to validate.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read messages from standard input, one per line.",
    )
    args = parser.parse_args(argv)

    if not args.stdin and not args.messages:
        parser.error("provide at least one message or use --stdin")

    failures = 0
    checked = 0
    for message in _iter_messages(args):
        checked += 1
        errors = _validate_message(message)
        safe_message = _safe_log_value(message)
        if errors:
            failures += 1
            print(f"INVALID: {safe_message}", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
        else:
            print(f"OK: {safe_message}")

    if checked == 0:
        print("No messages to validate.", file=sys.stderr)
        return 1

    if failures:
        print(
            f"\n{failures} of {checked} message(s) failed Conventional Commits "
            "validation.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
