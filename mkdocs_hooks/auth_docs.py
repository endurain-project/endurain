"""MkDocs hook that fills auth tables in the docs from the backend source.

The backend is read statically with ``ast`` so the docs build needs no backend
dependencies. A page opts in with a ``<!-- generated:NAME -->`` marker.
"""

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "backend" / "app"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _assigned_literal(path: Path, name: str):
    """Return the literal assigned to module-level ``name`` in ``path``."""
    for node in ast.parse(path.read_text()).body:
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            value = node.value
            if isinstance(value, ast.Call):  # frozenset({...})
                value = value.args[0]
            return ast.literal_eval(value)
    raise LookupError(f"{name} not found in {path}")


def _scopes() -> str:
    scopes = _assigned_literal(APP / "modules/auth/constants.py", "SCOPE_DICT")
    rows = "".join(f"| `{scope}` | {desc} |\n" for scope, desc in scopes.items())
    return "| Scope | Description |\n| ----- | ----------- |\n" + rows


def _enum_values(path: Path, name: str) -> list[str]:
    """Return the string values of the members of the enum class ``name`` in ``path``."""
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return [
                ast.literal_eval(stmt.value)
                for stmt in node.body
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
            ]
    raise LookupError(f"{name} not found in {path}")


def _api_key_scopes() -> str:
    scopes = sorted(_enum_values(APP / "modules/auth/api_keys/constants.py", "ApiKeyScope"))
    scope_dict = _assigned_literal(APP / "modules/auth/constants.py", "SCOPE_DICT")
    rows = "".join(f"| `{scope}` | {scope_dict[scope]} |\n" for scope in scopes)
    return "| Scope | Description |\n| ----- | ----------- |\n" + rows


def _api_key_endpoints() -> str:
    prefix = re.search(
        r'auth_api_keys_router\.router,\s*prefix=core_config\.ROOT_PATH \+ "([^"]+)"',
        (APP / "api.py").read_text(),
    )
    if prefix is None:
        raise LookupError("API key router prefix not found in api.py")
    rows = ""
    for node in ast.parse((APP / "modules/auth/account_security/api_keys_router.py").read_text()).body:
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            func = getattr(deco, "func", None)
            if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
                path = ast.literal_eval(deco.args[0]) if deco.args else ""
                summary = (ast.get_docstring(node) or "").splitlines()[0].rstrip(".")
                rows += f"| `{func.attr.upper()}` | `{prefix.group(1)}{path}` | {summary} |\n"
    return "| Method | Url | Description |\n| ------ | --- | ----------- |\n" + rows


def _error_types() -> str:
    """Table of the ``DomainError`` subclasses: status, ``type`` URN and title."""
    rows = ""
    for node in ast.parse((APP / "core/exceptions.py").read_text()).body:
        if not isinstance(node, ast.ClassDef):
            continue
        attrs = {}
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
                attrs[stmt.targets[0].id] = stmt.value
        if not {"status_code", "code", "title"} <= attrs.keys():
            continue
        status_name = ast.unparse(attrs["status_code"])
        number = re.search(r"HTTP_(\d{3})_", status_name)
        code = ast.literal_eval(attrs["code"])
        title = ast.literal_eval(attrs["title"])
        rows += f"| `{number.group(1)}` | `urn:endurain:error:{code}` | {title} |\n"
    return "| Status | `type` | Title |\n| ------ | ------ | ----- |\n" + rows


def _rate_limits() -> str:
    """Table of the rate-limit tiers with the description from their ``#:`` comments."""
    source = (APP / "core/rate_limit.py").read_text()
    rows = ""
    for comment, name, value in re.findall(r'((?:#:.*\n)+)([A-Z_]+): str = "([^"]+)"', source):
        description = " ".join(line[2:].strip() for line in comment.splitlines())
        rows += f"| `{name}` | {value} | {description} |\n"
    return "| Tier | Limit | Applies to |\n| ---- | ----- | ---------- |\n" + rows


def _router_prefixes() -> dict[Path, str]:
    """Map each router file to the prefix ``api.py`` mounts it under."""
    source = (APP / "api.py").read_text()
    modules = dict(re.findall(r"^import ([\w.]+) as (\w+)$", source, re.M))
    aliases = {alias: module for module, alias in modules.items()}
    prefixes = {}
    for alias, prefix in re.findall(r'(\w+)\.router,\s*prefix=core_config\.ROOT_PATH \+ "([^"]*)"', source):
        if alias in aliases:
            prefixes[APP / (aliases[alias].replace(".", "/") + ".py")] = prefix
    return prefixes


def idempotent_routes() -> list[tuple[str, str, str]]:
    """Return ``(method, url, kind)`` of every route that reads ``Idempotency-Key``.

    ``kind`` is ``response`` for a route that opts in to replay with ``core_idempotency.Idempotent`` and ``job`` for
    an upload that reads the key through ``core_idempotency.IdempotencyKey``.
    """
    routes = []
    for path, prefix in _router_prefixes().items():
        for node in ast.parse(path.read_text()).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            names = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            if not names & {"Idempotent", "IdempotencyKey"}:
                continue
            kind = "response" if "Idempotent" in names else "job"
            for deco in node.decorator_list:
                func = getattr(deco, "func", None)
                if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
                    url = prefix + (ast.literal_eval(deco.args[0]) if deco.args else "")
                    routes.append((func.attr.upper(), url, kind))
    return sorted(routes, key=lambda route: (route[1], route[0]))


def _idempotency_routes() -> str:
    """Table of the routes that accept ``Idempotency-Key`` and what a repeat of the request returns."""
    returns = {"response": "The stored response", "job": "The job of the first request"}
    rows = "".join(f"| `{method}` | `{url}` | {returns[kind]} |\n" for method, url, kind in idempotent_routes())
    return "| Method | Url | A repeat returns |\n| ------ | --- | ---------------- |\n" + rows


GENERATORS = {
    "idempotency-routes": _idempotency_routes,
    "error-types": _error_types,
    "rate-limits": _rate_limits,
    "scopes": _scopes,
    "api-key-scopes": _api_key_scopes,
    "api-key-endpoints": _api_key_endpoints,
}


def on_page_markdown(markdown, **kwargs):
    """Replace ``<!-- generated:NAME -->`` markers with generated tables."""
    for name, generate in GENERATORS.items():
        marker = f"<!-- generated:{name} -->"
        if marker in markdown:
            markdown = markdown.replace(marker, generate())
    return markdown
