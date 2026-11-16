"""Tests for the COROS MCP JSON-RPC client."""

from __future__ import annotations

import base64
import json

import httpx2
import pytest

import modules.coros.mcp_client as mcp_client


def _client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def _rpc(request: httpx2.Request) -> dict:
    return json.loads(request.content)


def _jsonrpc(result: dict, request_id: int = 1) -> httpx2.Response:
    return httpx2.Response(200, json={"jsonrpc": "2.0", "id": request_id, "result": result})


class TestSession:
    """The client initializes once and reuses the session for every call."""

    def test_initialize_then_tools_list_and_call(self):
        methods: list[str] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            body = _rpc(request)
            methods.append(body["method"])
            if body["method"] == "initialize":
                return _jsonrpc({"protocolVersion": "2025-06-18"}, body["id"])
            if body["method"] == "tools/list":
                return _jsonrpc({"tools": [{"name": "querySportRecords"}]}, body["id"])
            return _jsonrpc(
                {
                    "content": [{"type": "text", "text": "ok"}],
                    "structuredContent": {"activities": []},
                },
                body["id"],
            )

        client = mcp_client.CorosMCPClient("https://mcpeu.coros.com/mcp", "token", client=_client(handler))
        client.initialize()
        tools = client.list_tools()
        result = client.call_tool("querySportRecords", {"startDate": "20260101"})

        assert tools == [{"name": "querySportRecords"}]
        assert result.content[0]["text"] == "ok"
        assert result.structured_content == {"activities": []}
        assert methods == ["initialize", "tools/list", "tools/call"]

    def test_tools_list_follows_pagination(self):
        pages = [
            {"tools": [{"name": "a"}], "nextCursor": "next"},
            {"tools": [{"name": "b"}]},
        ]

        def handler(request: httpx2.Request) -> httpx2.Response:
            body = _rpc(request)
            if body["method"] == "initialize":
                return _jsonrpc({}, body["id"])
            return _jsonrpc(pages.pop(0), body["id"])

        client = mcp_client.CorosMCPClient("https://mcpeu.coros.com/mcp", "token", client=_client(handler))
        assert [tool["name"] for tool in client.list_tools()] == ["a", "b"]


class TestTransportErrors:
    """Failures map to errors the sync can classify."""

    def test_a_rejected_token_is_an_authentication_error(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(401)

        client = mcp_client.CorosMCPClient("https://mcpeu.coros.com/mcp", "token", client=_client(handler))
        with pytest.raises(mcp_client.CorosMCPAuthenticationError):
            client.initialize()

    def test_rate_limit_carries_the_retry_after(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(429, headers={"retry-after": "30"})

        client = mcp_client.CorosMCPClient("https://mcpeu.coros.com/mcp", "token", client=_client(handler))
        with pytest.raises(mcp_client.CorosMCPRateLimitError) as exc_info:
            client.initialize()
        assert exc_info.value.retry_after == 30

    def test_a_5xx_is_retried_once_then_raises_transient(self):
        calls = 0

        def handler(request: httpx2.Request) -> httpx2.Response:
            nonlocal calls
            calls += 1
            return httpx2.Response(503)

        client = mcp_client.CorosMCPClient(
            "https://mcpeu.coros.com/mcp",
            "token",
            client=_client(handler),
            retry_delay_seconds=0,
        )
        with pytest.raises(mcp_client.CorosMCPTransientError):
            client.initialize()
        assert calls == 2

    def test_jsonrpc_error_is_a_tool_error(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            body = _rpc(request)
            return httpx2.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32602, "message": "bad arguments"}},
            )

        client = mcp_client.CorosMCPClient("https://mcpeu.coros.com/mcp", "token", client=_client(handler))
        with pytest.raises(mcp_client.CorosMCPToolError):
            client.initialize()

    def test_sse_response_is_decoded(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            body = _rpc(request)
            payload = {"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "a"}]}}
            return httpx2.Response(
                200,
                text=f"event: message\ndata: {json.dumps(payload)}\n\n",
                headers={"content-type": "text/event-stream"},
            )

        client = mcp_client.CorosMCPClient("https://mcpeu.coros.com/mcp", "token", client=_client(handler))
        assert client.list_tools() == [{"name": "a"}]


class TestPayloadExtraction:
    """FIT files and fallback URLs are extracted from MCP content blocks."""

    def test_resource_blob_is_decoded(self):
        payload = b"fit-bytes"
        result = mcp_client.MCPToolResult(
            content=[
                {
                    "type": "resource",
                    "resource": {"blob": base64.b64encode(payload).decode()},
                }
            ]
        )

        assert mcp_client.extract_binary_payload(result) == payload

    def test_image_data_is_decoded(self):
        payload = b"fit-bytes"
        result = mcp_client.MCPToolResult(content=[{"type": "image", "data": base64.b64encode(payload).decode()}])

        assert mcp_client.extract_binary_payload(result) == payload

    def test_urls_are_deduplicated(self):
        result = mcp_client.MCPToolResult(
            content=[
                {"type": "text", "text": "https://files.coros.com/a.fit https://files.coros.com/a.fit"},
                {"type": "text", "text": "https://files.coros.com/b.fit"},
            ]
        )

        assert mcp_client.extract_urls(result) == [
            "https://files.coros.com/a.fit",
            "https://files.coros.com/b.fit",
        ]

    def test_malformed_base64_is_not_returned(self):
        result = mcp_client.MCPToolResult(content=[{"type": "resource", "resource": {"blob": "not base64!"}}])

        assert mcp_client.extract_binary_payload(result) is None
