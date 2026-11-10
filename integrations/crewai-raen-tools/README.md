# CrewAI tools for the RAEN MCP gateway

Two CrewAI `@tool` wrappers that call the RAEN MCP gateway over streamable HTTP,
so a CrewAI crew can draft an FCRA dispute letter or analyze a contract mid-flow.
Built for [bounty 3](https://github.com/bshelby88/raen-bounties/issues/3).

| Tool | Gateway tool | Service | Price | Input |
|---|---|---|---|---|
| `raen_dispute_letter` | `raen_dispute_letter` | dispute-forge | $0.75 USDC | `{creditor, reason}` |
| `raen_contract_analysis` | `raen_contract_analysis` | contract-eye | $0.05 USDC | `{text, focus?}` |

(The bounty text says `contract_analyze`; the live gateway tool is named
`raen_contract_analysis` per its `tools/list`, so the wrapper matches the gateway.)

## Install / import

Single-file importable: copy `raen_crewai_tools.py` next to your crew code, or run
from this directory. Only dependency is `crewai` itself — the transport is stdlib
`urllib`, no MCP SDK needed. Without `crewai` installed the module still imports and
exposes plain functions.

## Use from a crew

```python
from raen_crewai_tools import TOOLS  # [raen_dispute_letter, raen_contract_analysis]

agent = Agent(role="...", goal="...", backstory="...", tools=TOOLS)
```

Or call directly:

```python
from raen_crewai_tools import raen_dispute_letter
letter = raen_dispute_letter.func(creditor="Acme Collections LLC",
                                  reason="Debt is not mine / inaccurate reporting")
```

## Environment

- `RAEN_MCP_KEY` — Bearer gateway dev key (required). Tool calls spend real USDC on Base.
- `RAEN_MCP_URL` — endpoint override, default `https://raen-mcp-gateway.fly.dev/mcp`.

A missing key raises `RAENGatewayError` before any HTTP request; 401/402 and MCP
errors also surface as `RAENGatewayError` with the gateway's message.

## Example crew script (one real call)

```sh
export RAEN_MCP_KEY=<30-day dev key>
python examples/crew_dispute_flow.py
```

The crew runs one task that calls `raen_dispute_letter` once against the live
gateway and prints the drafted letter body.

## Run and validate

```sh
python3 -m unittest discover -s integrations/crewai-raen-tools/tests -v
```

Tests run against a local in-process MCP streamable-HTTP fixture (no network, no
API keys): Bearer gate and 401 surfacing, initialize → `mcp-session-id` handshake
ordering, JSON and SSE response modes, documented argument shapes for both tools,
`focus` omitted when empty, MCP error responses, `isError` tool results (402-style
payment failures), unreachable gateway, and missing-key fail-fast.

## Protocol notes

The client speaks MCP streamable HTTP: `initialize` (captures the `mcp-session-id`
response header), `notifications/initialized`, then `tools/call` with Bearer auth
on every request. Responses are accepted as `application/json` or
`text/event-stream`. Verified against the live gateway's unauthenticated behavior
(401 `Send Authorization: Bearer <MCP_GATEWAY_KEY>`); full tool calls need a dev
key, which bounty winners receive.
