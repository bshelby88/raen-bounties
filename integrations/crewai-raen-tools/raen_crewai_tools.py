"""CrewAI @tool wrappers for the RAEN MCP gateway: dispute letter + contract analysis.

Single-file importable module (RAEN bounty 3). HTTP transport is stdlib urllib,
so there are no dependencies beyond crewai itself. Without crewai installed the
module still imports and the plain functions stay usable, which keeps tests
dependency-free.

Environment:
    RAEN_MCP_KEY  Bearer gateway key (required; spend real USDC per tool call).
    RAEN_MCP_URL  Gateway endpoint override (default: live fly.dev gateway).
"""

import json
import os
import urllib.error
import urllib.request

GATEWAY_URL = "https://raen-mcp-gateway.fly.dev/mcp"
PROTOCOL_VERSION = "2025-03-26"

try:
    from crewai.tools import tool
except ImportError:  # crewai optional at import time; @tool is applied when present
    def tool(func):
        return func


class RAENGatewayError(RuntimeError):
    """Gateway unreachable, unauthorized, or returned an MCP-level error."""


def _parse_body(content_type, raw):
    """Decode a streamable-HTTP response body: plain JSON or one SSE data line."""
    if not raw.strip():
        return None
    if "text/event-stream" in (content_type or ""):
        for line in raw.decode(errors="replace").splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise RAENGatewayError("SSE response contained no data line")
    return json.loads(raw.decode(errors="replace"))


class RAENGatewayClient:
    """Minimal MCP streamable-HTTP client: initialize once, then tools/call."""

    def __init__(self, url=None, key=None, timeout=180):
        self.url = url or os.environ.get("RAEN_MCP_URL") or GATEWAY_URL
        self.key = key or os.environ.get("RAEN_MCP_KEY", "")
        self.timeout = timeout
        self.session_id = None
        self._next_id = 0
        if not self.key:
            raise RAENGatewayError("Set RAEN_MCP_KEY to your RAEN MCP gateway dev key.")

    def _post(self, payload):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.key,
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
            headers["mcp-protocol-version"] = PROTOCOL_VERSION
        request = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = _parse_body(response.headers.get("Content-Type"), response.read())
                session = response.headers.get("mcp-session-id")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise RAENGatewayError(f"HTTP {exc.code} from gateway: {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise RAENGatewayError(f"gateway unreachable: {exc}") from exc
        return body, session

    def _handshake(self):
        self._next_id += 1
        body, session = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "raen-crewai-tools", "version": "1.0"},
            },
        })
        if body is None or "result" not in body:
            raise RAENGatewayError("initialize returned no result")
        self.session_id = session or "anonymous"
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call_tool(self, name, arguments):
        """Call one gateway tool and return its concatenated text content."""
        if self.session_id is None:
            self._handshake()
        self._next_id += 1
        body, _ = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if body is None:
            raise RAENGatewayError("gateway returned an empty response")
        if "error" in body:
            error = body["error"]
            raise RAENGatewayError(f"MCP error {error.get('code')}: {error.get('message')}")
        result = body.get("result") or {}
        text = "\n".join(
            block.get("text", "")
            for block in result.get("content", [])
            if block.get("type") == "text"
        )
        if result.get("isError"):
            raise RAENGatewayError(f"tool error: {text or 'unknown'}")
        return text


def _call(name, arguments):
    return RAENGatewayClient().call_tool(name, arguments)


@tool
def raen_dispute_letter(creditor: str, reason: str) -> str:
    """Draft an FCRA-compliant credit dispute letter and on-chain certificate.

    Args:
        creditor: Name of the creditor or collection agency.
        reason: Grounds for the dispute, e.g. 'Debt is not mine / inaccurate reporting'.

    Calls RAEN's paid MCP gateway (dispute-forge service, $0.75 USDC on Base).
    Returns JSON text with letter_body, cert_svg, timestamp and signature.
    """
    return _call("raen_dispute_letter", {"creditor": creditor, "reason": reason})


@tool
def raen_contract_analysis(text: str, focus: str = "") -> str:
    """Analyze a contract for risk and flag one-sided clauses.

    Args:
        text: Full contract text to analyze.
        focus: Optional analysis focus, e.g. 'indemnification' or 'termination'.

    Calls RAEN's paid MCP gateway (contract-eye service, $0.05 USDC on Base).
    Returns JSON text with a risk score and flagged clauses.
    """
    arguments = {"text": text}
    if focus:
        arguments["focus"] = focus
    return _call("raen_contract_analysis", arguments)


TOOLS = [raen_dispute_letter, raen_contract_analysis]
