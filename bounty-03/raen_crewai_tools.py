#!/usr/bin/env python3
"""BOUNTY-03: CrewAI @tool wrappers calling the RAEN MCP gateway for dispute_letter and contract_analyze."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable

try:
    from crewai.tools import tool as crewai_tool  # type: ignore
except ImportError:
    def crewai_tool(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Fallback @tool decorator when crewai is not installed in minimal test environments."""
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            setattr(fn, "tool_name", name)
            setattr(fn, "is_crewai_tool", True)
            setattr(fn, "run", fn)
            return fn
        return decorator

DEFAULT_RAEN_MCP_URL = "https://raen-mcp-gateway.fly.dev/mcp"


class RaenMcpGatewayClient:
    """Streamable HTTP JSON-RPC 2.0 client for the RAEN MCP Gateway."""

    def __init__(
        self,
        api_key: str | None = None,
        gateway_url: str | None = None,
        transport: Callable[[str, dict[str, str], bytes], dict[str, Any]] | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("RAEN_MCP_API_KEY", "")
        self.gateway_url = gateway_url or os.environ.get("RAEN_MCP_URL", DEFAULT_RAEN_MCP_URL)
        self._transport = transport

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key.strip():
            raise ValueError("RAEN_MCP_API_KEY is required to call the RAEN MCP gateway")

        payload = {
            "jsonrpc": "2.0",
            "id": f"crewai-{tool_name}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "raen-crewai-tools/1.0.0",
        }
        body = json.dumps(payload).encode("utf-8")

        if self._transport is not None:
            resp = self._transport(self.gateway_url, headers, body)
        else:
            req = urllib.request.Request(self.gateway_url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as http_resp:
                raw = http_resp.read().decode("utf-8")
                resp = json.loads(raw)

        if "error" in resp:
            raise RuntimeError(f"RAEN MCP error: {resp['error']}")
        return resp.get("result", resp)


_DEFAULT_CLIENT: RaenMcpGatewayClient | None = None


def set_default_client(client: RaenMcpGatewayClient | None) -> None:
    global _DEFAULT_CLIENT
    _DEFAULT_CLIENT = client


def _get_client() -> RaenMcpGatewayClient:
    return _DEFAULT_CLIENT or RaenMcpGatewayClient()


@crewai_tool("dispute_letter")
def dispute_letter(
    recipient: str,
    claim_summary: str,
    statutory_basis: str = "FCRA 15 U.S.C. § 1681i",
    requested_remedy: str = "Immediate deletion or correction of inaccurate item within 30 days",
) -> str:
    """Draft a formal dispute letter via the RAEN MCP gateway (`dispute_letter`)."""
    result = _get_client().call_tool(
        "dispute_letter",
        {
            "recipient": recipient,
            "claim_summary": claim_summary,
            "statutory_basis": statutory_basis,
            "requested_remedy": requested_remedy,
        },
    )
    content = result.get("content", [])
    if isinstance(content, list) and content:
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return json.dumps(result)


@crewai_tool("contract_analyze")
def contract_analyze(
    contract_text: str,
    focus_areas: str = "indemnification, limitation of liability, auto-renewal, termination",
    jurisdiction: str = "US-DE",
) -> str:
    """Analyze a contract for risk clauses and obligations via the RAEN MCP gateway (`contract_analyze`)."""
    result = _get_client().call_tool(
        "contract_analyze",
        {
            "contract_text": contract_text,
            "focus_areas": focus_areas,
            "jurisdiction": jurisdiction,
        },
    )
    content = result.get("content", [])
    if isinstance(content, list) and content:
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return json.dumps(result)
