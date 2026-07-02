#!/usr/bin/env python3
"""Sync Weblate git/json-nested components with this repo's source i18n files.

Ports aux_scripts/move_to_weblate.ps1 to Python (no PowerShell dependency).

The v2 frontend stores namespace JSON files under
``frontend/src/i18n/locales/<lang>/<namespace>.json``, with ``en`` as the
source language. This script walks every ``*.json`` file under the ``en``
folder and creates/updates a matching Weblate component (or deletes stale
git/json-nested components first, when --no-purge is not passed).

For every component it manages, it also reconciles the enabled translation
languages against `SUPPORTED_LOCALES` in `frontend/src/i18n/index.ts` (the
app's single source of truth for which locales are supported): languages no
longer supported are removed, and supported languages missing a translation
are added. Pass --no-language-sync to skip this step.

As a final step, it tells Weblate to sync its internal repository clone with
the official upstream repo (default operation: `pull`), so the whole project
reflects exactly what's in the repo. Pass --no-repo-sync to skip this, or
--repo-sync-operation to use a different VCS operation (push/pull/commit/
reset/cleanup/file-sync/file-scan).

By default this runs in DRY-RUN mode and only prints what it would do.
Pass --apply to actually call the Weblate REST API.

The API token is NEVER hardcoded here. Provide it via the WEBLATE_TOKEN
environment variable or --token. Rotate any token that was ever pasted into
a tracked file.

Usage:
    WEBLATE_TOKEN=wlu_xxx python3 devscripts/move_to_weblate.py
    WEBLATE_TOKEN=wlu_xxx python3 devscripts/move_to_weblate.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

WEBLATE_URL = "https://translate.codeberg.org"
PROJECT_SLUG = "endurain"
REPO = "https://codeberg.org/endurain-project/endurain.git"
BRANCH = "master"  # v2 frontend (frontend/src/i18n/locales) lives on master now
PUSH_BRANCH = "l10n/weblate"  # branch Weblate commits translations to
LICENSE = "AGPL-3.0-only"
LICENSE_URL = "https://spdx.org/licenses/AGPL-3.0-only.html"

COMPONENT_FIELDS = (
    "name",
    "repo",
    "branch",
    "push_branch",
    "vcs",
    "file_format",
    "filemask",
    "template",
    "license",
    "license_url",
)


def repo_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "-C", str(script_dir), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return script_dir.parent


def read_supported_locale_codes(root: Path) -> list[str]:
    """Extract locale codes from `SUPPORTED_LOCALES` in the frontend's i18n
    entry point, so the list of "supported" languages can never drift from
    what the app itself supports.
    """
    index_file = root / "frontend" / "src" / "i18n" / "index.ts"
    text = index_file.read_text(encoding="utf-8")
    match = re.search(r"SUPPORTED_LOCALES\s*=\s*\[(.*?)\]\s*as const", text, re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not find SUPPORTED_LOCALES in {index_file}")
    codes = re.findall(r"code:\s*'([^']+)'", match.group(1))
    if not codes:
        raise RuntimeError(f"SUPPORTED_LOCALES in {index_file} had no code entries")
    return codes


def api_request(
    method: str, url: str, token: str, body: dict[str, Any] | None = None
) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Token {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310 - trusted fixed host
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc


def api_request_with_retry(
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None = None,
    *,
    retries: int = 5,
    initial_delay: float = 3.0,
    backoff: float = 2.0,
) -> Any:
    """Like api_request, but retries on failure with exponential backoff.

    Weblate creates/clones a component's repository in the BACKGROUND after
    POST .../components/ returns, so calls that depend on the template being
    parsed (e.g. adding a translation) can transiently fail right after a
    component is created. Retrying gives that background work time to finish.
    """
    delay = initial_delay
    last_exc: RuntimeError | None = None
    for attempt in range(retries):
        try:
            return api_request(method, url, token, body)
        except RuntimeError as exc:
            last_exc = exc
            if attempt == retries - 1:
                break
            time.sleep(delay)
            delay *= backoff
    assert last_exc is not None
    raise last_exc


def get_existing_components(token: str) -> dict[str, dict[str, Any]]:
    components: dict[str, dict[str, Any]] = {}
    next_url: str | None = (
        f"{WEBLATE_URL}/api/projects/{PROJECT_SLUG}/components/?page_size=1000"
    )
    while next_url:
        response = api_request("GET", next_url, token)
        for component in response.get("results", []):
            components[component["slug"]] = component
        next_url = response.get("next")
    return components


def purge_json_components(
    existing: dict[str, dict[str, Any]],
    protected_slugs: set[str],
    token: str,
    dry_run: bool,
) -> dict[str, dict[str, Any]]:
    """Delete stale git/json-nested components, except ones in
    `protected_slugs` (components matching a current v2 source file - those
    are reconciled via create/update instead, so they're never deleted).
    """
    for component in list(existing.values()):
        if (
            component.get("vcs") != "git"
            or component.get("file_format") != "json-nested"
        ):
            continue
        slug = component["slug"]
        if slug in protected_slugs:
            print(f"SKIP purge (matches a current source file): {slug}")
            continue
        if dry_run:
            print(f"DRYRUN delete component: {slug}")
            continue
        try:
            encoded_slug = urllib.parse.quote(slug, safe="")
            api_request(
                "DELETE",
                f"{WEBLATE_URL}/api/components/{PROJECT_SLUG}/{encoded_slug}/",
                token,
            )
            print(f"DELETED component: {slug}")
        except RuntimeError as exc:
            print(f"FAILED delete component: {slug}")
            print(exc)
    return get_existing_components(token)


def list_component_translations(
    component_slug: str, token: str
) -> dict[str, dict[str, Any]]:
    """Return the component's translations keyed by language code."""
    translations: dict[str, dict[str, Any]] = {}
    encoded_slug = urllib.parse.quote(component_slug, safe="")
    next_url: str | None = (
        f"{WEBLATE_URL}/api/components/{PROJECT_SLUG}/{encoded_slug}/translations/?page_size=200"
    )
    while next_url:
        response = api_request("GET", next_url, token)
        for translation in response.get("results", []):
            code = translation.get("language", {}).get("code")
            if code:
                translations[code] = translation
        next_url = response.get("next")
    return translations


def component_source_language(component: dict[str, Any] | None) -> str:
    """Read the component's source language code (documented `source_language`
    field), falling back to "en" if it's ever missing.
    """
    if component is None:
        return "en"
    return component.get("source_language", {}).get("code") or "en"


# Mapping from this app's locale codes (frontend/src/i18n/index.ts
# SUPPORTED_LOCALES) to the language codes Weblate expects for them. Weblate
# uses underscores instead of hyphens for region/script subtags (e.g.
# 'pt-PT' -> 'pt_PT', 'zh-Hans' -> 'zh_Hans'), and a couple of codes need an
# explicit region Weblate doesn't infer on its own (e.g. 'nb' -> 'nb_NO').
WEBLATE_LANGUAGE_CODE_OVERRIDES = {
    "nb": "nb_NO",
}


def to_weblate_language_code(app_code: str) -> str:
    """Translate one of this app's locale codes into the language code
    Weblate expects for it.
    """
    return WEBLATE_LANGUAGE_CODE_OVERRIDES.get(app_code, app_code.replace("-", "_"))


def sync_component_languages(
    component_slug: str,
    source_language: str,
    supported_codes: list[str],
    token: str,
    dry_run: bool,
    debug: bool,
) -> None:
    """Remove translation languages Weblate has that aren't supported
    anymore, and add supported languages the component is missing. The
    source language is always kept.
    """
    try:
        current = list_component_translations(component_slug, token)
    except RuntimeError as exc:
        print(f"FAILED to list languages for {component_slug}")
        print(exc)
        return

    supported = {to_weblate_language_code(code) for code in supported_codes}
    to_remove = sorted(
        code for code in current if code not in supported and code != source_language
    )
    to_add = sorted(
        code for code in supported if code != source_language and code not in current
    )

    for code in to_remove:
        if dry_run:
            print(f"DRYRUN remove language {code} from {component_slug}")
            continue
        try:
            encoded_slug = urllib.parse.quote(component_slug, safe="")
            api_request_with_retry(
                "DELETE",
                f"{WEBLATE_URL}/api/translations/{PROJECT_SLUG}/{encoded_slug}/{code}/",
                token,
            )
            print(f"REMOVED language {code} from {component_slug}")
        except RuntimeError as exc:
            print(f"FAILED to remove language {code} from {component_slug}")
            print(exc)
            if debug:
                print(f"DEBUG component={component_slug} language={code}")

    for code in to_add:
        if dry_run:
            print(f"DRYRUN add language {code} to {component_slug}")
            continue
        try:
            encoded_slug = urllib.parse.quote(component_slug, safe="")
            api_request_with_retry(
                "POST",
                f"{WEBLATE_URL}/api/components/{PROJECT_SLUG}/{encoded_slug}/translations/",
                token,
                {"language_code": code},
            )
            print(f"ADDED language {code} to {component_slug}")
        except RuntimeError as exc:
            print(f"FAILED to add language {code} to {component_slug}")
            print(exc)
            if debug:
                print(f"DEBUG component={component_slug} language={code}")


def sync_file(
    json_file: Path,
    root: Path,
    existing: dict[str, dict[str, Any]],
    token: str,
    dry_run: bool,
    debug: bool,
) -> tuple[str, bool, str] | None:
    """Create/update the Weblate component for one source json file.

    Returns (slug, queryable, source_language) on success, where `queryable`
    tells the caller whether the component can be queried right now (it
    either already existed, or was actually created because --apply was
    passed) - or None if the file was skipped/out of scope.
    """
    full_path = json_file.resolve()
    try:
        rel = full_path.relative_to(root).as_posix()
    except ValueError:
        print("WARN source path is outside repo root. Skipping file.")
        if debug:
            print(f"DEBUG fullPath={full_path}")
        return None

    if not rel.startswith("frontend/src/i18n/locales/en/"):
        print("WARN unexpected relative path. Skipping file.")
        if debug:
            print(f"DEBUG fullName={full_path}")
            print(f"DEBUG rel={rel}")
        return None

    mask = rel.replace("/en/", "/*/")
    name = json_file.stem
    slug = name

    desired: dict[str, Any] = {
        "name": name,
        "slug": slug,
        "vcs": "git",
        "repo": REPO,
        "branch": BRANCH,
        "push_branch": PUSH_BRANCH,
        "file_format": "json-nested",
        "filemask": mask,
        "template": rel,
        "new_base": rel,
        "license": LICENSE,
        "license_url": LICENSE_URL,
    }

    current = existing.get(slug)
    if current is not None:
        needs_update = any(
            current.get(field) != desired[field] for field in COMPONENT_FIELDS
        )
        if not needs_update:
            print(f"SKIP existing (already aligned): {slug}")
            return (slug, True, component_source_language(current))

        patch_body = {field: desired[field] for field in COMPONENT_FIELDS}
        patch_body["new_base"] = desired["new_base"]

        if dry_run:
            print(f"DRYRUN update: {slug} | template={rel} | mask={mask}")
            return (slug, True, component_source_language(current))

        try:
            encoded_slug = urllib.parse.quote(slug, safe="")
            updated = api_request(
                "PATCH",
                f"{WEBLATE_URL}/api/components/{PROJECT_SLUG}/{encoded_slug}/",
                token,
                patch_body,
            )
            print(f"UPDATED: {updated['slug']}")
        except RuntimeError as exc:
            print(f"FAILED update: {slug}")
            print(exc)
            if debug:
                print("DEBUG patch payload:")
                print(json.dumps(patch_body, indent=2))
            return None
        return (slug, True, component_source_language(updated))

    if dry_run:
        print(f"DRYRUN create: {slug} | template={rel} | mask={mask}")
        return (slug, False, "en")

    try:
        created = api_request(
            "POST",
            f"{WEBLATE_URL}/api/projects/{PROJECT_SLUG}/components/",
            token,
            desired,
        )
        print(f"CREATED: {created['slug']}")
    except RuntimeError as exc:
        print(f"FAILED: {slug}")
        print(exc)
        if debug:
            print("DEBUG create payload:")
            print(json.dumps(desired, indent=2))
            print(f"DEBUG source file: {json_file}")
            print(f"DEBUG rel={rel}")
            print(f"DEBUG mask={mask}")
        return None
    return (slug, True, component_source_language(created))


def sync_project_repository(operation: str, token: str) -> Any:
    """Perform a VCS operation on the whole project's repository (e.g. pull
    the latest state from the official upstream repo into Weblate).
    """
    return api_request_with_retry(
        "POST",
        f"{WEBLATE_URL}/api/projects/{PROJECT_SLUG}/repository/",
        token,
        {"operation": operation},
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("WEBLATE_TOKEN"),
        help="Weblate API token (defaults to the WEBLATE_TOKEN env var). Never hardcode this.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create/update/delete components via the API (default is dry-run).",
    )
    parser.add_argument(
        "--no-purge",
        action="store_true",
        help="Skip deleting existing git/json-nested components before recreating them.",
    )
    parser.add_argument(
        "--no-language-sync",
        action="store_true",
        help="Skip reconciling each component's enabled translation languages against SUPPORTED_LOCALES.",
    )
    parser.add_argument(
        "--no-repo-sync",
        action="store_true",
        help="Skip the final project-wide repository sync (pull) with the official upstream repo.",
    )
    parser.add_argument(
        "--repo-sync-operation",
        default="pull",
        choices=(
            "push",
            "pull",
            "commit",
            "reset",
            "cleanup",
            "file-sync",
            "file-scan",
        ),
        help="VCS operation to run as the final step (default: pull).",
    )
    parser.add_argument("--quiet", action="store_true", help="Reduce debug output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.token:
        print(
            "ERROR: no Weblate token supplied. Set WEBLATE_TOKEN or pass --token.",
            file=sys.stderr,
        )
        return 1

    dry_run = not args.apply
    debug = not args.quiet
    purge_first = not args.no_purge
    language_sync = not args.no_language_sync

    root = repo_root()
    base_dir = root / "frontend" / "src" / "i18n" / "locales" / "en"

    if debug:
        print(f"DEBUG repoRoot={root}")
        print(f"DEBUG baseDir={base_dir}")
        print(
            f"DEBUG dryRun={dry_run} purgeFirst={purge_first} languageSync={language_sync}"
        )

    if not base_dir.is_dir():
        print(f"ERROR: base dir not found: {base_dir}", file=sys.stderr)
        return 1

    supported_codes: list[str] = []
    if language_sync:
        try:
            supported_codes = read_supported_locale_codes(root)
            if debug:
                print(f"DEBUG supportedLocales={supported_codes}")
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    existing = get_existing_components(args.token)

    json_files = sorted(base_dir.rglob("*.json"))
    desired_slugs = {f.stem for f in json_files}

    if purge_first:
        existing = purge_json_components(existing, desired_slugs, args.token, dry_run)

    for json_file in json_files:
        result = sync_file(json_file, root, existing, args.token, dry_run, debug)
        if result is None or not language_sync:
            continue
        slug, queryable, source_language = result
        if not queryable:
            print(f"DRYRUN language sync for {slug} (component does not exist yet)")
            continue
        sync_component_languages(
            slug, source_language, supported_codes, args.token, dry_run, debug
        )

    if not args.no_repo_sync:
        if dry_run:
            print(
                f"DRYRUN repository {args.repo_sync_operation} for project {PROJECT_SLUG}"
            )
        else:
            try:
                result = sync_project_repository(args.repo_sync_operation, args.token)
                print(
                    f"REPOSITORY {args.repo_sync_operation}: result={result.get('result')}"
                )
            except RuntimeError as exc:
                print(
                    f"FAILED repository {args.repo_sync_operation} for project {PROJECT_SLUG}"
                )
                print(exc)
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
