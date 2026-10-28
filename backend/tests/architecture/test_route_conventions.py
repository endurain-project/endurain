"""Route and signature conventions from ``code-standards.md`` and ``errors-and-api.md``, enforced.

Each rule is stated on what the code does, not on a file existing: a route declares what it
returns, a write is rate limited, and ``db`` sits where a reader expects it. They apply to every
converted module, so a new route or function is covered the day it is written.
"""

import ast
import pathlib

from tests._helpers.module_roles import CONVERTED_MODULES, files_with_role, role_of

import modules.auth.constants as auth_constants

_ROOT = pathlib.Path("app/modules")
_CONVERTED = tuple(_ROOT / name for name in CONVERTED_MODULES)

_APP = pathlib.Path("app")

#: Dependencies that have a shared alias, mapped to the alias a parameter must use instead of repeating
#: ``Annotated[..., Depends(<dependency>)]``.
_DEPENDENCY_ALIASES = {
    "core_database.get_db": "core_dependencies.DbSession",
    "auth_dependencies.get_sub_from_access_token": "auth_dependencies.CurrentUserId",
    "core_dependencies.get_storage": "core_dependencies.Storage",
    "core_dependencies.get_platform_state": "core_dependencies.PlatformState",
}

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_WRITE_METHODS = frozenset({"post", "put", "patch", "delete"})

#: Roles whose functions are FastAPI handlers or dependencies. FastAPI reads their parameters by
#: name, so they order them by dependency and are outside the ``db``-position rule.
_FRAMEWORK_ROLES = frozenset({"router", "public_router", "dependencies"})


def _route_decorators(function: ast.AST):
    """Yield ``(method, call)`` for each HTTP route decorator on a function."""
    for decorator in getattr(function, "decorator_list", []):
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in _HTTP_METHODS
        ):
            yield decorator.func.attr, decorator


def _router_functions() -> list[tuple[pathlib.Path, ast.FunctionDef]]:
    """Return every route handler of every converted module."""
    found: list[tuple[pathlib.Path, ast.FunctionDef]] = []
    for role in ("router", "public_router"):
        for path in files_with_role(_CONVERTED, role):
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, ast.FunctionDef) and any(True for _ in _route_decorators(node)):
                    found.append((path, node))
    return found


def _limits(function: ast.FunctionDef) -> bool:
    """Return whether a function carries a ``limiter.limit(...)`` decorator."""
    return any(
        isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "limit"
        for decorator in function.decorator_list
    )


def _scope_parameter_names(path: pathlib.Path) -> frozenset[str]:
    """Names a route must not give its scope check."""
    return frozenset({"_check_scopes"})


class TestRouteConventions:
    def test_every_route_declares_what_it_returns(self):
        """JSON routes declare ``response_model``; byte routes declare ``response_class`` or ``responses``.

        A route that declares neither publishes an untyped response, so the generated client
        and the OpenAPI document cannot say what it sends.
        """
        offenders = [
            f"{path.relative_to(_ROOT).as_posix()}::{function.name}"
            for path, function in _router_functions()
            for _, call in _route_decorators(function)
            if not {"response_model", "response_class", "responses"} & {keyword.arg for keyword in call.keywords}
        ]

        assert offenders == [], "Declare response_model (JSON) or responses/response_class (bytes):\n  " + "\n  ".join(
            offenders
        )

    def test_the_default_200_is_not_repeated(self):
        """A route answers 200 by default, so ``status_code=200`` only says what FastAPI already does.

        Other codes (201, 202, 204) are the information a ``status_code`` carries; a repeated 200 hides them.
        """
        offenders = [
            f"{path.relative_to(_ROOT).as_posix()}::{function.name}"
            for path, function in _router_functions()
            for _, call in _route_decorators(function)
            for keyword in call.keywords
            if keyword.arg == "status_code" and ast.unparse(keyword.value) in {"200", "status.HTTP_200_OK"}
        ]

        assert offenders == [], "Remove the default status_code=200 from:\n  " + "\n  ".join(offenders)

    def test_every_write_route_is_rate_limited(self):
        """Reads rely on the global default; a write, upload or sync names its own tier.

        The tier is picked by what the endpoint costs or exposes (see ``errors-and-api.md``), so
        a write route without ``@limiter.limit`` would silently take the read budget.
        """
        offenders = [
            f"{path.relative_to(_ROOT).as_posix()}::{function.name}"
            for path, function in _router_functions()
            if any(method in _WRITE_METHODS for method, _ in _route_decorators(function)) and not _limits(function)
        ]

        assert offenders == [], "Add a @core_rate_limit.limiter.limit(<tier>) to:\n  " + "\n  ".join(offenders)

    def test_dependencies_declare_constraints_on_types(self):
        """A parameter's constraint is its type; ``dependencies`` does not raise ``HTTPException`` by hand.

        A hand-written validator shows up in no OpenAPI schema and answers with its own body, so
        the generated client cannot type the parameter and a bad value looks different per module.
        """
        offenders = [
            path.relative_to(_ROOT).as_posix()
            for path in files_with_role(_CONVERTED, "dependencies")
            if "HTTPException" in path.read_text()
        ]

        assert offenders == [], "Declare the constraint with Path/Query/AfterValidator instead:\n  " + "\n  ".join(
            offenders
        )

    def test_path_parameters_are_typed_by_alias(self):
        """A path parameter's constraint is its type: ``PositiveId``/``ActivityId``, not a bare ``int``.

        A bare ``int`` accepts ``0`` and negative ids, and publishes no constraint in OpenAPI.
        """
        offenders: list[str] = []
        for path, function in _router_functions():
            for _, call in _route_decorators(function):
                if not call.args or not isinstance(call.args[0], ast.Constant):
                    continue
                route_params = {
                    segment[1:-1]
                    for segment in str(call.args[0].value).split("/")
                    if segment.startswith("{") and segment.endswith("}")
                }
                for argument in function.args.args:
                    annotation = argument.annotation
                    if (
                        argument.arg in route_params
                        and isinstance(annotation, ast.Name)
                        and annotation.id in {"int", "str"}
                    ):
                        offenders.append(f"{path.relative_to(_ROOT).as_posix()}::{function.name}({argument.arg})")

        assert offenders == [], "Type the path parameter with an alias from dependencies:\n  " + "\n  ".join(offenders)

    def test_shared_dependencies_are_injected_through_their_alias(self):
        """A parameter uses ``DbSession``/``CurrentUserId``/``Storage``/``PlatformState``, not an inline ``Depends``.

        Repeating ``Annotated[..., Depends(...)]`` on every route lets the same dependency drift
        into several spellings; the alias keeps one definition to change.
        """
        offenders: list[str] = []
        for path in sorted(_APP.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                arguments = node.args
                for argument in arguments.posonlyargs + arguments.args + arguments.kwonlyargs:
                    if argument.annotation is None:
                        continue
                    for call in ast.walk(argument.annotation):
                        if (
                            isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Name)
                            and call.func.id == "Depends"
                            and call.args
                            and ast.unparse(call.args[0]) in _DEPENDENCY_ALIASES
                        ):
                            alias = _DEPENDENCY_ALIASES[ast.unparse(call.args[0])]
                            offenders.append(
                                f"{path.relative_to(_APP).as_posix()}::{node.name}({argument.arg}) -> {alias}"
                            )

        assert offenders == [], "Use the shared alias instead of an inline Depends:\n  " + "\n  ".join(offenders)

    def test_every_authenticated_route_declares_its_own_scope(self):
        """A route's scope sits on its decorator, not on the ``include_router`` call in ``api.py``.

        One spelling means a reader of a route sees what it requires, and a route added to a router
        cannot inherit a scope nobody chose for it. A router whose access control is not a token
        (a signed URL, a one-time link token) is listed with its reason.
        """
        credentialed_by_url = {
            "photo_router.py": "the signed token in the URL is the credential (an <img> cannot send a header)",
            "browser_redirect_router.py": "the one-time link_token parameter is the credential",
        }
        scope_checks = {"check_scopes", "check_auth_scopes"}
        offenders = []
        for path, function in _router_functions():
            if role_of(path.stem) != "router" or path.name in credentialed_by_url:
                continue
            for _, call in _route_decorators(function):
                declared = {
                    node.attr
                    for keyword in call.keywords
                    if keyword.arg == "dependencies"
                    for node in ast.walk(keyword.value)
                    if isinstance(node, ast.Attribute)
                }
                if not scope_checks & declared:
                    offenders.append(f"{path.relative_to(_ROOT).as_posix()}::{function.name}")

        assert offenders == [], "Add dependencies=[Security(auth_dependencies.check_scopes, scopes=[...])] to:\n  " + (
            "\n  ".join(offenders)
        )

    def test_scope_checks_are_declared_on_the_route_decorator(self):
        """A scope check nobody reads goes in ``dependencies=[Security(...)]``, not a ``_check_scopes`` parameter.

        The parameter would appear in the function signature and in its docstring, which FastAPI
        publishes as the OpenAPI description.
        """
        offenders = [
            f"{path.relative_to(_APP).as_posix()}::{node.name}"
            for path in sorted(_APP.rglob("*.py"))
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                argument.arg in _scope_parameter_names(path)
                for argument in node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            )
        ]

        assert offenders == [], (
            "Move the Security(...) scope check to the route's dependencies=[...]:\n  " + "\n  ".join(offenders)
        )


class TestSignatureConventions:
    def test_db_is_the_last_required_positional_parameter(self):
        """``service``, ``crud`` and the other non-framework layers put ``db`` after the data and before options.

        Routers and dependencies are exempt: FastAPI resolves their parameters by name and the
        dependency graph, so their order follows what reads best, not a positional convention.
        """
        offenders: list[str] = []
        for root in _CONVERTED:
            for path in sorted(root.rglob("*.py")):
                if "__pycache__" in path.parts or role_of(path.stem) in _FRAMEWORK_ROLES:
                    continue
                for node in ast.walk(ast.parse(path.read_text())):
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    arguments = node.args
                    positional = [argument.arg for argument in arguments.posonlyargs + arguments.args]
                    required = positional[: len(positional) - len(arguments.defaults)]
                    if "db" in positional and (not required or required[-1] != "db"):
                        offenders.append(f"{path.relative_to(_ROOT).as_posix()}::{node.name}({', '.join(positional)})")

        assert offenders == [], "db must be the last required positional parameter:\n  " + "\n  ".join(offenders)

    def test_publishers_take_db_and_any_commit_as_a_required_keyword(self):
        """``publish_<fact>(<ids>, db, [*, commit,] <extras>)``: ``commit``, when taken, is required by keyword.

        A publisher that stages (``publish_on_commit``) takes only ``db`` and leaves the commit to
        its caller. One that owns the commit ordering (``publish_committing``) takes it required: an
        optional ``commit`` would let a caller publish outside the transaction.
        """
        offenders: list[str] = []
        for path in files_with_role(_CONVERTED, "event_publishers"):
            for node in ast.parse(path.read_text()).body:
                if not isinstance(node, ast.FunctionDef) or not node.name.startswith("publish_"):
                    continue
                positional = [argument.arg for argument in node.args.args]
                keyword_only = {
                    argument.arg: default
                    for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True)
                }
                if positional[-1:] != ["db"] or ("commit" in keyword_only and keyword_only["commit"] is not None):
                    offenders.append(f"{path.relative_to(_ROOT).as_posix()}::{node.name}")

        assert offenders == [], (
            "Publishers must be (<ids>, db, [*, commit,] <extras>), with commit required:\n  " + "\n  ".join(offenders)
        )


#: Writes to a versioned package that carry no ``If-Match``, with why (``optimistic-concurrency.md``, "What is not versioned").
_UNVERSIONED_WRITES = {
    ("activities/activity/router.py", "edit_activities"): "the bulk edit has no single record to name",
}

#: Routes that take a ``{user_id}`` path parameter, hold only a regular-user scope and take no ``CurrentUserId``.
_USER_PATH_WITHOUT_OWNER = {
    ("users/users/router.py", "read_users_id"): "returns the public projection, which any authenticated user may read",
}


def _declared_scopes(call: ast.Call) -> set[str]:
    """Return the scope strings a route decorator passes to its scope check."""
    return {
        node.value
        for keyword in call.keywords
        if keyword.arg == "dependencies"
        for node in ast.walk(keyword.value)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _parameter_aliases(function: ast.FunctionDef) -> str:
    """Return the unparsed parameter list, for a check that an alias is among the annotations."""
    return ast.unparse(function.args)


#: Last path segments that name an action on a resource, not a representation of it.
_ACTION_SEGMENTS = {"approve", "revoke", "read", "enable", "disable", "unlink"}


class TestActionRoutes:
    def test_an_action_is_a_post(self):
        """An action neither replaces nor partially edits a representation, so it is a ``POST``.

        ``PUT`` and ``PATCH`` mean "this is what the resource looks like now"; mixing them with ``POST`` for
        approve, revoke, read, enable, disable and unlink left clients guessing the verb of each.
        """
        offenders = []
        for path, function in _router_functions():
            for method, call in _route_decorators(function):
                route = call.args[0].value if call.args and isinstance(call.args[0], ast.Constant) else ""
                if route.rsplit("/", 1)[-1] in _ACTION_SEGMENTS and method != "post":
                    offenders.append(
                        f"{path.relative_to(_ROOT).as_posix()}::{function.name} ({method.upper()} {route})"
                    )

        assert offenders == [], "Make these actions POST routes:\n  " + "\n  ".join(offenders)


class TestVersionedAndOwnedRoutes:
    def test_a_versioned_resource_is_edited_only_with_if_match(self):
        """A ``PUT``/``PATCH`` in a package whose model declares ``version_id_col`` takes ``IfMatch``.

        Without it the write is last-writer-wins and silently loses a concurrent edit. Creates, deletes and
        actions are not versioned; the exceptions are listed with their reason.
        """
        offenders = []
        for path, function in _router_functions():
            models = path.parent / "models.py"
            if not models.exists() or "version_id_col" not in models.read_text():
                continue
            relative = path.relative_to(_ROOT).as_posix()
            if (relative, function.name) in _UNVERSIONED_WRITES:
                continue
            edits = any(method in {"put", "patch"} for method, _ in _route_decorators(function))
            if edits and "IfMatch" not in _parameter_aliases(function):
                offenders.append(f"{relative}::{function.name}")

        assert offenders == [], "Take core_dependencies.IfMatch (see optimistic-concurrency.md) in:\n  " + "\n  ".join(
            offenders
        )

    def test_a_route_naming_another_user_checks_ownership_or_needs_an_admin_scope(self):
        """A route with a ``{user_id}`` path parameter takes ``CurrentUserId`` or requires an admin-class scope.

        ``users:read`` and ``profile`` belong to every regular user, so a route guarded only by them that
        names another user is open to any account (an IDOR). Admin scopes end in ``_all`` or are minted only in an
        ``*_ADMIN_SCOPE`` tuple of ``modules.auth.constants``.
        """
        admin_scopes = {
            scope for name, scopes in vars(auth_constants).items() if name.endswith("_ADMIN_SCOPE") for scope in scopes
        }
        offenders = []
        for path, function in _router_functions():
            relative = path.relative_to(_ROOT).as_posix()
            if role_of(path.stem) != "router" or (relative, function.name) in _USER_PATH_WITHOUT_OWNER:
                continue
            for _, call in _route_decorators(function):
                if not call.args or not isinstance(call.args[0], ast.Constant) or "{user_id}" not in call.args[0].value:
                    continue
                scopes = _declared_scopes(call)
                is_admin = any(scope in admin_scopes or scope.endswith("_all") for scope in scopes)
                if scopes and not is_admin and "CurrentUserId" not in _parameter_aliases(function):
                    offenders.append(f"{relative}::{function.name}")

        assert offenders == [], (
            "Require an admin scope or take CurrentUserId and check ownership in the service:\n  "
            + "\n  ".join(offenders)
        )
