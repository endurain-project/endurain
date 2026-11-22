"""A small MCP client for the stateless COROS Streamable HTTP endpoint.

COROS MCP speaks JSON-RPC 2.0 over HTTP and returns JSON or SSE. This client
implements the three messages a tool caller needs — ``initialize``,
``tools/list`` and ``tools/call`` — with one bearer token and one client per
sync, so a session is opened once and reused instead of per operation.
"""

import base64
import binascii
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx2

import core.logger as core_logger
import core.provider_rate_limit as core_provider_rate_limit
import modules.coros.constants as coros_constants

logger = core_logger.get_logger(__name__)

_HTTP_TIMEOUT_SECONDS = 60.0
_MCP_PROTOCOL_VERSION = "2025-06-18"
_MAX_TOOL_PAGES = 10
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


class CorosMCPError(Exception):
    """Base error for the COROS MCP transport."""


class CorosMCPAuthenticationError(CorosMCPError):
    """The access token was rejected; the account must be reconnected."""


class CorosMCPRateLimitError(CorosMCPError):
    """COROS asked the caller to slow down."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        """Initialise the rate-limit error.

        Args:
            message: Safe error message.
            retry_after: Server-provided delay in seconds, when present.
        """
        super().__init__(message)
        self.retry_after = retry_after


class CorosMCPTransientError(CorosMCPError):
    """A timeout, network failure or server-side error worth retrying."""


class CorosMCPProtocolError(CorosMCPError):
    """COROS returned a response that is not valid MCP."""


class CorosMCPToolError(CorosMCPError):
    """A tool call was rejected or reported an error."""

    def __init__(self, tool_name: str, message: str) -> None:
        """Initialise the tool error.

        Args:
            tool_name: Name of the tool that failed.
            message: Safe error message.
        """
        super().__init__(message)
        self.tool_name = tool_name


class CorosToolUnavailableError(CorosMCPError):
    """A required tool is missing from the discovered tool list."""

    def __init__(self, tool_name: str) -> None:
        """Initialise the missing-tool error.

        Args:
            tool_name: Tool the integration requires.
        """
        super().__init__(f"COROS MCP does not expose {tool_name}")
        self.tool_name = tool_name


@dataclass
class MCPToolResult:
    """The payload of one ``tools/call`` result.

    Attributes:
        content: MCP content blocks.
        structured_content: Optional structured payload.
        is_error: Whether the tool reported an error.
    """

    content: list[dict[str, Any]] = field(default_factory=list)
    structured_content: dict[str, Any] | None = None
    is_error: bool = False


class CorosMCPClient:
    """One authenticated MCP session against the COROS endpoint."""

    def __init__(
        self,
        mcp_url: str,
        access_token: str,
        *,
        client: httpx2.Client | None = None,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        """Create a client.

        Args:
            mcp_url: Regional MCP endpoint.
            access_token: Bearer token issued by COROS.
            client: Optional HTTP client, for tests.
            retry_delay_seconds: Base delay between transient retries.
        """
        self._url = mcp_url
        self._access_token = access_token
        self._client = client
        self._owns_client = client is None
        self._retry_delay = retry_delay_seconds
        self._next_id = 1
        self._initialized = False

    def __enter__(self) -> "CorosMCPClient":
        """Enter the client context."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """Close a client created by this instance."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client when this instance owns it."""
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None

    def _http(self) -> httpx2.Client:
        """Return the HTTP client, creating one on first use.

        Returns:
            The HTTP client.
        """
        if self._client is None:
            self._client = httpx2.Client(
                timeout=_HTTP_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        return self._client

    def _headers(self) -> dict[str, str]:
        """Return the MCP request headers.

        Returns:
            Authorization and content negotiation headers.
        """
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send one JSON-RPC request, retrying transient failures.

        Args:
            method: MCP method name.
            params: Method parameters.

        Returns:
            The JSON-RPC result object.

        Raises:
            CorosMCPAuthenticationError: When the token is rejected.
            CorosMCPRateLimitError: When COROS rate-limits the caller.
            CorosMCPTransientError: When the request can be retried.
            CorosMCPProtocolError: When the response is not usable MCP.
            CorosMCPToolError: When the server returns a JSON-RPC error.
        """
        request_id = self._next_id
        self._next_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = self._http().post(self._url, headers=self._headers(), json=body)
            except (httpx2.TimeoutException, httpx2.RequestError) as err:
                last_error = CorosMCPTransientError("COROS MCP request failed")
                if attempt == 0:
                    time.sleep(self._retry_delay)
                    continue
                raise last_error from err
            if response.status_code in (401, 403):
                raise CorosMCPAuthenticationError("COROS rejected the access token")
            if response.status_code == 429:
                retry_after = core_provider_rate_limit.parse_retry_after(response.headers.get("retry-after"))
                raise CorosMCPRateLimitError("COROS rate limit reached", retry_after)
            if response.status_code == 404 and attempt == 0:
                last_error = CorosMCPTransientError("COROS MCP endpoint returned 404")
                time.sleep(self._retry_delay)
                continue
            if response.status_code >= 500:
                last_error = CorosMCPTransientError("COROS MCP is unavailable")
                if attempt == 0:
                    time.sleep(self._retry_delay)
                    continue
                raise last_error
            if response.status_code != 200:
                raise CorosMCPProtocolError("COROS MCP rejected the request")
            payload = _payload_from_response(response, request_id)
            if "error" in payload:
                error = payload["error"]
                code = error.get("code") if isinstance(error, dict) else None
                message = error.get("message") if isinstance(error, dict) else None
                safe_message = message if isinstance(message, str) and len(message) <= 200 else "COROS tool error"
                raise CorosMCPToolError(method, f"{safe_message} ({code})")
            result = payload.get("result")
            if not isinstance(result, dict):
                raise CorosMCPProtocolError("COROS MCP returned no result object")
            return result
        raise last_error or CorosMCPTransientError("COROS MCP request failed")

    def initialize(self) -> dict[str, Any]:
        """Initialize the MCP session.

        Returns:
            The server's initialize result.
        """
        result = self._request(
            "initialize",
            {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "Endurain", "version": "1.0.0"},
            },
        )
        self._initialized = True
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        """Discover every tool the server publishes.

        Returns:
            The tool definitions, across all pages.
        """
        if not self._initialized:
            self.initialize()
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        for _page in range(_MAX_TOOL_PAGES):
            params = {"cursor": cursor} if cursor else {}
            result = self._request("tools/list", params)
            page = result.get("tools")
            if not isinstance(page, list):
                raise CorosMCPProtocolError("COROS tools/list returned no tools")
            tools.extend(tool for tool in page if isinstance(tool, dict))
            next_cursor = result.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        """Call one discovered tool.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            The tool result.

        Raises:
            CorosMCPToolError: When the tool reports an error.
        """
        if not self._initialized:
            self.initialize()
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content")
        structured = result.get("structuredContent")
        is_error = bool(result.get("isError"))
        tool_result = MCPToolResult(
            content=[item for item in content if isinstance(item, dict)] if isinstance(content, list) else [],
            structured_content=structured if isinstance(structured, dict) else None,
            is_error=is_error,
        )
        if is_error:
            raise CorosMCPToolError(name, _tool_error_text(tool_result))
        return tool_result


def _payload_from_response(response: httpx2.Response, request_id: int) -> dict[str, Any]:
    """Decode a JSON or SSE MCP response.

    Args:
        response: HTTP response.
        request_id: JSON-RPC request id to match in an SSE stream.

    Returns:
        The JSON-RPC envelope.

    Raises:
        CorosMCPProtocolError: When no usable envelope is present.
    """
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if not data or data == "[DONE]":
                continue
            try:
                payload = json.loads(data)
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get("id") == request_id:
                return payload
        raise CorosMCPProtocolError("COROS MCP returned no matching SSE response")
    try:
        payload = response.json()
    except ValueError as err:
        raise CorosMCPProtocolError("COROS MCP returned invalid JSON") from err
    if not isinstance(payload, dict):
        raise CorosMCPProtocolError("COROS MCP returned a non-object response")
    return payload


def _tool_error_text(result: MCPToolResult) -> str:
    """Return a safe error message from a tool error result.

    Args:
        result: Failed tool result.

    Returns:
        The first text block, truncated, or a generic message.
    """
    for item in result.content:
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            return item["text"][:200]
    return "COROS tool error"


def _decode_base64(value: str) -> bytes | None:
    """Decode a base64 payload, rejecting malformed or oversized input.

    Args:
        value: Base64 string.

    Returns:
        Decoded bytes, or None when the value is not base64.
    """
    compact = "".join(value.split())
    if not compact or not _BASE64_RE.fullmatch(compact):
        return None
    if len(compact) // 4 * 3 > coros_constants.MAX_FIT_BYTES:
        return None
    try:
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return None


def extract_binary_payload(result: MCPToolResult) -> bytes | None:
    """Return the first binary payload carried by a tool result.

    COROS returns FIT files as MCP ``resource`` blocks with a base64 ``blob``.
    Text-only fallbacks are handled by :func:`extract_urls`.

    Args:
        result: Tool result.

    Returns:
        The decoded bytes, or None when the result carries no binary payload.
    """
    for item in result.content:
        item_type = item.get("type")
        if item_type == "resource":
            resource = item.get("resource")
            if isinstance(resource, dict):
                blob = resource.get("blob")
                if isinstance(blob, str):
                    decoded = _decode_base64(blob)
                    if decoded:
                        return decoded
                text = resource.get("text")
                if isinstance(text, str):
                    decoded = _decode_base64(text)
                    if decoded:
                        return decoded
        elif item_type in {"image", "audio"}:
            data = item.get("data")
            if isinstance(data, str):
                decoded = _decode_base64(data)
                if decoded:
                    return decoded
        elif item_type == "text":
            text = item.get("text")
            if isinstance(text, str) and len(text) > 256 and "://" not in text:
                decoded = _decode_base64(text)
                if decoded:
                    return decoded
    structured = result.structured_content
    if structured:
        candidate = _find_base64_field(structured)
        if candidate:
            return candidate
    return None


def _find_base64_field(value: Any) -> bytes | None:
    """Find a base64 payload under a known structured-content key.

    Args:
        value: Structured content value.

    Returns:
        The decoded bytes, or None.
    """
    if isinstance(value, dict):
        for key in ("blob", "base64", "contentBase64", "content_base64", "data"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                decoded = _decode_base64(candidate)
                if decoded:
                    return decoded
        for nested in value.values():
            found = _find_base64_field(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_base64_field(nested)
            if found:
                return found
    return None


def extract_urls(result: MCPToolResult) -> list[str]:
    """Return every HTTP(S) URL carried by a tool result.

    Args:
        result: Tool result.

    Returns:
        The URLs, deduplicated in encounter order.
    """
    urls: list[str] = []
    texts: list[str] = []
    for item in result.content:
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            texts.append(item["text"])
        elif item.get("type") == "resource":
            resource = item.get("resource")
            if isinstance(resource, dict) and isinstance(resource.get("uri"), str):
                texts.append(resource["uri"])
        elif item.get("type") == "resource_link" and isinstance(item.get("uri"), str):
            texts.append(item["uri"])
    if result.structured_content:
        texts.extend(_strings_in(result.structured_content))
    for text in texts:
        for match in re.findall(r"https://[^\s\"'<>]+", text):
            cleaned = match.rstrip(").,;")
            if cleaned not in urls:
                urls.append(cleaned)
    return urls


def _strings_in(value: Any) -> list[str]:
    """Collect strings recursively from structured content.

    Args:
        value: Structured content value.

    Returns:
        The strings found.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for nested in value.values() for text in _strings_in(nested)]
    if isinstance(value, list):
        return [text for nested in value for text in _strings_in(nested)]
    return []
