"""Route and signature conventions from ``code-standards.md`` and ``errors-and-api.md``, enforced.

Each rule is stated on what the code does, not on a file existing: a route declares what it
returns, a write is rate limited, and ``db`` sits where a reader expects it. They apply to every
converted module, so a new route or function is covered the day it is written.
"""

import ast
import pathlib

from tests._helpers.module_roles import CONVERTED_MODULES, files_with_role, role_of

_ROOT = pathlib.Path("app/modules")
_CONVERTED = tuple(_ROOT / name for name in CONVERTED_MODULES)

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
