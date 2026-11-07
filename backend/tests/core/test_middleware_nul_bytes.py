"""NUL characters are refused before they reach a text column, which PostgreSQL cannot store them in."""

import ast
import json
import pathlib

import pytest
from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.testclient import TestClient
from pydantic import BaseModel

import core.exceptions as core_exceptions
import core.middleware_body_limit as body_limit
import core.middleware_nul_bytes as nul_bytes


class Payload(BaseModel):
    name: str


@pytest.fixture
def client():
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    # The inner middleware is added first, so the body cap wraps it and still sees the stream.
    app.add_middleware(nul_bytes.NulByteMiddleware)
    app.add_middleware(body_limit.BodySizeLimitMiddleware)

    @app.post("/json")
    def json_route(payload: Payload):
        return {"name": payload.name}

    @app.post("/raw")
    async def raw(request: Request):
        return {"size": len(await request.body())}

    @app.post("/login")
    def login(username: str = Form(), password: str = Form()):
        return {"username": username}

    @app.post("/upload")
    def upload(file: UploadFile):
        return {"name": file.filename}

    @app.get("/search")
    def search(q: str = ""):
        return {"q": q}

    @app.get("/things/{name}")
    def thing(name: str):
        return {"name": name}

    return TestClient(app)


def _refused(response, field):
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "urn:endurain:error:validation-failed"
    assert body["errors"][0]["field"] == field


class TestRefused:
    def test_a_json_string_with_an_escaped_nul(self, client):
        _refused(
            client.post("/json", content=b'{"name": "a\\u0000b"}', headers={"content-type": "application/json"}), "body"
        )

    def test_a_json_key_with_an_escaped_nul(self, client):
        _refused(client.post("/raw", content=b'{"a\\u0000": 1}', headers={"content-type": "application/json"}), "body")

    def test_a_nul_nested_in_a_json_structure(self, client):
        body = json.dumps({"a": [{"b": ["x\u0000"]}]})

        _refused(client.post("/raw", content=body, headers={"content-type": "application/json"}), "body")

    def test_a_nul_written_in_upper_case_hex_digits(self, client):
        _refused(client.post("/raw", content=b'["\\u0000"]', headers={"content-type": "application/json"}), "body")

    def test_a_login_form_field(self, client):
        _refused(client.post("/login", data={"username": "bob\x00", "password": "x"}), "body")

    def test_a_percent_encoded_nul_in_a_form(self, client):
        response = client.post(
            "/login",
            content=b"username=bob%00&password=x",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

        _refused(response, "body")

    def test_a_query_string(self, client):
        _refused(client.get("/search?q=a%00b"), "query")

    def test_a_path(self, client):
        _refused(client.get("/things/a%00b"), "path")


class TestAccepted:
    def test_an_escaped_backslash_followed_by_u0000_text_is_not_a_nul(self, client):
        response = client.post(
            "/json", content=b'{"name": "a\\\\u0000b"}', headers={"content-type": "application/json"}
        )

        assert response.json() == {"name": "a\\u0000b"}

    def test_a_normal_json_body_reaches_the_route_intact(self, client):
        assert client.post("/json", json={"name": "Ana"}).json() == {"name": "Ana"}

    def test_a_large_body_is_replayed_whole(self, client):
        body = json.dumps({"name": "x" * 500_000})

        assert client.post("/raw", content=body, headers={"content-type": "application/json"}).json() == {
            "size": len(body)
        }

    def test_a_normal_form_reaches_the_route(self, client):
        assert client.post("/login", data={"username": "bob", "password": "x"}).json() == {"username": "bob"}

    def test_an_invalid_json_body_is_left_to_the_route_to_refuse(self, client):
        response = client.post("/json", content=b"{not json", headers={"content-type": "application/json"})

        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] != "body"

    def test_a_multipart_upload_is_not_inspected(self, client):
        response = client.post("/upload", files={"file": ("a.bin", b"\x00\x00%00\\u0000")})

        assert response.json() == {"name": "a.bin"}

    def test_a_request_without_a_body_or_query_passes(self, client):
        assert client.get("/search?q=ok").json() == {"q": "ok"}

    def test_a_percent_encoded_percent_followed_by_digits_is_not_a_nul(self, client):
        assert client.get("/search?q=%2500").json() == {"q": "%00"}

    def test_an_oversized_body_is_still_refused_by_the_cap(self, client, monkeypatch):
        monkeypatch.setattr(body_limit, "MAX_BODY_BYTES", 100)

        response = client.post("/raw", content=b"[" + b"1," * 200 + b"1]", headers={"content-type": "application/json"})

        assert response.status_code == 413


class TestJsonIsParsedOnlyWhenItCanHoldANul:
    def test_a_body_without_the_escape_is_not_parsed(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(nul_bytes, "_json_contains_nul", lambda document: calls.append(document))
        body = json.dumps({"name": "x" * 100_000})

        response = client.post("/raw", content=body, headers={"content-type": "application/json"})

        assert response.json() == {"size": len(body)}
        assert calls == []

    @pytest.mark.parametrize("encoding", ["utf-16", "utf-32", "utf-16-le"])
    def test_a_utf_16_or_32_body_with_an_escaped_nul_is_refused(self, client, encoding):
        body = '{"name": "a\\u0000b"}'.encode(encoding)

        _refused(client.post("/raw", content=body, headers={"content-type": "application/json"}), "body")

    def test_a_utf_16_body_without_one_passes(self, client):
        body = '{"name": "ab"}'.encode("utf-16")

        assert client.post("/raw", content=body, headers={"content-type": "application/json"}).json() == {
            "size": len(body)
        }

    def test_a_body_that_is_not_text_is_left_to_the_route(self, client):
        body = b"\xff\xfe\xfd\x00\x00"

        assert client.post("/raw", content=body, headers={"content-type": "application/json"}).status_code == 200


def _middleware_registration_order() -> list[str]:
    """Name the classes ``create_app`` passes to ``add_middleware``, in call order."""
    tree = ast.parse((pathlib.Path(__file__).resolve().parents[2] / "app" / "main.py").read_text())
    create_app = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    )
    calls = sorted(
        (
            node
            for node in ast.walk(create_app)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_middleware"
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )
    return [ast.unparse(call.args[0]).rsplit(".", 1)[-1] for call in calls]


def test_the_application_installs_it_inside_the_body_cap():
    """A middleware added earlier sits inside one added later (the last added is the outermost).

    main.py builds the app on import and needs a full deployment environment, so the registration order is read
    from the ``add_middleware`` calls rather than from ``app.user_middleware``.
    """
    order = _middleware_registration_order()

    assert order.count("NulByteMiddleware") == 1
    assert order.index("NulByteMiddleware") < order.index("BodySizeLimitMiddleware")
