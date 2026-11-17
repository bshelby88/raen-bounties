# RAEN Fleet & MCP Tools — Cursor & VS Code Extension (BOUNTY-06)

VS Code and Cursor IDE extension that surfaces the **RAEN SKU catalog, per-call micro-pricing, and paid MCP tool execution** directly inside your editor.

Integrates:
- **SKU Catalog**: Dynamically pulled and parsed from `raen-agent-directory` ([`llms.txt`](https://raw.githubusercontent.com/bshelby88/raen-agent-directory/main/llms.txt)).
- **Paid Execution**: Direct streamable JSON-RPC 2.0 client communicating with the RAEN MCP Gateway (`https://raen-mcp-gateway.fly.dev/mcp`).
- **One-Liner Cursor MCP Integration**: Generates `.cursor/mcp.json` with a single command or one-click action.

---

## Features

### 1. Activity Bar Sidebar: "RAEN Fleet"
Explorer TreeView displaying all fleet offerings grouped by category:
- **MCP Flagship Tools**: 5 tools exposed by the gateway (`raen_law_lookup`, `raen_ticker_analysis`, `raen_dispute_letter`, `raen_image_generate`, `raen_contract_analysis`) with active pricing ($0.01–$0.10 USDC).
- **Production x402 Services**: 150+ fleet services on Base mainnet (`royal-ruby-x402`, `vault-pro-x402`, `dispute-forge-x402`, `contract-eye-x402`, `nanobanana-x402`, etc.) with manifest links (`/.well-known/x402.json`).
- **Cloudflare Workers**: Edge endpoints (`dispute-forge-worker`, etc.).
- **Fleet Reference & Benchmarks**: Real autonomous operations datasets (`benchmark.html`).

### 2. Interactive Tool Invocation from the IDE
- **`RAEN: Run Law Lookup (FCRA/FDCPA)`**: Prompts for consumer-protection topics, executes against `raen_law_lookup`, and displays legal citations with statutes of limitations.
- **`RAEN: Audit Contract Selection`**: Available from the editor right-click context menu. Analyzes the highlighted agreement text via `raen_contract_analysis` and flags risky clauses.
- **Dedicated Output Channel (`RAEN Fleet Output`)**: Streams live JSON-RPC request/response payloads, connection handshakes, and settlement receipt hashes.

### 3. Cursor MCP Server Auto-Configuration
- **Command `RAEN: Configure Cursor MCP Server (.cursor/mcp.json)`**: Writes or copies the exact MCP configuration into your workspace `.cursor/mcp.json` for immediate Cursor Composer and Chat tool access.

```json
{
  "mcpServers": {
    "raen": {
      "url": "https://raen-mcp-gateway.fly.dev/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_DEV_KEY>"
      }
    }
  }
}
```

### 4. Status Bar & Authentication Management
- Status bar item showing `$(server) RAEN: Ready` when a dev key is configured, or `$(server) RAEN: Set Dev Key` to input via secure dialog.
- Dev keys can be requested free of charge via self-serve:
  ```bash
  curl -X POST https://raen-mcp-gateway.fly.dev/keys/request \
    -H "Content-Type: application/json" \
    -d '{"email":"your-email@domain.com"}'
  ```

---

## Extension Installation

### Option A: Local Development / Testing
1. Clone the repository and navigate to `bounty-06/`:
   ```bash
   cd bounty-06
   ```
2. Open `bounty-06` in VS Code or Cursor:
   ```bash
   code .
   # or
   cursor .
   ```
3. Press `F5` to launch an Extension Development Host window.
4. The **RAEN Fleet** icon appears in the left Activity Bar.

### Option B: Package VSIX
```bash
npx @vscode/vsce package --no-dependencies
# Install in Cursor/VS Code:
cursor --install-extension raen-ide-extension-1.0.0.vsix
```

---

## Unit & Integration Test Suite

Run the automated test runner (uses Node's native `node --test`):

```bash
npm test
```

### Test Suite Output

```
▶ RAEN Catalog Service & llms.txt Parser
  ✔ parses llms.txt correctly into structured SKU entities (19.5774ms)
  ✔ combines MCP tools with catalog items (267.3096ms)
✔ RAEN Catalog Service & llms.txt Parser (295.5068ms)
▶ RaenMcpClient Protocol Handling
  ✔ formats JSON-RPC 2.0 messages correctly (300.4812ms)
  ✔ handles 402 challenge gracefully with structured receipt (3.5486ms)
  ✔ captures payment response receipt headers on success (2.6426ms)
✔ RaenMcpClient Protocol Handling (312.8421ms)
▶ Cursor MCP Configuration Generator
  ✔ generates valid .cursor/mcp.json structure with auth headers (0.8822ms)
  ✔ generates one-liner JSON string (0.6152ms)
✔ Cursor MCP Configuration Generator (2.1896ms)
ℹ tests 7
ℹ suites 3
ℹ pass 7
ℹ fail 0
```

---

## Live Gateway Demo & Verification Transcript

Run the included verification runner:

```bash
node bounty-06/demo/ide-runner-demo.mjs
```

### Live Transcript against `raen-mcp-gateway.fly.dev` and `raen-agent-directory`

```
==================================================================
  RAEN IDE EXTENSION (BOUNTY-06) — VERIFICATION & LIVE DEMO
==================================================================

[1] Environment & Configuration:
    Gateway URL : https://raen-mcp-gateway.fly.dev/mcp
    Catalog URL : https://raw.githubusercontent.com/bshelby88/raen-agent-directory/main/llms.txt
    Dev Key     : None (402 challenge demonstration)

[2] Executing live MCP Gateway handshake (initialize)...
    Handshake SUCCESS:
    Server Name    : raen-mcp
    Protocol Ver   : 2025-03-26
    Server Info    : RAEN paid x402 services. Each tool call spends USDC on Base via the x402 protocol; prices ...

[3] Fetching RAEN fleet SKU catalog from llms.txt & live MCP tools...
    Catalog loaded: 170 total entities
    - MCP Flagship Tools   : 5
      * [$0.05 USDC] RAEN Law Lookup (FCRA/FDCPA/TILA/UDAP) (raen_law_lookup)
      * [$0.05 USDC] RAEN Ticker Consensus Demo (raen_ticker_analysis)
      * [$0.10 USDC] RAEN Dispute Letter (raen_dispute_letter)
      * [$0.01 USDC] RAEN Image Generation (raen_image_generate)
      * [$0.05 USDC] RAEN Contract Analysis (raen_contract_analysis)
    - Production x402 Fleet: 157 services (e.g. royal-ruby-x402, vault-pro-x402, dispute-forge-x402...)
    - Cloudflare Workers   : 2 workers (e.g. dispute-forge-worker, dispute-forge-worker)

[4] Invoking paid MCP tool: raen_law_lookup for topic "FCRA § 605 7-year obsolete reporting timeline"...
    [x402 Payment Challenge Captured from Gateway]:
    Error Message  : Payment required
    Network        : eip155:8453
    Amount         : 50000 (0.05 USDC)
    PayTo Address  : 0x9b8a27e03CEbA490953cDa8AB1291c0E13bAf72f
    Instructions   : 1. Sign an x402 v2 exact-scheme payment for 50000 (0.05 USDC) to 0x9b8a27e03CEbA490953cDa8AB1291c0E13bAf72f on...

[5] Generating Cursor MCP One-Liner (.cursor/mcp.json)...
{
  "mcpServers": {
    "raen": {
      "url": "https://raen-mcp-gateway.fly.dev/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_RAEN_DEV_KEY"
      }
    }
  }
}

==================================================================
  VERIFICATION COMPLETE: Live handshake, catalog & tools OK.
==================================================================
```
