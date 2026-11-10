# RAEN Bounty Board

Open integration bounties for agent developers building on the RAEN x402 fleet.

**Reward:** the winning contributor gets a **free 30-day RAEN MCP gateway dev key**
(Bearer access to `law_lookup`, `dispute_letter`, `image_generate`, `contract_analyze`, `tool_finder`
at `https://raen-mcp-gateway.fly.dev/mcp`) plus a shout-out in
[raen-agent-directory/llms.txt](https://bshelby88.github.io/raen-agent-directory/llms.txt)
so every agent crawler that indexes us sees your integration.

## How it works

1. Pick an open bounty in [Issues](https://github.com/bshelby88/raen-bounties/issues) labeled `bounty`.
2. Comment `/claim <issue#>` — the issue gets an `claimed` label so nobody duplicates work.
3. Ship it (repo, gist, or PR). Open a PR here linking the artifact.
4. On merge/acceptance you get: dev key by email (ops@royalruby.io sends it, 24h turnaround),
   llms.txt listing, and your project linked from [the agent directory](https://bshelby88.github.io/raen-agent-directory/).

## What counts

Real, working, publicly linkable integration of a RAEN x402 service or the MCP gateway into any
agent framework (LangChain/LangGraph, CrewAI, ElizaOS, AutoGen, OpenHands, custom harnesses),
or tooling that helps other developers consume the fleet (CLI clients, wrappers, test harnesses).

## The fleet you're integrating

12 x402 services on Base Mainnet (USDC, pay-per-call, $0.01–$0.50/call), MCP gateway, llms.txt,
agents.json. Start at the [tool finder](https://bshelby88.github.io/raen-agent-directory/) or the
[integration cookbook](https://github.com/bshelby88/x402-cookbook).

> Not legal advice. Bounties reward code, not legal outcomes. CROA-compliant copy only.

— RAEN / Royal Agentic Enterprises · raen.royalruby.io

## Bounty 04 implementation

[Reusable x402 manifest drift Action](integrations/x402-manifest-watch/README.md), with fleet configuration, tests and a reproducible bad-payTo sample run.
